/**
 * 输入区交互：Enter 发送 / Shift+Enter 换行 / IME 组词 / 运行中变「停止」；
 * 悬浮形态（rounded-2xl 卡片、透明输入行、下行元信息条）见「悬浮形态」组。
 */
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatInput } from "../../../src/ui/session/ChatInput.tsx";
import { useSessionStore } from "../../../src/stores/sessionStore.ts";
import { useRuntimeStatusStore } from "../../../src/stores/runtimeStatusStore.ts";

function setup(options: { isAgentRunning?: boolean } = {}) {
  const onSend = vi.fn();
  const onCancel = vi.fn();
  render(
    <ChatInput
      isAgentRunning={options.isAgentRunning ?? false}
      onSend={onSend}
      onCancel={onCancel}
    />,
  );
  return { onSend, onCancel };
}

function getTextarea(): HTMLTextAreaElement {
  return screen.getByLabelText("消息输入框");
}

describe("ChatInput", () => {
  it("Enter 发送并清空草稿", async () => {
    const { onSend } = setup();
    await userEvent.type(getTextarea(), "帮我跑下测试{Enter}");
    expect(onSend).toHaveBeenCalledWith("帮我跑下测试");
    expect(getTextarea()).toHaveValue("");
  });

  it("Shift+Enter 换行而不发送", async () => {
    const { onSend } = setup();
    await userEvent.type(getTextarea(), "第一行{Shift>}{Enter}{/Shift}第二行");
    expect(onSend).not.toHaveBeenCalled();
    expect(getTextarea()).toHaveValue("第一行\n第二行");
  });

  it("输入法组词中的 Enter 不发送", () => {
    const { onSend } = setup();
    const textarea = getTextarea();
    fireEvent.change(textarea, { target: { value: "拼字中" } });
    fireEvent.keyDown(textarea, { key: "Enter", isComposing: true });
    expect(onSend).not.toHaveBeenCalled();
    expect(textarea).toHaveValue("拼字中");
  });

  it("空输入（纯空白）禁用发送", async () => {
    const { onSend } = setup();
    const sendButton = screen.getByRole("button", { name: "发送" });
    expect(sendButton).toBeDisabled();
    await userEvent.type(getTextarea(), "   ");
    expect(sendButton).toBeDisabled();
    expect(onSend).not.toHaveBeenCalled();
  });

  it("运行中主按钮变「停止」，点击触发取消；Enter 不发送", async () => {
    const { onSend, onCancel } = setup({ isAgentRunning: true });
    expect(screen.getByRole("button", { name: "停止" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "发送" }),
    ).not.toBeInTheDocument();
    await userEvent.type(getTextarea(), "排队消息{Enter}");
    expect(onSend).not.toHaveBeenCalled();
    expect(getTextarea()).toHaveValue("排队消息");
    await userEvent.click(screen.getByRole("button", { name: "停止" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });
});

describe("ChatInput 悬浮形态", () => {
  afterEach(() => {
    // 模型 / 审批模式元信息是本组注入的，收口避免影响其他用例
    useSessionStore.setState({ modelLabel: null, approvalMode: null });
    useRuntimeStatusStore.getState().reset();
  });

  it("模型标识：runtime 模型名优先，回落 sessionStore 的 profile id；短格式与占位 —", () => {
    useSessionStore.setState({
      modelLabel: "0123456789abcdef0123456789abcdef",
    });
    const { rerender } = render(
      <ChatInput isAgentRunning={false} onSend={vi.fn()} onCancel={vi.fn()} />,
    );
    // runtime 无模型信息：回落 sessionStore 的 modelLabel（裸 hash 截 12 位）
    expect(screen.getByTitle(/0123456789abcdef/)).toHaveTextContent(
      "0123456789ab",
    );

    // runtimeDetails 带模型名时优先于 profile id
    useRuntimeStatusStore.getState().handleSessionEvent({
      type: "chrys_runtime",
      sessionId: "s-test",
      runtime: {
        modelProfileId: "glm-max",
        runtimeDetails: {
          model: { name: "glm-5.3-flash", provider: "zhipu" },
        },
      },
    });
    rerender(
      <ChatInput isAgentRunning={false} onSend={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByTitle(/glm-5/)).toHaveTextContent("glm-5.3-flash");

    // 两处都无模型时占位 —
    useSessionStore.setState({ modelLabel: null });
    useRuntimeStatusStore.getState().reset();
    rerender(
      <ChatInput isAgentRunning={false} onSend={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("审批模式徽标随 approvalMode 显示", () => {
    useSessionStore.setState({
      approvalMode: { id: "manual", name: "手动审批" },
    });
    render(
      <ChatInput isAgentRunning={false} onSend={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByTitle("审批模式")).toHaveTextContent("手动审批");
  });

  it("发送为圆形主钮：空输入禁用、填写后可用并发出", async () => {
    const onSend = vi.fn();
    render(
      <ChatInput isAgentRunning={false} onSend={onSend} onCancel={vi.fn()} />,
    );
    const sendButton = screen.getByRole("button", { name: "发送" });
    expect(sendButton).toHaveClass("rounded-full");
    expect(sendButton).toBeDisabled();
    await userEvent.type(getTextarea(), "悬浮输入");
    expect(sendButton).toBeEnabled();
    await userEvent.click(sendButton);
    expect(onSend).toHaveBeenCalledWith("悬浮输入");
  });

  it("运行中停止钮为圆形危险钮", () => {
    render(
      <ChatInput isAgentRunning={true} onSend={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.getByRole("button", { name: "停止" })).toHaveClass(
      "rounded-full",
    );
  });

  it("附件占位已移除：功能接入前不留可点却无动作的图标", () => {
    render(
      <ChatInput isAgentRunning={false} onSend={vi.fn()} onCancel={vi.fn()} />,
    );
    expect(screen.queryByLabelText(/附件/)).not.toBeInTheDocument();
    expect(screen.queryByTitle(/附件/)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------- 输入历史 / @ 提及
import { useWorkspaceStore } from "../../../src/stores/workspaceStore.ts";
import { listWorkspaceFiles } from "../../../src/aaw/fileListing.ts";
import { resetPromptHistoryForTests } from "../../../src/ui/session/promptHistory.ts";

vi.mock("../../../src/aaw/fileListing.ts", () => ({
  listWorkspaceFiles: vi.fn(),
}));

describe("ChatInput 输入历史", () => {
  it("空输入按 ↑ 回溯最近发送，↑↑ 再上一条，↓ 前进并回到空草稿", async () => {
    resetPromptHistoryForTests();
    const { onSend } = setup();
    const textarea = getTextarea();
    await userEvent.type(textarea, "第一条{Enter}");
    await userEvent.type(textarea, "第二条{Enter}");
    expect(onSend).toHaveBeenCalledTimes(2);

    await userEvent.type(textarea, "{ArrowUp}");
    expect(textarea).toHaveValue("第二条");
    await userEvent.type(textarea, "{ArrowUp}");
    expect(textarea).toHaveValue("第一条");
    await userEvent.type(textarea, "{ArrowDown}");
    expect(textarea).toHaveValue("第二条");
    await userEvent.type(textarea, "{ArrowDown}");
    // 退出浏览：回到起步时的草稿（空）
    expect(textarea).toHaveValue("");
  });

  it("非空输入且不在浏览态时 ↑ 不劫持（多行编辑自由移动光标）", async () => {
    const { onSend } = setup();
    const textarea = getTextarea();
    await userEvent.type(textarea, "多行内容不劫持");
    await userEvent.type(textarea, "{ArrowUp}");
    expect(textarea).toHaveValue("多行内容不劫持");
    expect(onSend).not.toHaveBeenCalled();
  });
});

describe("ChatInput @ 文件提及", () => {
  it("输入 @ 弹候选面板，Enter 插入 @路径 并关闭面板", async () => {
    useWorkspaceStore.setState({ activePath: "D:/dev/demo" });
    vi.mocked(listWorkspaceFiles).mockResolvedValue([
      "README.md",
      "src/app.ts",
    ]);
    setup();
    const textarea = getTextarea();
    await userEvent.type(textarea, "看 @rea");
    const option = await screen.findByRole("option", { name: /README/ });
    expect(option).toBeInTheDocument();

    await userEvent.type(textarea, "{Enter}");
    expect(textarea).toHaveValue("看 @README.md ");
    expect(
      screen.queryByRole("listbox", { name: "文件候选" }),
    ).not.toBeInTheDocument();
  });

  it("无匹配显示空态提示，Esc 关闭面板", async () => {
    useWorkspaceStore.setState({ activePath: "D:/dev/demo" });
    vi.mocked(listWorkspaceFiles).mockResolvedValue(["README.md"]);
    setup();
    const textarea = getTextarea();
    await userEvent.type(textarea, "@zzz");
    expect(await screen.findByText("没有匹配的文件")).toBeInTheDocument();
    await userEvent.type(textarea, "{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("面板内 ↑↓ 移动选中项（aria-selected 跟随）", async () => {
    useWorkspaceStore.setState({ activePath: "D:/dev/demo" });
    vi.mocked(listWorkspaceFiles).mockResolvedValue([
      "README.md",
      "src/app.ts",
      "docs/guide.md",
    ]);
    setup();
    const textarea = getTextarea();
    await userEvent.type(textarea, "@");
    const options = await screen.findAllByRole("option");
    expect(options).toHaveLength(3);
    expect(options[0]).toHaveAttribute("aria-selected", "true");

    await userEvent.type(textarea, "{ArrowDown}");
    expect(options[1]).toHaveAttribute("aria-selected", "true");
    await userEvent.type(textarea, "{ArrowUp}");
    expect(options[0]).toHaveAttribute("aria-selected", "true");
  });
});
