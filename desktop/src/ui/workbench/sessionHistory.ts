/**
 * 历史会话的启动期补充（workbench 组装层）。
 *
 * 左栏树在未连接时读取本地历史：优先会话索引，不可用时扫描元数据（见
 * src/agents/chrysSessions.ts），按项目路径分组后补进 sessionStore 的
 * 各项目缓存。触发时机是「已知项目集合发生变化」——应用启动、以及新添
 * 加项目之后——不需要任何 agent 进程。
 *
 * 三条纪律：
 * - **只补不覆盖**：`session/list` 是已连接项目的权威快照，缓存可能落后
 *   （chrys 对索引缓存有合并节流），因此 store 的 mergeSessionHistory
 *   只写空缺项目；
 * - **路径匹配用归一化串**：索引里存的是 chrys 写入的原始路径，项目列表
 *   里是目录对话框给的串，分隔符 / 大小写都可能不同；
 * - **读不到就是读不到**：两种来源均不可读时不当成「没有会话」对外断言，
 *   也绝不因此清空任何已有缓存。
 */
import { hostRuntime } from "../../core/host.ts";
import {
  normalizeSessionPath,
  readSessionCatalog,
} from "../../agents/chrysSessions.ts";
import { useSessionStore } from "../../stores/sessionStore.ts";
import type { SessionSummary } from "../../stores/sessionStore.ts";
import { useWorkspaceStore } from "../../stores/workspaceStore.ts";

/**
 * 读一次 agent 的会话索引，把各项目的已知历史补进左栏树的数据源。
 * 幂等（已补充过的项目不会再被写），失败静默（树退回既有观感）。
 */
export async function hydrateSessionHistory(): Promise<void> {
  const workspace = useWorkspaceStore.getState();
  const knownPaths = [
    ...workspace.pinnedPaths,
    ...workspace.recentWorkspaces.map((entry) => entry.path),
  ];
  if (knownPaths.length === 0) {
    return;
  }
  const grouped = await readSessionCatalog(hostRuntime);
  if (grouped.size === 0) {
    return;
  }
  const mapping: Record<string, readonly SessionSummary[]> = {};
  for (const path of knownPaths) {
    const known = grouped.get(normalizeSessionPath(path));
    if (known === undefined) {
      continue;
    }
    mapping[path] = known.map((session) => ({
      id: session.id,
      title: session.title,
      updatedAt: session.updatedAt,
    }));
  }
  useSessionStore.getState().mergeSessionHistory(mapping);
}
