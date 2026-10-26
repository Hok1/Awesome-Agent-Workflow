/**
 * 会话视图组合：回放脚本渲染全类条目、工具条元信息、输入区驱动 store、
 * 运行中「停止」走绑定取消。
 */
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SessionView } from "../../../src/ui/session/SessionView.tsx";
import {
  useSessionStore,
  type SessionBinding,
} from "../../../src/stores/sessionStore.ts";
import { useWorkspaceStore } from "../../../src/stores/workspaceStore.ts";
import { useWorkbenchUiStore } from "../../../src/stores/workbenchUiStore.ts";
import { replaySampleConversation } from "../../fixtures/sessionScript.ts";

const PATH = "D:/dev/demo-project";

beforeEach(() => {
  useSessionStore.getState().clear();
  useSessionStore.getState().bindSession(null);
  useSessionStore.setState({ modelLabel: null, approvalMode: null });
  useWorkspaceStore.setState({ activePath: null });
  useWorkbenchUiStore.setState({ treeView: "session", contextPath: null });
});

describe("SessionView", () => {
  it("回放会话后渲染全部条目类型与输入区元信息（模型 + 审批徽标在输入区下行）", () => {
    replaySampleConversation();
    render(<SessionView />);

    // 输入区下行：模型 + 审批徽标（原会话工具条元信息，已收编至此）
    expect(screen.getByText("glm-4.7-coding")).toBeInTheDocument();
    expect(screen.getByText("手动审批")).toBeInTheDocument();

    // 用户消息
    expect(
      screen.getByText(
        "帮我看下登录接口为什么返回 401，必要时改掉测试里的过期 token。",
      ),
    ).toBeInTheDocument();

    // 工具卡（折叠态）
    expect(
      screen.getAllByRole("button", { name: /search|read|load skill/ }).length,
    ).toBe(3);

    // 助手 Markdown：代码块语言标签
    expect(screen.getByText("bash")).toBeInTheDocument();

    // 思考块折叠入口（按钮名含折叠箭头，按子串匹配）
    expect(
      screen.getByRole("button", { name: /思考过程/ }),
    ).toBeInTheDocument();
  });

  it("空会话显示引导文案", () => {
    render(<SessionView />);
    // hero 空态：时段问候 + 主旨问句 + 入口 chips
    expect(screen.getByText(/，今天想推进什么？/)).toBeInTheDocument();
  });

  it("项目已关闭（无 activePath）时空态改为「项目已关闭」并提供重新打开入口", async () => {
    useWorkbenchUiStore.setState({ treeView: "session", contextPath: PATH });
    render(<SessionView />);

    expect(screen.getByText("项目已关闭")).toBeInTheDocument();
    expect(
      screen.queryByText("会话为空。发送第一条消息即可开始。"),
    ).not.toBeInTheDocument();

    // 重新打开项目：把路径写回 activePath（RealSessionRuntime 据此重连）
    await userEvent.click(screen.getByRole("button", { name: "重新打开项目" }));
    expect(useWorkspaceStore.getState().activePath).toBe(PATH);
  });

  it("输入 + Enter 经 store 发送：落用户消息并调用绑定 prompt", async () => {
    const prompt = vi.fn(
      () => new Promise<{ stopReason: "end_turn" }>(() => undefined),
    );
    const binding: SessionBinding = { prompt, cancel: vi.fn() };
    useSessionStore.getState().bindSession(binding);
    render(<SessionView />);

    await userEvent.type(screen.getByLabelText("消息输入框"), "第一问{Enter}");
    expect(prompt).toHaveBeenCalledWith("第一问");
    expect(await screen.findByText("第一问")).toBeInTheDocument();
    // 运行中：输入区变停止按钮
    expect(screen.getByRole("button", { name: "停止" })).toBeInTheDocument();
  });

  it("运行中点击「停止」触发绑定的 cancel（session/cancel）", async () => {
    const cancel = vi.fn();
    const binding: SessionBinding = {
      prompt: () => new Promise<{ stopReason: "cancelled" }>(() => undefined),
      cancel,
    };
    useSessionStore.getState().bindSession(binding);
    render(<SessionView />);
    await userEvent.type(
      screen.getByLabelText("消息输入框"),
      "跑长任务{Enter}",
    );
    await userEvent.click(screen.getByRole("button", { name: "停止" }));
    expect(cancel).toHaveBeenCalledTimes(1);
  });

  it("未绑定时发送：提示未连接且不落用户消息", async () => {
    render(<SessionView />);
    await userEvent.type(
      screen.getByLabelText("消息输入框"),
      "没有 agent{Enter}",
    );
    expect(await screen.findByText(/尚未连接 agent/)).toBeInTheDocument();
    expect(screen.queryByText("没有 agent")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------- 窗口化与空态入口
import type { SessionItem } from "../../../src/stores/sessionStore.ts";

describe("SessionView 长会话窗口化与空态入口", () => {
  it("300 条长会话只渲染最近 150 条；滚动到顶补载更早一块", async () => {
    const items: SessionItem[] = Array.from({ length: 300 }, (_, index) => ({
      kind: "user" as const,
      id: `u${index}`,
      text: `消息${index}`,
      createdAt: "2026-10-24T10:00:00Z",
    }));
    useSessionStore.setState({ items });
    render(<SessionView />);

    // 旧块未挂载，最近块在
    expect(screen.queryByText("消息0")).not.toBeInTheDocument();
    expect(screen.getByText("消息299")).toBeInTheDocument();

    // 贴顶滚动触发补载（jsdom 中 scrollTop=0 恒贴顶）
    fireEvent.scroll(screen.getByRole("log", { name: "消息流" }));
    expect(await screen.findByText("消息0")).toBeInTheDocument();
    expect(screen.getByText("消息299")).toBeInTheDocument();
  });

  it("空会话给推荐入口 chips；点击预填输入框（不自动发送）", async () => {
    render(<SessionView />);
    await userEvent.click(
      screen.getByRole("button", { name: "启动一条工作流" }),
    );
    expect(screen.getByLabelText("消息输入框")).toHaveValue(
      "请从 sr 入口新建一条 AAW 工作流，先与我确认需求。",
    );
    // 预填不是发送：消息流仍呈空态 hero
    expect(screen.getByText(/，今天想推进什么？/)).toBeInTheDocument();
  });
});
