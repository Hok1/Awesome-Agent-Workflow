/**
 * ACP transport 的 Tauri IPC 实现（webview 前端 ↔ Rust 宿主）。
 *
 * 与 `nodeStdioTransport`（Node 子进程直连）满足同一 `AcpTransport` 接口，
 * 协议层（connection / session）对运行时无感。Rust 侧薄壳命令见
 * `src-tauri/src/acp_process.rs`：
 *
 * - spawn → `acp_spawn`（句柄 + PID）；
 * - writeLine → `acp_stdin_write`（Rust 补 `\n` 并 flush）；
 * - 行/块/退出 → `acp://stdout` / `acp://stderr` / `acp://exit` 事件
 *   （payload 携带句柄，本类按句柄过滤）；
 * - close → `acp_stdin_close`（对端收到 EOF）→ 等 `acp://exit` → 超时升级
 *   kill（与 Node 实现的 gracefulExit 同一编排）；
 * - kill → `acp_kill_tree`（Windows `taskkill /T /F`，对齐 Python 参考的
 *   `_terminate_process_tree`）。
 *
 * 与 Node 实现的一处固有差异：IPC 写入是异步的，`writeLine` 同步签名下
 * 无法同步报告管道断裂。策略：句柄已知失效（已关闭 / 上次写入失败）时
 * 同步抛 `AcpWriteError`；异步失败经 onStderr 旁路报告——进程死后
 * `acp://exit` 随即到达，连接层的挂起请求会被 `AcpClosedError` 唤醒，
 * 行为与 Node 实现等价。
 *
 * 只能在 Tauri WebView 内创建（`isTauriEnv()`）；浏览器 / vitest 下工厂
 * Promise 以可读错误 reject，测试用 mock 的 invoke / listen 覆盖逻辑。
 */

import { invoke } from "@tauri-apps/api/core";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";

import { AcpWriteError } from "../errors.ts";
import {
  HandlerSlot,
  type AcpTransport,
  type TransportExit,
  type TransportExitHandler,
  type TransportLineHandler,
  type TransportStderrHandler,
} from "./acpTransport.ts";

/** `acp_spawn` 的返回（acp_process.rs AcpSpawnResult）。 */
interface AcpSpawnResultWire {
  readonly handle?: unknown;
  readonly pid?: unknown;
}

/** `acp_kill_tree` 的返回（acp_process.rs AcpExitInfo）。 */
interface AcpExitInfoWire {
  readonly code?: unknown;
  readonly signal?: unknown;
}

/** stdout / stderr 事件载荷（acp_process.rs AcpIoEvent）。 */
interface AcpIoEventWire {
  readonly handle?: unknown;
  readonly data?: unknown;
}

/** 退出事件载荷（acp_process.rs AcpExitEvent）。 */
interface AcpExitEventWire {
  readonly handle?: unknown;
  readonly code?: unknown;
  readonly signal?: unknown;
}

/** 优雅关闭（关 stdin 后）等待对端自退的默认宽限（对齐 Node 实现）。 */
const DEFAULT_CLOSE_GRACE_MS = 5_000;

export interface TauriStdioSpawnOptions {
  /** 完整 argv，如 ["C:/path/chrys.exe", "acp"]。 */
  readonly command: readonly string[];
  /** 工作目录。 */
  readonly cwd?: string;
  /** 注入的环境变量（与当前环境合并）。 */
  readonly extraEnv?: Readonly<Record<string, string>>;
}

/** Rust 事件名与句柄的绑定（三个事件共用 handle 过滤）。 */
const EVENT_STDOUT = "acp://stdout";
const EVENT_STDERR = "acp://stderr";
const EVENT_EXIT = "acp://exit";

function isHandle(payload: unknown, handle: number): boolean {
  if (typeof payload !== "object" || payload === null) {
    return false;
  }
  return (payload as { readonly handle?: unknown }).handle === handle;
}

/**
 * Tauri IPC transport。构造是异步的（spawn invoke + 事件订阅），请用
 * `createTauriStdioTransport` 工厂；构造成功即代表进程已在运行。
 */
export class TauriStdioTransport implements AcpTransport {
  private readonly handle: number;
  private unlisteners: UnlistenFn[] = [];
  private readonly lineSlot = new HandlerSlot<TransportLineHandler>();
  private readonly stderrSlot = new HandlerSlot<TransportStderrHandler>();
  private readonly exitSlot = new HandlerSlot<TransportExitHandler>();

  private closed = false;
  private writeBroken = false;
  private exitPromise: Promise<TransportExit> | null = null;
  private reportedExit: TransportExit | null = null;
  private exitWaiterResolve: ((exit: TransportExit) => void) | null = null;
  private readonly exitWaiter: Promise<TransportExit>;

  /** 请用 createTauriStdioTransport 工厂创建（spawn + 事件订阅一体）。 */
  constructor(handle: number) {
    this.handle = handle;
    this.exitWaiter = new Promise<TransportExit>((resolve) => {
      this.exitWaiterResolve = resolve;
    });
  }

  /** 工厂在事件订阅成功后回填退订函数（订阅晚于构造完成）。 */
  bindUnlisteners(unlisteners: readonly UnlistenFn[]): void {
    this.unlisteners = [...unlisteners];
  }

  /** agent 进程句柄与 PID（日志与诊断用）。 */
  get processHandle(): number {
    return this.handle;
  }

  get isClosed(): boolean {
    return this.closed;
  }

  writeLine(line: string): void {
    if (this.closed) {
      throw new AcpWriteError("ACP 进程已退出，无法写入");
    }
    if (this.writeBroken) {
      throw new AcpWriteError("ACP stdin 已断裂（上次写入失败），无法写入");
    }
    // IPC 写入异步完成：失败经 stderr 旁路报告，下次调用同步抛错
    void invoke("acp_stdin_write", { handle: this.handle, line }).catch(
      (error: unknown) => {
        if (this.closed) {
          return; // 进程已退出，exit 事件才是权威信号
        }
        this.writeBroken = true;
        const reason = error instanceof Error ? error.message : String(error);
        this.stderrSlot.emit(`stdin 写入失败：${reason}`);
      },
    );
  }

  onLine(handler: TransportLineHandler): void {
    this.lineSlot.set(handler);
  }

  onStderr(handler: TransportStderrHandler): void {
    this.stderrSlot.set(handler);
  }

  onExit(handler: TransportExitHandler): void {
    this.exitSlot.set(handler);
    // 退出先于订阅发生时补发（对端可能在订阅前崩溃）
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
    this.exitPromise = this.killTree();
    const exit = await this.exitPromise;
    this.closed = true;
    return exit;
  }

  // ----------------------------------------------------------------- 内部

  /** 关 stdin → 等对端自退 → 超时升级强杀（对齐 Node 的 gracefulExit）。 */
  private async gracefulExit(graceMs: number): Promise<TransportExit> {
    try {
      await invoke("acp_stdin_close", { handle: this.handle });
    } catch {
      // 进程可能已退出：继续等 exit 事件，超时走强杀
    }
    const winner = await Promise.race([
      this.exitWaiter,
      delay(graceMs).then(() => "timeout" as const),
    ]);
    if (winner === "timeout") {
      return this.killTree();
    }
    return winner;
  }

  /** 调 Rust 杀树命令并收口。 */
  private async killTree(): Promise<TransportExit> {
    let wire: AcpExitInfoWire;
    try {
      wire = await invoke<AcpExitInfoWire>("acp_kill_tree", {
        handle: this.handle,
      });
    } catch {
      // 句柄已不存在等极端情况：以已收到的退出事件为准
      const exit = await Promise.race([
        this.exitWaiter,
        delay(1_000).then(() => null),
      ]);
      return exit ?? { code: null, signal: "SIGKILL" };
    }
    return {
      code: typeof wire.code === "number" ? wire.code : null,
      signal: typeof wire.signal === "string" ? wire.signal : null,
    };
  }

  /** 事件回调（工厂里绑定）：分发到本句柄的三个 slot。 */
  handleStdoutEvent(payload: unknown): void {
    if (this.closed || !isHandle(payload, this.handle)) {
      return;
    }
    const data = (payload as AcpIoEventWire).data;
    if (typeof data === "string") {
      this.lineSlot.emit(data);
    }
  }

  handleStderrEvent(payload: unknown): void {
    if (!isHandle(payload, this.handle)) {
      return;
    }
    const data = (payload as AcpIoEventWire).data;
    if (typeof data === "string") {
      this.stderrSlot.emit(data);
    }
  }

  handleExitEvent(payload: unknown): void {
    if (!isHandle(payload, this.handle)) {
      return;
    }
    const wire = payload as AcpExitEventWire;
    const exit: TransportExit = {
      code: typeof wire.code === "number" ? wire.code : null,
      signal: typeof wire.signal === "string" ? wire.signal : null,
    };
    if (this.reportedExit !== null) {
      return; // 幂等：退出至多报告一次
    }
    this.reportedExit = exit;
    this.closed = true;
    this.exitWaiterResolve?.(exit);
    this.exitSlot.emit(exit);
  }

  /**
   * 释放事件订阅并通知 Rust 侧删除进程表项（close/kill 完成后可调用；
   * 构造失败时由工厂调用）。表项释放是幂等的（acp_release），失败仅
   * 意味着表项已不存在，无需处理。
   */
  dispose(): void {
    for (const unlisten of this.unlisteners) {
      unlisten();
    }
    // fire-and-forget：释放幂等，失败仅意味着表项已不存在
    void Promise.resolve(invoke("acp_release", { handle: this.handle })).catch(
      () => {
        // 句柄不存在（进程退出清理路径）等：无需处理
      },
    );
  }
}

/**
 * 创建 Tauri IPC transport：spawn 进程、订阅三个事件。
 * 非 Tauri 环境或 spawn 失败时 reject（错误信息可直接展示）。
 */
export async function createTauriStdioTransport(
  options: TauriStdioSpawnOptions,
): Promise<TauriStdioTransport> {
  const [program, ...args] = options.command;
  if (typeof program !== "string" || program.length === 0) {
    throw new Error("TauriStdioTransport：command 不能为空");
  }
  const spawnWire = await invoke<AcpSpawnResultWire>("acp_spawn", {
    program,
    args,
    cwd: options.cwd ?? null,
    extraEnv: options.extraEnv ?? null,
  });
  if (typeof spawnWire.handle !== "number") {
    throw new Error("acp_spawn 返回形状不合法（缺少 handle）");
  }
  const transport = new TauriStdioTransport(spawnWire.handle);
  // 事件订阅失败（非 Tauri 环境等）：杀掉已 spawn 的进程再抛错
  try {
    const unlisteners = await Promise.all([
      listen<AcpIoEventWire>(EVENT_STDOUT, (event) => {
        transport.handleStdoutEvent(event.payload);
      }),
      listen<AcpIoEventWire>(EVENT_STDERR, (event) => {
        transport.handleStderrEvent(event.payload);
      }),
      listen<AcpExitEventWire>(EVENT_EXIT, (event) => {
        transport.handleExitEvent(event.payload);
      }),
    ]);
    transport.bindUnlisteners(unlisteners);
  } catch (error) {
    try {
      await invoke("acp_kill_tree", { handle: spawnWire.handle });
    } catch {
      // 清理失败不掩盖原始错误
    }
    throw new Error("订阅 ACP 进程事件失败", { cause: error });
  }
  return transport;
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}
