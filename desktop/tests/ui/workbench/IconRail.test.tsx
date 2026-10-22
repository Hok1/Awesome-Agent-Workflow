/**
 * 图标窄栏（IconRail）交互测试：
 * - 四个入口齐备：侧边栏开关 / 新建会话 / 设置 / 诊断；
 * - 开关切换 sidebarCollapsed 并持久化（键不变）；
 * - ＋ 新建会话与左栏树段头的 ＋ 是同一动作：展开树列（面板锚定在段头
 *   下方）并打开【+】面板；
 * - 设置 / 诊断：toggleOverlay 语义（再点同页取消）。
 *
 * 布局级行为（收起后树列消失、窄栏常驻）由 workbench.test.tsx 覆盖，
 * 这里用独立渲染收口组件自身语义。
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { IconRail } from "../../../src/ui/workbench/IconRail.tsx";
import { useSessionStore } from "../../../src/stores/sessionStore.ts";
import { useWorkspaceStore } from "../../../src/stores/workspaceStore.ts";
import { useWorkbenchUiStore } from "../../../src/stores/workbenchUiStore.ts";

const PATH = "D:/dev/demo-project";

function resetAll(): void {
  window.localStorage.clear();
  useWorkbenchUiStore.setState({
    treeView: "project-overview",
    contextPath: null,
    overlay: null,
    expandedOverrides: {},
    sidebarCollapsed: false,
    treeViewMode: "projects",
    isAddPanelOpen: false,
  });
  useWorkspaceStore.setState({ recentWorkspaces: [], favoritePaths: [] });
  useWorkspaceStore.getState().closeWorkspace();
  useWorkspaceStore.getState().clearSelection();
  useSessionStore.setState({ sessionsByPath: {} });
}

beforeEach(() => {
  resetAll();
});

describe("IconRail 图标窄栏", () => {
  it("四个入口齐备（开关 / 新建会话 / 设置 / 诊断）", () => {
    render(<IconRail />);
    const rail = screen.getByLabelText("主导航");
    expect(rail).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "展开/收起侧边栏" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "新建会话" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "设置" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "诊断" })).toBeInTheDocument();
  });

  it("开关切换 sidebarCollapsed 并按原键持久化", async () => {
    render(<IconRail />);
    const toggle = screen.getByRole("button", { name: "展开/收起侧边栏" });

    await userEvent.click(toggle);
    expect(useWorkbenchUiStore.getState().sidebarCollapsed).toBe(true);
    expect(
      window.localStorage.getItem("aaw-desktop/layout/sidebar-collapsed"),
    ).toBe("1");

    await userEvent.click(toggle);
    expect(useWorkbenchUiStore.getState().sidebarCollapsed).toBe(false);
    expect(
      window.localStorage.getItem("aaw-desktop/layout/sidebar-collapsed"),
    ).toBe("0");
  });

  it("新建会话：与树段头＋同一动作——展开树列并打开【+】面板（不在导航栏里预选项目）", async () => {
    useWorkbenchUiStore.setState({ contextPath: PATH });
    render(<IconRail />);
    await userEvent.click(screen.getByRole("button", { name: "新建会话" }));

    const ui = useWorkbenchUiStore.getState();
    // 与左栏 ＋ 的落点完全一致：开面板，由用户在面板里选项目
    expect(ui.isAddPanelOpen).toBe(true);
    expect(ui.treeView).toBe("project-overview");
    expect(ui.contextPath).toBe(PATH);
  });

  it("新建会话：侧边栏收起时先展开（面板锚定在树段头下方）", async () => {
    useWorkbenchUiStore.setState({ sidebarCollapsed: true });
    render(<IconRail />);
    await userEvent.click(screen.getByRole("button", { name: "新建会话" }));

    const ui = useWorkbenchUiStore.getState();
    expect(ui.sidebarCollapsed).toBe(false);
    expect(ui.isAddPanelOpen).toBe(true);
  });

  it("设置 / 诊断：toggleOverlay 语义，再点同页取消覆盖", async () => {
    render(<IconRail />);
    const settings = screen.getByRole("button", { name: "设置" });
    await userEvent.click(settings);
    expect(useWorkbenchUiStore.getState().overlay).toBe("settings");
    expect(settings).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(settings);
    expect(useWorkbenchUiStore.getState().overlay).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: "诊断" }));
    expect(useWorkbenchUiStore.getState().overlay).toBe("diagnostics");
  });
});
