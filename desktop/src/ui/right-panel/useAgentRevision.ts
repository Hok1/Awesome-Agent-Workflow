import { useEffect, useState } from "react";
import { insidePath } from "../../core/panelPaths.ts";
import { useSessionStore } from "../../stores/sessionStore.ts";
import { useWorkspaceStore } from "../../stores/workspaceStore.ts";

/** 工具完成和轮次结束补一次刷新；流式文本不会使文件查询反复失效。 */
export function useAgentRevision(project: string, enabled = true): number {
  const activePath = useWorkspaceStore((state) => state.activePath);
  const marker = useSessionStore((state) => {
    const completed = state.items.reduce(
      (count, item) =>
        count +
        (item.kind === "tool" &&
        (item.status === "completed" || item.status === "failed")
          ? 1
          : 0),
      0,
    );
    return `${state.activeSessionId}:${state.isAgentRunning}:${completed}`;
  });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!enabled || !activePath || !insidePath(activePath, project)) return;
    const timer = setTimeout(() => setRevision((old) => old + 1), 400);
    return () => clearTimeout(timer);
  }, [marker, activePath, project, enabled]);
  return revision;
}
