/**
 * 「点会话自动重连」的共享入口（workbench 组装层）：
 * 项目树与会话视角（跨项目最近会话列表）共用同一条打开路径——
 * 目标项目未连接时先 selectWorkspace + openRealWorkspace 建立连接
 * （等待完成），连接落地 activePath 后再 switchRealSession 切入目标
 * 会话；切换成功才聚焦该会话并把内容区切到会话视图，失败保留当前
 * 视图不聚焦。
 *
 * 另含会话视角的数据派生：把各项目的会话列表缓存（sessionsByPath）
 * 拍平为跨项目的「最近活跃会话」条目，按 updatedAt 降序（缺失时间
 * 视为最旧，排在末尾）。
 */
import { useSessionStore } from "../../stores/sessionStore.ts";
import type { SessionSummary } from "../../stores/sessionStore.ts";
import { useWorkspaceStore } from "../../stores/workspaceStore.ts";
import { useWorkbenchUiStore } from "../../stores/workbenchUiStore.ts";
import { openRealWorkspace, switchRealSession } from "../realRuntime.ts";

/** 拍平后的一条最近会话：所属项目路径 + 会话摘要。 */
export interface SessionListEntry {
  readonly path: string;
  readonly session: SessionSummary;
}

/** 条目的排序时间戳：缺失或非法时间视为最旧（-∞，排末尾）。 */
function rankOf(updatedAt: string | null): number {
  if (updatedAt === null) {
    return Number.NEGATIVE_INFINITY;
  }
  const time = Date.parse(updatedAt);
  return Number.isNaN(time) ? Number.NEGATIVE_INFINITY : time;
}

/**
 * 把 sessionsByPath 拍平为跨项目的会话条目，按 updatedAt 降序。
 * 同一会话（路径 + id 相同）只保留一条。
 */
export function flattenRecentSessions(
  sessionsByPath: Readonly<Record<string, readonly SessionSummary[]>>,
): readonly SessionListEntry[] {
  const seen = new Set<string>();
  const entries: SessionListEntry[] = [];
  for (const [path, sessions] of Object.entries(sessionsByPath)) {
    for (const session of sessions) {
      const key = `${path}\u0000${session.id}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      entries.push({ path, session });
    }
  }
  return entries.sort(
    (a, b) => rankOf(b.session.updatedAt) - rankOf(a.session.updatedAt),
  );
}

/**
 * 打开一个历史会话（项目树 / 会话视角共用的唯一入口）：
 * 项目未连接先自动建立连接（等待完成），再切换到目标会话；
 * 切换成功才聚焦并切到会话视图（失败保留当前视图）。
 */
export async function openSessionFromEntry(
  path: string,
  sessionId: string,
): Promise<void> {
  const workspace = useWorkspaceStore.getState();
  if (workspace.activePath !== path) {
    workspace.selectWorkspace(path);
    await openRealWorkspace(path);
    // 连接建立后再落 activePath（RealSessionRuntime 对同路径幂等）
    useWorkspaceStore.getState().openWorkspace(path);
  }
  if (await switchRealSession(sessionId)) {
    useSessionStore.getState().openSession(sessionId);
    useWorkbenchUiStore.getState().openSessionView(path);
  }
}
