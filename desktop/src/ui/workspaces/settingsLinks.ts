/**
 * 设置页的工具路径桥接（组件层组装，store 之间不互相 import）。
 *
 * iCode 路径在 settingsStore 的 Agent 设置中，uv 命令与 aaw 脚本路径在
 * workspaceStore.toolPaths（工作流健康检查 / 状态查询的执行入参）。
 *
 * - useToolPathSettings()：设置页「工具路径」区块的受控读写；
 * - settingsPathsOverride()：一次诊断 / 查询执行的路径覆盖（chrys 取
 *   设置页的值；aaw 脚本未显式配置时从 skills 源目录推导）。
 */
import {
  deriveAawScriptPath,
  type WorkspaceToolPaths,
} from "../../aaw/healthChecks.ts";
import { useSettingsStore } from "../../stores/settingsStore.ts";
import { useWorkspaceStore } from "../../stores/workspaceStore.ts";

/** 组装本次执行的工具路径覆盖（chrys 与 aaw 脚本）。 */
export function settingsPathsOverride(): Partial<WorkspaceToolPaths> {
  const { chrysPath, skillsSourceDir } = useSettingsStore.getState();
  const { toolPaths } = useWorkspaceStore.getState();
  return {
    chrysCommand: chrysPath,
    aawScriptPath:
      toolPaths.aawScriptPath.trim() !== ""
        ? toolPaths.aawScriptPath
        : deriveAawScriptPath(skillsSourceDir),
  };
}

/** 设置页「工具路径」区块的读写面：三路径一处配置。 */
export interface ToolPathSettings {
  readonly chrysPath: string;
  readonly uvCommand: string;
  readonly aawScriptPath: string;
  readonly setChrysPath: (path: string) => void;
  readonly setUvCommand: (command: string) => void;
  readonly setAawScriptPath: (path: string) => void;
}

export function useToolPathSettings(): ToolPathSettings {
  const chrysPath = useSettingsStore((state) => state.chrysPath);
  const setChrysPath = useSettingsStore((state) => state.setChrysPath);
  const uvCommand = useWorkspaceStore((state) => state.toolPaths.uvCommand);
  const aawScriptPath = useWorkspaceStore(
    (state) => state.toolPaths.aawScriptPath,
  );

  return {
    chrysPath,
    uvCommand,
    aawScriptPath,
    setChrysPath,
    setUvCommand: (command) => {
      const store = useWorkspaceStore.getState();
      store.setToolPaths({ ...store.toolPaths, uvCommand: command });
    },
    setAawScriptPath: (path) => {
      const store = useWorkspaceStore.getState();
      store.setToolPaths({ ...store.toolPaths, aawScriptPath: path });
    },
  };
}
