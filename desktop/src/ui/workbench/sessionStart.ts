/**
 * 「新建会话」与「打开会话」的共享入口（workbench 组装层）。
 *
 * 会话是骨架，AAW 是挂在骨架上的增强：新建会话的落点是一条**空对话**
 * ——直接和 agent 说话，不要求先声明 SR / AR / dev 入口、先填变量、先过
 * prompt 预览。想看 AAW 的引导流程时，再从会话内或【+】面板显式发起
 * （见 wizardSubmit）。
 *
 * 两个动词必须分开，因为它们的结果不同：
 * - `startNewSession`：**新建**。跳过历史恢复（forceNew），落一条空对话；
 * - `openSessionFromEntry`（sessionEntry）：**打开**指定历史会话。
 *
 * 从前只有一个动词（连上后自动恢复「最近一个」），于是树上的「＋ 新会话」
 * 在项目有历史时实际打开的是旧对话——标签在说谎。现在按语义拆开：想继续
 * 上次的对话就点树上那条会话行，点「＋ 新会话」就得到一条新的。
 *
 * 流程：选中项目 → 未连接则先建立连接（等待完成）→ 内容区切到会话视图。
 *
 * 连接失败时不硬切会话（空会话比不上去修路径），改成落在项目总览：
 * 那里有失败横幅与「去设置工具路径」，用户能直接看到原因并动手改。
 */
import { useSessionStore } from "../../stores/sessionStore.ts";
import { useWorkspaceStore } from "../../stores/workspaceStore.ts";
import { useWorkbenchUiStore } from "../../stores/workbenchUiStore.ts";
import { openRealWorkspace } from "../realRuntime.ts";

/** 结构化结果：失败时 reason 直接面向用户展示。 */
export type StartSessionResult = { ok: true } | { ok: false; reason: string };

/**
 * 在指定项目里新建一条会话（空对话，可直接发送第一条消息）。
 * 失败（连接建立不起来）返回 ok=false 与用户可读原因，调用方负责展示。
 */
export async function startNewSession(
  path: string,
): Promise<StartSessionResult> {
  const workspace = useWorkspaceStore.getState();
  workspace.selectWorkspace(path);
  if (workspace.activePath !== path) {
    // forceNew：本条入口的语义是「新建」，不能落进上次那个对话
    await openRealWorkspace(path, { forceNew: true });
    useWorkspaceStore.getState().openWorkspace(path);
    if (!useSessionStore.getState().isBound) {
      const error = useWorkspaceStore.getState().lastConnectError;
      const detail =
        error !== null && error.path === path ? `：${error.message}` : "";
      // 落在总览：失败横幅与「去设置工具路径」都在那儿，原因看得见
      useWorkbenchUiStore.getState().openProjectOverview(path);
      return {
        ok: false,
        reason: `连接 agent 失败${detail || "，请在设置中检查 agent 可执行路径"}`,
      };
    }
  } else {
    // 项目已连接：当前运行时可能正停在某个历史会话上，新建要另开一条
    await openRealWorkspace(path, { forceNew: true });
  }
  useWorkbenchUiStore.getState().openSessionView(path);
  return { ok: true };
}
