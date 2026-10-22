/// <reference types="node" />
/**
 * ACP transport 的 Node stdio 子进程实现。
 *
 * 职责（对照 Python 参考实现 session.py 的 start / _read_stdout /
 * _drain_stderr / _terminate_process_tree / close）：
 * - `spawn` 拉起 agent（如 `chrys acp`），stdin/stdout/stderr 三管道；
 * - stdout 用 LineDecoder 行分帧（含半包拼接），stderr 旁路透传；
 * - Windows 强杀走 `taskkill /PID <pid> /T /F` 杀整棵进程树——单杀父
 *   进程会留下孤儿子进程；POSIX 走 SIGTERM → 宽限 → SIGKILL；
 * - 优雅关闭：先 `session/close`（上层的事）再关 stdin，等对端退出。
 *
 * 运行环境说明：本文件只在 Node 侧加载（vitest / 未来 Tauri 主进程
 * 工具脚本）；webview 前端应改用 Tauri IPC 实现的 AcpTransport。
 */

import { spawn, type ChildProcessWithoutNullStreams } from "node:child_process";
import process from "node:process";

import { AcpWriteError } from "../errors.ts";
import { LineDecoder } from "../framing.ts";
import {
  HandlerSlot,
  type AcpTransport,
  type TransportExit,
  type TransportLineHandler,
  type TransportStderrHandler,
  type TransportExitHandler,
} from "./acpTransport.ts";

/** taskkill 强杀后等待进程回收的宽限（毫秒）。 */
const KILL_GRACE_MS = 5_000;
/** 优雅关闭（关 stdin 后）等待对端自行退出的默认宽限。 */
const DEFAULT_CLOSE_GRACE_MS = 5_000;

export interface StdioSpawnOptions {
  /** 完整 argv，如 ["chrys", "acp"]。 */
  readonly command: readonly string[];
  /** 工作目录。 */
  readonly cwd?: string;
  /** 注入的环境变量（与当前环境合并；null 表示不继承）。 */
  readonly env?: Readonly<Record<string, string>>;
  readonly extraEnv?: Readonly<Record<string, string>>;
}

/**
 * Node 子进程 transport。构造即 spawn；退出事件（对端自行退出或我们
 * 主动终止）都会且只会触发一次 onExit。
 */
export class NodeStdioTransport implements AcpTransport {
  private readonly child: ChildProcessWithoutNullStreams;
  private readonly decoder = new LineDecoder();
  private readonly lineSlot = new HandlerSlot<TransportLineHandler>();
  private readonly stderrSlot = new HandlerSlot<TransportStderrHandler>();
  private readonly exitSlot = new HandlerSlot<TransportExitHandler>();
  private readonly stderrDecoder = new TextDecoder("utf-8", { fatal: false });

  private closed = false;
  private exitPromise: Promise<TransportExit> | null = null;
  private settledExit = false;
  private reportedExit: TransportExit | null = null;

  constructor(options: StdioSpawnOptions) {
    const [file, ...args] = options.command;
    if (typeof file !== "string" || file.length === 0) {
      throw new Error("NodeStdioTransport：command 不能为空");
    }
    const env: NodeJS.ProcessEnv | undefined = options.env
      ? { ...options.env }
      : options.extraEnv
        ? { ...process.env, ...options.extraEnv }
        : undefined;
    this.child = spawn(file, args, {
      cwd: options.cwd,
      env,
      stdio: ["pipe", "pipe", "pipe"],
      // Windows 上 shell:false 直接 CreateProcess；chrys 是控制台程序，
      // 不需要 shell。POSIX 保持默认（不脱离进程组，与 Python 参考一致）。
      shell: false,
    });
    this.wireStreams();
  }

  /** 子进程 PID（日志与诊断用）。 */
  get pid(): number | undefined {
    return this.child.pid;
  }

  get isClosed(): boolean {
    return this.closed;
  }

  writeLine(line: string): void {
    if (this.closed) {
      throw new AcpWriteError("ACP 进程 stdin 已关闭，无法写入");
    }
    try {
      this.child.stdin.write(`${line}\n`);
    } catch (error) {
      throw new AcpWriteError(
        `ACP stdin 写入失败：${describeError(error)}`,
        error,
      );
    }
  }

  onLine(handler: TransportLineHandler): void {
    this.lineSlot.set(handler);
  }

  onStderr(handler: TransportStderrHandler): void {
    this.stderrSlot.set(handler);
  }

  onExit(handler: TransportExitHandler): void {
    this.exitSlot.set(handler);
    // 退出先于订阅发生时补发（对端可能在 spawn 后立即崩溃）
    if (this.reportedExit !== null) {
      handler(this.reportedExit);
    }
  }

  async close(
    graceMs: number = DEFAULT_CLOSE_GRACE_MS,
  ): Promise<TransportExit> {
    if (this.exitPromise !== null) {
      return this.exitPromise;
    }
    this.exitPromise = this.gracefulExit(graceMs);
    const exit = await this.exitPromise;
    this.closed = true;
    return exit;
  }

  async kill(): Promise<TransportExit> {
    if (this.exitPromise !== null) {
      return this.exitPromise;
    }
    this.exitPromise = this.terminateTree();
    const exit = await this.exitPromise;
    this.closed = true;
    return exit;
  }

  // ----------------------------------------------------------------- 内部

  private wireStreams(): void {
    // stdin 的 EPIPE 是异步 error 事件（子进程死亡后写入触发），同步
    // try/catch 接不住：必须挂监听把它降级为 stderr 旁路诊断，否则
    // Node 以 uncaught exception 崩掉宿主——「agent 崩溃/被杀后上层
    // 仍在写」正是本层设计要稳健处理的场景。
    this.child.stdin.on("error", (error: NodeJS.ErrnoException) => {
      this.stderrSlot.emit(`stdin 写入错误：${describeError(error)}`);
    });

    this.child.stdout.on("data", (chunk: Buffer) => {
      let lines: string[];
      try {
        lines = this.decoder.push(
          new Uint8Array(chunk.buffer, chunk.byteOffset, chunk.byteLength),
        );
      } catch (error) {
        // 行超限：视为对端异常，强杀并退出
        this.stderrSlot.emit(`行分帧错误：${describeError(error)}`);
        void this.kill();
        return;
      }
      for (const line of lines) {
        this.lineSlot.emit(line);
      }
    });

    this.child.stderr.on("data", (chunk: Buffer) => {
      this.stderrSlot.emit(this.stderrDecoder.decode(chunk));
    });

    this.child.on("error", (error) => {
      // spawn 失败（命令不存在）或运行中管道错误：合成退出事件
      this.settleExit({ code: null, signal: null }, error);
    });

    // 子进程已退出时主动关掉父端 stdin 写端：Node 的 'close' 事件要等
    // 全部 stdio 流关闭才派发，而父端不 end() 的话 stdin 永远开着——
    // 对一个死进程写入端毫无用处，却会让 exit/onExit 悬置（实测于
    // 「子进程输出完毕即自然退出」的场景）。
    this.child.on("exit", () => {
      try {
        this.child.stdin.end();
      } catch {
        // stdin 已坏：忽略
      }
    });

    this.child.on("close", (code, signal) => {
      // close（而非 exit）保证 stdio 流已排空；把残留半行吐出
      for (const tail of this.decoder.flush()) {
        this.lineSlot.emit(tail);
      }
      this.settleExit({ code: code ?? null, signal: signal ?? null }, null);
    });
  }

  private async gracefulExit(graceMs: number): Promise<TransportExit> {
    // 对端可能早已退出（exit 事件已消费过）——直接复用终态
    if (this.child.exitCode !== null || this.child.signalCode !== null) {
      this.closed = true;
      return { code: this.child.exitCode, signal: this.child.signalCode };
    }
    // 对端收到 EOF（stdin 关闭）后通常会自行退出；超时升级为强杀。
    const exited = new Promise<TransportExit>((resolve) => {
      this.child.once("close", (code, signal) => {
        resolve({ code: code ?? null, signal: signal ?? null });
      });
    });
    try {
      this.child.stdin.end();
    } catch {
      // stdin 已坏：直接走强杀
    }
    const winner = await Promise.race([
      exited,
      delay(graceMs).then(() => "timeout" as const),
    ]);
    if (winner === "timeout") {
      return this.terminateTree();
    }
    this.closed = true;
    return winner;
  }

  /**
   * 进程树终止。Windows：`taskkill /PID <pid> /T /F`；POSIX：SIGTERM，
   * 5s 后仍存活则 SIGKILL。对齐 Python 参考的 _terminate_process_tree。
   */
  private async terminateTree(): Promise<TransportExit> {
    const child = this.child;
    if (child.exitCode !== null || child.signalCode !== null) {
      this.closed = true;
      return { code: child.exitCode, signal: child.signalCode };
    }
    const pid = child.pid;
    if (pid === undefined) {
      // 从未成功 spawn：error 事件会补 settleExit
      this.closed = true;
      return { code: null, signal: null };
    }
    if (process.platform === "win32") {
      await runTaskkill(pid);
    } else {
      try {
        child.kill("SIGTERM");
      } catch {
        // 已退出：忽略
      }
    }
    const exited = new Promise<TransportExit>((resolve) => {
      child.once("close", (code, signal) => {
        resolve({ code: code ?? null, signal: signal ?? null });
      });
    });
    const winner = await Promise.race([
      exited,
      delay(KILL_GRACE_MS).then(() => "timeout" as const),
    ]);
    if (winner === "timeout") {
      if (process.platform !== "win32") {
        try {
          child.kill("SIGKILL");
        } catch {
          // 忽略：已退出
        }
      }
      // 二次兜底：'exit' 常早于 'close' 派发，直接读终态；两者都缺时
      // 给 'close' 最后一个短窗口，绝不无限等待（close 可能因父端
      // stdio 未关而悬置——onExit 兜底路径会补通知）。
      if (child.exitCode !== null || child.signalCode !== null) {
        this.closed = true;
        return { code: child.exitCode, signal: child.signalCode };
      }
      const finalExit = await Promise.race([
        exited,
        delay(1_000).then(() => "timeout" as const),
      ]);
      this.closed = true;
      return finalExit === "timeout"
        ? { code: child.exitCode, signal: child.signalCode ?? "SIGKILL" }
        : finalExit;
    }
    this.closed = true;
    return winner;
  }

  private settleExit(exit: TransportExit, error: unknown): void {
    if (this.settledExit) {
      return;
    }
    this.settledExit = true;
    this.closed = true;
    this.reportedExit = exit;
    if (error !== null) {
      this.stderrSlot.emit(`进程错误：${describeError(error)}`);
    }
    this.exitSlot.emit(exit);
  }
}

/** Windows 进程树强杀。taskkill 自带等待，失败不抛（进程可能已退出）。 */
function runTaskkill(pid: number): Promise<void> {
  return new Promise((resolve) => {
    const taskkill = spawn("taskkill", ["/PID", String(pid), "/T", "/F"], {
      stdio: "ignore",
      shell: false,
    });
    taskkill.on("error", () => resolve());
    taskkill.on("close", () => resolve());
  });
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
