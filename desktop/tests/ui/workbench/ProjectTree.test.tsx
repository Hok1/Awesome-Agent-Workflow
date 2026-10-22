/**
 * 项目树（左栏）冷启动空态测试：无任何已知项目时树体给一行添加指引，
 * 段头【+】入口仍在（添加项目的实际落点）。树行交互与徽标见 workbench
 * 级测试（workbench.test.tsx 经 App 集成渲染）。
 */
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { ProjectTree } from "../../../src/ui/workbench/ProjectTree.tsx";
import { useSessionStore } from "../../../src/stores/sessionStore.ts";
import { useWorkspaceStore } from "../../../src/stores/workspaceStore.ts";
import { useWorkbenchUiStore } from "../../../src/stores/workbenchUiStore.ts";

beforeEach(() => {
  window.localStorage.clear();
  useWorkspaceStore.setState({ recentWorkspaces: [], favoritePaths: [] });
  useSessionStore.setState({ sessionsByPath: {} });
  useWorkbenchUiStore.setState({ treeViewMode: "projects" });
});

describe("ProjectTree 冷启动空态", () => {
  it("无任何项目时树体给一行添加指引，段头【+】入口仍在", () => {
    render(<ProjectTree />);
    expect(screen.getByText("还没有项目，点右上 ＋ 添加")).toBeInTheDocument();
    // 添加项目的实际入口（树段头【+】面板触发按钮）仍可用
    expect(
      screen.getByRole("button", { name: "新建会话或添加项目" }),
    ).toBeEnabled();
    // 空态下不再渲染空的分组
    expect(screen.queryByLabelText("收藏")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("最近打开")).not.toBeInTheDocument();
  });
});
