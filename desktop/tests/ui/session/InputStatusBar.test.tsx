/**
 * 输入区状态行（InputStatusBar）测试：上下文用量条（百分比与用量条、
 * 70/90 阈值换色）、skills/mcp 计数徽标与悬停明细、运行状态章（相位文案
 * 随轮次状态机变化，轮次外不显示）。
 */
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  InputStatusLeft,
  InputStatusRight,
  TurnStatusRow,
} from "../../../src/ui/session/InputStatusBar.tsx";
import { useRuntimeStatusStore } from "../../../src/stores/runtimeStatusStore.ts";
import { useSessionStore } from "../../../src/stores/sessionStore.ts";
import { useApprovalStore } from "../../../src/stores/approvalStore.ts";

beforeEach(() => {
  useRuntimeStatusStore.getState().reset();
  useSessionStore.setState({ isAgentRunning: false });
});

afterEach(() => {
  cleanup();
});

function seedRuntime(): void {
  useRuntimeStatusStore.getState().handleSessionEvent({
    type: "chrys_runtime",
    sessionId: "s-1",
    runtime: {
      modelProfileId: "glm-max",
      skillNames: ["aaw-workflow", "code-check"],
      runtimeDetails: {
        model: { name: "GLM-4.6", provider: "zhipu" },
        mcp_tools: { "server-a": ["t1"], "server-b": ["t1", "t2"] },
        mcp_failures: { "server-c": "connection refused" },
        skill_sources: { user: ["aaw-workflow"], project: ["code-check"] },
      },
    },
  });
  useRuntimeStatusStore.getState().handleSessionEvent({
    type: "chrys_usage",
    sessionId: "s-1",
    usage: {
      sessionId: "s-1",
      pct: 42.5,
      totalTokens: 51000,
      maxContextTokens: 120000,
      totalSessionTokens: 90000,
      cacheHitTokens: 8000,
      usageSourceId: "s-1",
    },
  } as never);
}

describe("InputStatusBar", () => {
  it("上下文用量圆环：百分比 + 悬停明细（窗口/累计/缓存）", () => {
    seedRuntime();
    render(<InputStatusRight />);
    const meter = screen.getByText("42%").closest("[data-status=context]");
    expect(meter).not.toBeNull();
    expect(meter).toHaveAttribute(
      "title",
      expect.stringContaining("51k / 120k"),
    );
    expect(meter).toHaveAttribute("title", expect.stringContaining("90k"));
    expect(meter).toHaveAttribute("title", expect.stringContaining("8k"));
  });

  it("「+」二级菜单只收纳 skills 清单（评审确认），不含 MCP", async () => {
    seedRuntime();
    render(<InputStatusLeft />);
    // 状态行只留一枚 + 芯片，旧计数徽标不再出现
    expect(screen.getByRole("button", { name: "会话 skills" })).toBeInTheDocument();
    expect(screen.queryByText(/skills \d/)).not.toBeInTheDocument();
    expect(screen.queryByText(/mcp \d/)).not.toBeInTheDocument();

    // 点开：只有 skills 清单；MCP 不进菜单
    await userEvent.click(screen.getByRole("button", { name: "会话 skills" }));
    const menu = screen.getByRole("menu", { name: "会话 skills" });
    expect(menu).toHaveTextContent("Skills · 2");
    expect(menu).toHaveTextContent("aaw-workflow");
    expect(menu).not.toHaveTextContent("MCP");
    expect(menu).not.toHaveTextContent("server-a");
  });

  it("模型切换器：无清单时纯展示；有清单时菜单可换（经 store switchModel）", async () => {
    seedRuntime();
    const { rerender } = render(<InputStatusRight />);
    // 无清单：纯展示标签（圆环测试另行覆盖，这里只看模型不带 menu）
    expect(
      screen.queryByRole("button", { name: "模型选择" }),
    ).not.toBeInTheDocument();

    const switchModel = vi.fn();
    useSessionStore.setState({
      availableModels: [
        { modelId: "glm-5", name: "glm-5", description: null },
        { modelId: "deepseek-v4", name: "deepseek-v4", description: null },
      ],
      currentModelId: "glm-5",
      switchModel,
    });
    rerender(<InputStatusRight />);
    await userEvent.click(screen.getByRole("button", { name: "模型选择" }));
    const menu = screen.getByRole("menu", { name: "模型选择" });
    expect(menu).toHaveTextContent("glm-5");
    expect(menu).toHaveTextContent("deepseek-v4");
    // 选中 deepseek-v4
    await userEvent.click(screen.getByRole("menuitem", { name: /deepseek-v4/ }));
    expect(switchModel).toHaveBeenCalledWith("deepseek-v4");
  });

  it("无 usage 时不渲染圆环；无 skills 时「+」菜单呈空态（模型占位仍在）", async () => {
    render(<InputStatusLeft />);
    render(<InputStatusRight />);
    expect(screen.queryByText(/%/)).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "会话 skills" }));
    const menu = screen.getByRole("menu", { name: "会话 skills" });
    expect(menu).toHaveTextContent("无已加载 skill");
  });

  it("轮次相位行：轮次内相位可见，轮次外不渲染", () => {
    seedRuntime();
    useSessionStore.setState({ isAgentRunning: true });
    const { rerender } = render(<TurnStatusRow />);
    // 轮次未开始（isTurnActive=false）：不显示
    expect(screen.queryByText(/思考中/)).not.toBeInTheDocument();

    useRuntimeStatusStore.getState().beginTurn();
    rerender(<TurnStatusRow />);
    expect(screen.getByText("思考中…")).toBeInTheDocument();

    useRuntimeStatusStore.getState().handleSessionEvent({
      type: "tool_call",
      sessionId: "s-1",
      toolCallId: "t1",
      status: "in_progress",
    } as never);
    rerender(<TurnStatusRow />);
    expect(screen.getByText("工具运行中 1…")).toBeInTheDocument();

    // 轮次结束（isAgentRunning=false）：不显示
    useSessionStore.setState({ isAgentRunning: false });
    rerender(<TurnStatusRow />);
    expect(screen.queryByText(/工具运行中/)).not.toBeInTheDocument();
  });

  it("轮次相位行：有挂起的提问/审批时退场（此刻是在等用户，不是生成中）", () => {
    seedRuntime();
    useSessionStore.setState({ isAgentRunning: true });
    useRuntimeStatusStore.getState().beginTurn();
    render(<TurnStatusRow />);
    expect(screen.getByText("思考中…")).toBeInTheDocument();

    // 挂起一条提问（Promise 悬置、轮次仍 active）：相位行让位给问答面板
    act(() => {
      void useApprovalStore.getState().offerQuestions({
        sessionId: "s-1",
        requestId: "q1",
        callerName: "sr-init",
        questions: [
          {
            question: "原文是否一致？",
            header: "核对",
            multiSelect: false,
            options: [
              { label: "一致", description: "" },
              { label: "不一致", description: "" },
            ],
          },
        ],
      });
    });
    expect(screen.queryByText("思考中…")).not.toBeInTheDocument();
    useApprovalStore.getState().clear();
  });
});
