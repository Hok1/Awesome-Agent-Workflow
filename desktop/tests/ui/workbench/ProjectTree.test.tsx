/**
 * 项目树（左栏）测试：冷启动空态（无任何已知项目时给一行添加指引）；
 * 会话子节点分页呈现（默认最近 5 条 + 「加载更多」逐页纳新）。树行
 * 交互与徽标见 workbench 级测试（workbench.test.tsx 经 App 集成渲染）。
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { ProjectTree } from "../../../src/ui/workbench/ProjectTree.tsx";
import { useSessionStore } from "../../../src/stores/sessionStore.ts";
import { useWorkspaceStore } from "../../../src/stores/workspaceStore.ts";
import { useWorkbenchUiStore } from "../../../src/stores/workbenchUiStore.ts";

const PATH = "D:/dev/pager";

beforeEach(() => {
  window.localStorage.clear();
  useWorkspaceStore.setState({ recentWorkspaces: [], favoritePaths: [] });
  useSessionStore.setState({ sessionsByPath: {} });
  useWorkbenchUiStore.setState({ treeViewMode: "projects", sessionListLimits: {} });
});

describe("ProjectTree 冷启动空态", () => {
  it("无任何项目时分组头恒在（含段头【+】），树体给一行添加指引", () => {
    render(<ProjectTree />);
    expect(
      screen.getByText("还没有项目，点分组标题行的 ＋ 添加"),
    ).toBeInTheDocument();
    // 添加入口住分组标题行尾（ZCode PurposeSections 段头动作位）：
    // 收藏 / 最近打开各一枚，均可用
    const triggers = screen.getAllByRole("button", {
      name: "新建会话或添加项目",
    });
    expect(triggers).toHaveLength(2);
    expect(triggers[0]).toBeEnabled();
    expect(triggers[1]).toBeEnabled();
    // 分组头恒在（ZCode WorkspacePurposeSection 结构），空组只是没有行
    expect(screen.getByLabelText("收藏")).toBeInTheDocument();
    expect(screen.getByLabelText("最近打开")).toBeInTheDocument();
  });

  it("分组头 chevron：点击收起/展开本组行（行消失，分组头保留）", async () => {
    useWorkspaceStore.setState({
      recentWorkspaces: [{ path: PATH, lastOpenedAt: "2026-10-20T10:00:00Z" }],
      favoritePaths: [],
    });
    useSessionStore.setState({
      sessionsByPath: {
        [PATH]: [{ id: "s-1", title: "会话 · 甲", updatedAt: null }],
      },
    });
    render(<ProjectTree />);
    const recent = screen.getByLabelText("最近打开");
    const toggle = within(recent).getByRole("button", { name: /最近打开/ });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(within(recent).getByTitle(PATH)).toBeInTheDocument();

    // 收起：行消失，分组头保留且 aria-expanded 翻 false
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(
      within(screen.getByLabelText("最近打开")).queryByTitle(PATH),
    ).not.toBeInTheDocument();

    // 再展开：行回来
    await userEvent.click(toggle);
    expect(
      within(screen.getByLabelText("最近打开")).getByTitle(PATH),
    ).toBeInTheDocument();
  });
});

describe("ProjectTree 会话子节点分页", () => {
  /** 12 条会话（s-12 … s-01，s-12 更新时间最新）。 */
  const twelve = Array.from({ length: 12 }, (_, index) => {
    const n = 12 - index;
    return {
      id: `s-${String(n).padStart(2, "0")}`,
      title: `会话 ${String(n).padStart(2, "0")}`,
      updatedAt: `2026-10-${String(n).padStart(2, "0")}T10:00:00Z`,
    };
  });

  function seedProject(
    sessions: ReadonlyArray<{
      id: string;
      title: string;
      updatedAt: string;
    }>,
  ) {
    useWorkspaceStore.setState({
      recentWorkspaces: [{ path: PATH, lastOpenedAt: "2026-10-20T10:00:00Z" }],
      favoritePaths: [],
    });
    useSessionStore.setState({ sessionsByPath: { [PATH]: [...sessions] } });
  }

  it("默认只呈现最近 5 条，按钮标注剩余条数；逐页纳新直到全量", async () => {
    seedProject(twelve);
    const user = userEvent.setup();
    render(<ProjectTree />);

    // 默认 5 条（列表顺序即呈现顺序），第 6 条起不渲染
    expect(screen.getByRole("button", { name: /会话 12/ })).toBeVisible();
    expect(screen.getByRole("button", { name: /会话 08/ })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /会话 07/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "加载更多会话（还有 7 条）" }),
    ).toBeVisible();

    // 第一页：5 → 10
    await user.click(
      screen.getByRole("button", { name: "加载更多会话（还有 7 条）" }),
    );
    expect(screen.getByRole("button", { name: /会话 03/ })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /会话 02/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "加载更多会话（还有 2 条）" }),
    ).toBeVisible();

    // 第二页：10 → 12，全部呈现后按钮消失，「＋ 新会话」仍在末尾
    await user.click(
      screen.getByRole("button", { name: "加载更多会话（还有 2 条）" }),
    );
    expect(screen.getByRole("button", { name: /会话 01/ })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /^加载更多/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "新会话（pager）" }),
    ).toBeVisible();
  });

  it("不超过一页时全量呈现，无加载更多按钮", () => {
    seedProject(twelve.slice(0, 5));
    render(<ProjectTree />);
    expect(screen.getByRole("button", { name: /会话 12/ })).toBeVisible();
    expect(screen.getByRole("button", { name: /会话 08/ })).toBeVisible();
    expect(
      screen.queryByRole("button", { name: /^加载更多/ }),
    ).not.toBeInTheDocument();
  });
});
