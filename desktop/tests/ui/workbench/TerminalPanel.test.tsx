/**
 * 底部终端面板（TerminalPanel）测试：开合（isTerminalOpen 驱动 + 关闭钮）、
 * execute 工具输出的只读回放（mock sessionStore items，非 execute 滤除）、
 * 空态、失败样式、高度钳制边界（clamp [140px, 容器 50%]）。
 *
 * 能力口径（与实现一致）：本面板是 execute 输出回放，非 PTY 终端——
 * 无 shell 标签 / 多 tab 断言。
 */
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import {
  TERMINAL_MIN_HEIGHT_PX,
  TerminalPanel,
  clampTerminalHeight,
} from "../../../src/ui/workbench/TerminalPanel.tsx";
import {
  useSessionStore,
  type ToolCallItem,
} from "../../../src/stores/sessionStore.ts";
import { useWorkbenchUiStore } from "../../../src/stores/workbenchUiStore.ts";

const PATH = "D:/dev/demo-project";

function executeItem(
  overrides: Partial<ToolCallItem> & { readonly id: string },
): ToolCallItem {
  return {
    kind: "tool",
    toolCallId: `call-${overrides.id}`,
    title: "执行命令",
    toolKind: "execute",
    status: "completed",
    rawInput: "npm test",
    rawOutput: "all passed\n",
    inputSummary: "",
    resultSummary: "",
    startedAt: null,
    endedAt: null,
    ...overrides,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  useSessionStore.setState({ items: [] });
  useWorkbenchUiStore.setState({ isTerminalOpen: false });
});

describe("clampTerminalHeight（高度钳制）", () => {
  it("下限 140px；上限容器 50%；区间内原样；容器不可量测时不设上限", () => {
    expect(clampTerminalHeight(100, 1000)).toBe(TERMINAL_MIN_HEIGHT_PX);
    expect(clampTerminalHeight(800, 1000)).toBe(500);
    expect(clampTerminalHeight(300, 1000)).toBe(300);
    expect(clampTerminalHeight(300, 0)).toBe(300);
  });
});

describe("TerminalPanel（execute 输出的只读回放）", () => {
  it("渲染 execute 工具项的命令行与输出；非 execute 工具滤除；末尾 20 条", () => {
    const items = [
      executeItem({ id: "read-1", toolKind: "read", rawInput: "D:/x.ts" }),
      ...Array.from({ length: 22 }, (_, index) =>
        executeItem({
          id: `run-${index}`,
          rawInput: `cmd ${index}`,
          rawOutput: `out ${index}`,
        }),
      ),
    ];
    useSessionStore.setState({ items });
    render(<TerminalPanel project={PATH} />);

    // 只保留末尾 20 条 execute（最早两条被裁掉）
    expect(screen.queryByText("cmd 0")).not.toBeInTheDocument();
    expect(screen.queryByText("cmd 1")).not.toBeInTheDocument();
    expect(screen.getByText("cmd 21")).toBeInTheDocument();
    // 命令行 + 输出体（TerminalOutput 复用：aria-label=终端输出，共 20 条）
    expect(screen.getByText("cmd 2")).toBeInTheDocument();
    const outputs = screen.getAllByLabelText("终端输出");
    expect(outputs).toHaveLength(20);
    expect(outputs[outputs.length - 1]).toHaveTextContent("out 21");
    // 非 execute（read）不进回放
    expect(screen.queryByText("D:/x.ts")).not.toBeInTheDocument();
  });

  it("空态给一行指引；失败项的输出体呈危险色", () => {
    useSessionStore.setState({ items: [] });
    render(<TerminalPanel project={PATH} />);
    expect(screen.getByText("当前会话暂无命令输出")).toBeInTheDocument();

    // store 变更经订阅重渲染：断言失败样式挂在输出体上
    act(() => {
      useSessionStore.setState({
        items: [executeItem({ id: "bad-1", status: "failed" })],
      });
    });
    const output = screen.getByLabelText("终端输出");
    expect(output.className).toContain("text-danger-ink");
  });

  it("关闭钮与 store 同路：点击 toggleTerminal 翻转 isTerminalOpen（不持久化）", async () => {
    useWorkbenchUiStore.setState({ isTerminalOpen: true });
    render(<TerminalPanel project={PATH} />);
    expect(screen.getByTestId("terminal-panel")).toBeInTheDocument();

    await userEvent.click(screen.getByTestId("terminal-close-button"));
    expect(useWorkbenchUiStore.getState().isTerminalOpen).toBe(false);
  });

  it("ContentArea 集成：isTerminalOpen 驱动挂载，全屏覆盖层激活时不渲染", async () => {
    const { default: ContentArea } = await import(
      "../../../src/ui/workbench/ContentArea.tsx"
    );
    useWorkbenchUiStore.setState({
      treeView: "session",
      contextPath: PATH,
      overlay: null,
    });
    render(<ContentArea />);
    expect(
      screen.queryByTestId("terminal-panel"),
    ).not.toBeInTheDocument();

    act(() => {
      useWorkbenchUiStore.getState().toggleTerminal();
    });
    expect(screen.getByTestId("terminal-panel")).toBeInTheDocument();

    // 全屏功能页激活：面板退场（面板与覆盖层互斥）
    act(() => {
      useWorkbenchUiStore.getState().toggleOverlay("settings");
    });
    expect(screen.queryByTestId("terminal-panel")).not.toBeInTheDocument();
  });
});
