import { StrictMode } from "react";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { GitPanel } from "../../src/ui/right-panel/GitPanel.tsx";
import {
  panelService,
  type GitChange,
  type GitDiff,
  type GitSnapshot,
} from "../../src/core/panelService.ts";
import { useRightPanelStore } from "../../src/stores/rightPanelStore.ts";

const a: GitChange = {
  path: "src/a.txt",
  oldPath: null,
  source: "unstaged",
  status: "修改",
  added: 2,
  removed: 1,
};
const b: GitChange = { ...a, path: "b.txt", source: "untracked", removed: 0 };
const staged: GitChange = { ...a, source: "staged", added: 4 };
const branch: GitChange = { ...a, path: "committed.txt", source: "branch" };
const snapshot: GitSnapshot = {
  repoRoot: "D:/repo",
  branch: "main",
  changes: [a, b, staged],
  watchPaths: [],
  upstream: "origin/main",
  branchChanges: [branch],
};
const diff = (text: string): GitDiff => ({
  patch: `@@ -1 +1 @@\n-old\n+${text}\n`,
  notice: null,
  beforeContent: "old\n",
  afterContent: `${text}\n`,
});

beforeEach(() => {
  vi.restoreAllMocks();
  useRightPanelStore.setState({ projects: {} });
  vi.spyOn(panelService, "watch").mockResolvedValue(() => {});
  vi.spyOn(panelService, "gitStatus").mockResolvedValue(snapshot);
  vi.spyOn(panelService, "gitDiff").mockImplementation((_project, change) =>
    Promise.resolve(diff(change.path === "b.txt" ? "target B" : "target A")),
  );
});

describe("ZCode 风格 Git 审查", () => {
  it("来源筛选、单文件懒加载、行数统计，StrictMode 下只展开一个文件", async () => {
    render(
      <StrictMode>
        <GitPanel project="D:/repo" />
      </StrictMode>,
    );
    const open = await screen.findByRole("button", { name: "展开 src/a.txt" });
    expect(open).toHaveTextContent("+2−1");
    expect(panelService.gitDiff).not.toHaveBeenCalled();
    await userEvent.click(open);
    expect(await screen.findByText("target A")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "展开 b.txt" }));
    expect(await screen.findByText("target B")).toBeInTheDocument();
    expect(screen.queryByText("target A")).not.toBeInTheDocument();
    expect(screen.getAllByLabelText("Git 统一差异")).toHaveLength(1);
    await userEvent.selectOptions(screen.getByLabelText("变更来源"), "staged");
    expect(
      screen.getByRole("button", { name: "展开 src/a.txt" }),
    ).toHaveTextContent("+4");
    expect(
      screen.queryByRole("button", { name: "展开 b.txt" }),
    ).not.toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("变更来源"), "branch");
    expect(
      screen.getByRole("button", { name: "展开 committed.txt" }),
    ).toBeInTheDocument();
    expect(screen.getByText("origin/main…HEAD")).toBeInTheDocument();
    await userEvent.selectOptions(
      screen.getByLabelText("变更来源"),
      "last-turn",
    );
    expect(screen.getByText(/暂无上一轮更改/)).toBeInTheDocument();
  });
  it("搜索折叠文件内容并循环定位，文件名不算命中，Escape 只清查找", async () => {
    render(<GitPanel project="D:/repo" />);
    const input = await screen.findByLabelText("查找变更内容");
    await userEvent.type(input, "target");
    await waitFor(() =>
      expect(screen.getByLabelText("查找命中数")).toHaveTextContent("1/2"),
    );
    expect(
      screen.getByRole("button", { name: "收起 src/a.txt" }),
    ).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText("下一处匹配"));
    expect(
      screen.getByRole("button", { name: "收起 b.txt" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("查找命中数")).toHaveTextContent("2/2");
    expect(
      document.querySelector('[data-current-hit="true"]'),
    ).toHaveTextContent("target");
    await userEvent.click(screen.getByLabelText("下一处匹配"));
    expect(screen.getByLabelText("查找命中数")).toHaveTextContent("1/2");
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input).toHaveValue("");
    await userEvent.type(input, "a.txt");
    expect(screen.getByLabelText("查找命中数")).toHaveTextContent("0/0");
  });
  it("刷新后忽略旧缓存迟到结果，切来源保留查询且来源按项目恢复", async () => {
    let finish: ((value: GitDiff) => void) | undefined;
    vi.spyOn(panelService, "gitDiff")
      .mockImplementationOnce(
        () =>
          new Promise((resolve) => {
            finish = resolve;
          }),
      )
      .mockResolvedValue(diff("fresh"));
    const view = render(<GitPanel project="D:/repo" />);
    await userEvent.click(
      await screen.findByRole("button", { name: "展开 src/a.txt" }),
    );
    vi.spyOn(panelService, "gitStatus").mockResolvedValue({ ...snapshot });
    await userEvent.click(screen.getByRole("button", { name: "刷新" }));
    expect(await screen.findByText("fresh")).toBeInTheDocument();
    await act(async () => {
      finish?.(diff("late"));
      await Promise.resolve();
    });
    expect(screen.queryByText("late")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("查找变更内容"), "fresh");
    await userEvent.selectOptions(screen.getByLabelText("变更来源"), "staged");
    expect(screen.getByLabelText("查找变更内容")).toHaveValue("fresh");
    await waitFor(() =>
      expect(screen.getByLabelText("查找命中数")).toHaveTextContent("1/1"),
    );
    view.unmount();
    render(<GitPanel project="D:/repo" />);
    expect(await screen.findByLabelText("变更来源")).toHaveValue("staged");
  });
});
