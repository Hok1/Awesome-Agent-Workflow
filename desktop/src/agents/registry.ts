/**
 * Agent 适配注册表（src/agents）：「协议」与「具体 agent」的解耦点。
 *
 * 一个 `AgentAdapter` 回答四件事：这是谁（id / displayName）、怎么启动
 * （buildLaunch 产出 argv 与环境）、会话建立时的初始化参数、有什么方言
 * （createDialect 注入私有通知翻译与私有反向请求处理）。启动描述交给
 * transport 工厂执行（Node 子进程 / Tauri IPC），本层不 spawn 进程、
 * 不依赖 UI 与 store。
 *
 * 扩展约束（docs/architecture.md「扩展第二种 agent」）：接入新 agent =
 * 在 `agentAdapters` 加一个注册项；`src/acp` 协议层与 `src/ui` 一行不改。
 * 讲标准 ACP 的 agent 到此即完成；带私有扩展的 agent 在注册项里提供
 * `createDialect`（协议层的 `AcpDialect` 挂接点），私有消息的解析留在
 * 本层，同样不动协议层。
 */

import type { AcpDialect } from "../acp/session.ts";

import type { ChrysRequestInputResult } from "../acp/types.ts";
import { createChrysDialect, type QuestionResponder } from "./chrysDialect.ts";

/** 一次 agent 启动的完整描述（transport 工厂的入参形状）。 */
export interface AgentLaunch {
  /** 完整 argv，如 ["C:/path/chrys.exe", "acp"]。 */
  readonly command: readonly string[];
  /** 工作目录；null 表示继承宿主。 */
  readonly cwd: string | null;
  /** 追加的环境变量（与宿主环境合并）。 */
  readonly extraEnv: Readonly<Record<string, string>>;
}

/** buildLaunch 的入参。 */
export interface AgentLaunchContext {
  /** 会话工作区目录（chrys 经 session/new 的 cwd 参数使用，启动目录可选）。 */
  readonly workspacePath: string | null;
  /** agent 可执行文件路径；缺省回退 PATH 查找（command 名语义）。 */
  readonly executablePath?: string;
}

/** 组装层传给 createDialect 的运行时回调（UI 挂起 → 用户决策 → 回传）。 */
export interface AgentDialectHooks {
  /** 结构化提问回调（chrys 的 _chrys/request_input）。 */
  readonly onQuestion?: QuestionResponder;
}

export interface AgentAdapter {
  /** 稳定标识（日志与设置引用）。 */
  readonly id: string;
  /** 展示名（界面与日志）。 */
  readonly displayName: string;
  /** 产出启动描述。 */
  buildLaunch(context: AgentLaunchContext): AgentLaunch;
  /** initialize 握手的客户端标识（AcpSession clientInfo）。 */
  readonly clientInfo: { readonly name: string; readonly version?: string };
  /**
   * 创建方言挂接（私有通知翻译 + 私有反向请求处理，注入 AcpSession）。
   * 纯标准 ACP agent 可省略——协议层对未知消息已有兜底透传。
   */
  readonly createDialect?: (hooks: AgentDialectHooks) => AcpDialect;
  /** 方言注记（扩展通知 / 反向请求名等，供诊断与人读）。 */
  readonly notes: readonly string[];
}

/**
 * chrys 适配项。权威定义：D:/dev/workspace-ai/chrys/src/chrys/app/acp/
 * （server.py 的 initialize 能力声明、_request_permission 与
 * _chrys/request_input 结构化提问、session_manager.py、content.py）。
 */
export const chrysAgentAdapter: AgentAdapter = {
  id: "chrys",
  displayName: "chrys",
  buildLaunch(context) {
    const program = context.executablePath?.trim() || "chrys";
    return {
      command: [program, "acp"],
      cwd: context.workspacePath,
      extraEnv: {},
    };
  },
  clientInfo: { name: "aaw-desktop", version: "0.1.0" },
  createDialect(hooks) {
    return createChrysDialect({ onQuestion: hooks.onQuestion });
  },
  notes: [
    "扩展通知：_chrys/runtime_update、_chrys/usage_update、_chrys/error、_chrys/warning",
    "反向请求：session/request_permission（allow_once / reject_once）、_chrys/request_input（结构化提问）",
    "能力（server.py）：loadSession、promptCapabilities.embeddedContext、sessionCapabilities.{close,list,additionalDirectories}",
  ],
};

/** 注册表：接入第二种 agent = 在此追加一项。 */
export const agentAdapters: readonly AgentAdapter[] = [chrysAgentAdapter];

/**
 * 当前默认 agent 的 id。界面文案里需要指代「这一侧」时用它取名，不要写
 * 死字面量——接入第二个 agent 时，散落的硬编码就得逐个找出来。
 */
export const DEFAULT_AGENT_ID = "chrys";

/** 默认 agent 的展示名（注册表缺失时回落 id，绝不返回空串）。 */
export function defaultAgentLabel(): string {
  return findAgentAdapter(DEFAULT_AGENT_ID)?.displayName ?? DEFAULT_AGENT_ID;
}

/** 按 id 查适配项；未知 id 返回 null（调用方如实报错，不静默替换）。 */
export function findAgentAdapter(id: string): AgentAdapter | null {
  return agentAdapters.find((adapter) => adapter.id === id) ?? null;
}

/** 类型再导出：组装层构造 dialect 回调时引用（避免深入 import 链）。 */
export type { QuestionResponder, ChrysRequestInputResult };
