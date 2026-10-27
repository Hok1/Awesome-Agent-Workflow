/** 工作流查询复用工具设置，以当前项目为工作目录；配置变化立即重绑。 */
import { useEffect } from "react";
import { createCliAawStatusLoader } from "../aaw/statusLoader.ts";
import { deriveAawScriptPath } from "../aaw/healthChecks.ts";
import { defaultProcessRunner } from "../aaw/tauriProcessRunner.ts";
import { useAawStatusStore } from "../stores/aawStatusStore.ts";
import { useWorkspaceStore } from "../stores/workspaceStore.ts";
import { useSettingsStore } from "../stores/settingsStore.ts";
import { useWorkbenchUiStore } from "../stores/workbenchUiStore.ts";

export function AawStatusLoaderBinding() {
  const contextPath = useWorkbenchUiStore((state) => state.contextPath);
  const uvCommand = useWorkspaceStore((state) => state.toolPaths.uvCommand);
  const configuredScript = useWorkspaceStore(
    (state) => state.toolPaths.aawScriptPath,
  );
  const skillsSourceDir = useSettingsStore((state) => state.skillsSourceDir);
  const scriptPath =
    configuredScript.trim() || deriveAawScriptPath(skillsSourceDir);

  useEffect(() => {
    const store = useAawStatusStore.getState();
    if (contextPath === null) {
      store.bindLoader(null, null);
      return;
    }
    store.bindLoader(
      createCliAawStatusLoader({
        workspacePath: contextPath,
        uvCommand,
        aawScriptPath: scriptPath,
        runner: defaultProcessRunner,
      }),
      contextPath,
    );
    void store.refresh();
    return () => {
      // 同项目改配置保留上次成功快照；切项目由下一次绑定清空。
      useAawStatusStore.getState().bindLoader(null, contextPath);
    };
  }, [contextPath, uvCommand, scriptPath]);
  return null;
}
