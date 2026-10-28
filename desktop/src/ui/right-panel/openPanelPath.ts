import { panelService } from "../../core/panelService.ts";
import { pathKey } from "../../core/panelPaths.ts";
import { useWorkbenchUiStore } from "../../stores/workbenchUiStore.ts";
import { useRightPanelStore } from "../../stores/rightPanelStore.ts";

/** 文件点击的项目在调用时捕获，异步 stat 完成后仍须匹配当前项目。 */
export async function openPanelPath(
  project: string,
  path: string,
  line?: number,
): Promise<void> {
  const entry = await panelService.stat(path);
  if (
    pathKey(useWorkbenchUiStore.getState().contextPath ?? "") !==
    pathKey(project)
  )
    throw new Error("项目已切换，请在文件所属项目中重新打开");
  const panel = useRightPanelStore.getState();
  if (entry.directory) panel.openDirectory(project, entry.path);
  else panel.openFile(project, entry.path, line);
}
