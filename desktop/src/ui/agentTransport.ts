/**
 * agent 进程 transport 工厂（ui 层组装模块）：按运行时选择进程承载——
 * Tauri webview 走 IPC transport；dev 浏览器（npm run dev:web）走 dev
 * bridge（vite 内嵌插件代为拉起，见 src/dev/bridgeClient.ts）；其余环境
 * （vitest 等）返回 null，如实报告不可用，不伪造连接。
 * 生产构建把 DEV 折叠为 false，bridge 分支成为死代码。
 *
 * 从 realRuntime 提取为独立工厂：协议自检（agentProbe）与真实会话
 * （realRuntime）共用同一套环境判定，防止两处漂移。
 */
import { isTauriEnv } from "../core/host.ts";
import { createTauriStdioTransport } from "../acp/transport/tauriStdioTransport.ts";
import { createBridgeAcpTransport } from "../dev/bridgeClient.ts";
import type { AcpTransport } from "../acp/transport/acpTransport.ts";
import type { AgentLaunch } from "../agents/registry.ts";

/** 按当前运行时创建 agent 进程 transport；环境不支持返回 null。 */
export async function createAgentTransport(
  launch: AgentLaunch,
): Promise<AcpTransport | null> {
  if (isTauriEnv()) {
    return createTauriStdioTransport({
      command: launch.command,
      cwd: launch.cwd ?? undefined,
      extraEnv: launch.extraEnv,
    });
  }
  if (import.meta.env.DEV && !import.meta.env.VITEST) {
    return createBridgeAcpTransport({
      command: launch.command,
      cwd: launch.cwd ?? undefined,
      extraEnv: launch.extraEnv,
    });
  }
  return null;
}
