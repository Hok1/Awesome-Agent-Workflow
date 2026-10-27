/** 设置变更经真实 loader/CLI/store 通路更新查询；宿主进程用替身。 */
import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const runner = vi.hoisted(() => ({ run: vi.fn(), exists: vi.fn() }));
vi.mock("../../src/aaw/tauriProcessRunner.ts", () => ({
  defaultProcessRunner: runner,
}));
import { AawStatusLoaderBinding } from "../../src/ui/AawStatusLoaderBinding.tsx";
import { useAawStatusStore } from "../../src/stores/aawStatusStore.ts";
import { useWorkspaceStore } from "../../src/stores/workspaceStore.ts";
import { useSettingsStore } from "../../src/stores/settingsStore.ts";
import { useWorkbenchUiStore } from "../../src/stores/workbenchUiStore.ts";

beforeEach(() => {
  runner.run.mockReset().mockImplementation(() =>
    Promise.resolve({
      ok: true,
      code: 0,
      stdout: '{"ok":true,"srs":[]}',
      stderr: "",
      durationMs: 1,
    }),
  );
  runner.exists.mockReset().mockResolvedValue(true);
  useAawStatusStore.getState().reset();
  useWorkspaceStore.getState().setToolPaths({
    chrysCommand: "icode",
    uvCommand: "uv",
    aawScriptPath: "D:/tools/aaw.py",
  });
  useSettingsStore.getState().setSkillsSourceDir("D:/source/skills");
  useWorkbenchUiStore.setState({ contextPath: "D:/projects/one" });
});
afterEach(() => {
  cleanup();
  useAawStatusStore.getState().reset();
});

describe("工作流数据源配置", () => {
  it("复用已选工具，修改工具或项目立即查询，无需重启", async () => {
    render(<AawStatusLoaderBinding />);
    await waitFor(() => expect(runner.run).toHaveBeenCalledTimes(1));
    expect(runner.run).toHaveBeenLastCalledWith(
      expect.objectContaining({
        cwd: "D:/projects/one",
        command: ["uv", "run", "D:/tools/aaw.py", "status", "--json"],
      }),
    );
    act(() =>
      useWorkspaceStore.getState().setToolPaths({
        chrysCommand: "icode",
        uvCommand: "D:/bin/uv.exe",
        aawScriptPath: "D:/other/aaw.py",
      }),
    );
    await waitFor(() => expect(runner.run).toHaveBeenCalledTimes(2));
    expect(runner.run).toHaveBeenLastCalledWith(
      expect.objectContaining({
        cwd: "D:/projects/one",
        command: [
          "D:/bin/uv.exe",
          "run",
          "D:/other/aaw.py",
          "status",
          "--json",
        ],
      }),
    );
    act(() => useWorkbenchUiStore.setState({ contextPath: "D:/projects/two" }));
    await waitFor(() => expect(runner.run).toHaveBeenCalledTimes(3));
    expect(runner.run).toHaveBeenLastCalledWith(
      expect.objectContaining({ cwd: "D:/projects/two" }),
    );
  });

  it("显式脚本优先；未选脚本时只从用户配置的 skills 目录推导", async () => {
    render(<AawStatusLoaderBinding />);
    await waitFor(() => expect(runner.run).toHaveBeenCalledTimes(1));
    act(() => useSettingsStore.getState().setSkillsSourceDir("D:/new/skills"));
    expect(runner.run).toHaveBeenCalledTimes(1);
    act(() =>
      useWorkspaceStore.getState().setToolPaths({
        chrysCommand: "icode",
        uvCommand: "uv",
        aawScriptPath: "",
      }),
    );
    await waitFor(() => expect(runner.run).toHaveBeenCalledTimes(2));
    expect(runner.run).toHaveBeenLastCalledWith(
      expect.objectContaining({
        command: [
          "uv",
          "run",
          "D:/new/skills/aaw-workflow/scripts/aaw.py",
          "status",
          "--json",
        ],
      }),
    );
    act(() =>
      useSettingsStore.getState().setSkillsSourceDir("D:/third/skills"),
    );
    await waitFor(() => expect(runner.run).toHaveBeenCalledTimes(3));
    expect(runner.exists).toHaveBeenLastCalledWith(
      "D:/third/skills/aaw-workflow/scripts/aaw.py",
    );
  });

  it("未配置与工具不存在分别提示，修好配置后立即恢复", async () => {
    useWorkspaceStore.getState().setToolPaths({
      chrysCommand: "icode",
      uvCommand: "uv",
      aawScriptPath: "",
    });
    useSettingsStore.getState().resetToDefaults();
    expect(useSettingsStore.getState().skillsSourceDir).toBe("");
    render(<AawStatusLoaderBinding />);
    await waitFor(() =>
      expect(useAawStatusStore.getState().lastError).toContain(
        "尚未配置 aaw 脚本路径",
      ),
    );
    expect(runner.run).not.toHaveBeenCalled();
    runner.exists.mockResolvedValue(false);
    act(() =>
      useWorkspaceStore.getState().setToolPaths({
        chrysCommand: "icode",
        uvCommand: "uv",
        aawScriptPath: "D:/missing/aaw.py",
      }),
    );
    await waitFor(() =>
      expect(useAawStatusStore.getState().lastError).toContain(
        "D:/missing/aaw.py",
      ),
    );
    expect(runner.run).not.toHaveBeenCalled();
    runner.exists.mockResolvedValue(true);
    act(() =>
      useWorkspaceStore.getState().setToolPaths({
        chrysCommand: "icode",
        uvCommand: "uv",
        aawScriptPath: "D:/valid/aaw.py",
      }),
    );
    await waitFor(() =>
      expect(useAawStatusStore.getState().lastRefreshedAt).not.toBeNull(),
    );
    expect(useAawStatusStore.getState().lastError).toBeNull();
  });
});
