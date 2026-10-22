/**
 * src/ui/PendingInbox（顶栏「待办」下拉面板形态）测试：
 * 空态不渲染、列表渲染、焦点切换（aria-current）、点选回调。
 * 数据经 offerPermission / offerQuestions 真实挂起通路预置。
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PendingInbox } from "../../src/ui/PendingInbox";
import { useApprovalStore } from "../../src/stores/approvalStore";

const PERMISSION_TOOL_CALL = {
  toolCallId: "call-1",
  title: "执行 aaw run --stage review",
  kind: "execute",
  status: "pending",
  rawInput: { command: "aaw run --stage review" },
  _meta: { chrys: { tool_name: "bash", tool_kind: "execute" } },
};

const CHRYS_OPTIONS = [
  { optionId: "allow", name: "Allow once", kind: "allow_once" as const },
  { optionId: "reject", name: "Reject once", kind: "reject_once" as const },
];

const QUESTIONS = [
  {
    question: "评审结论采用哪种严格度？",
    header: "评审严格度",
    multiSelect: false,
    options: [{ label: "标准", description: "列出全部级别" }],
  },
];

/** 经 offer* 真实通路挂起一条审批与一条提问（Promise 悬置由 clear 收口）。 */
function seedPendingItems(): void {
  void useApprovalStore.getState().offerPermission({
    sessionId: "s1",
    toolCall: PERMISSION_TOOL_CALL,
    options: CHRYS_OPTIONS,
  });
  void useApprovalStore.getState().offerQuestions({
    sessionId: "s1",
    requestId: "req-1",
    questions: QUESTIONS,
    callerName: null,
  });
}

beforeEach(() => {
  useApprovalStore.getState().clear();
});

describe("PendingInbox（下拉面板）", () => {
  it("无挂起项时面板不渲染", () => {
    render(<PendingInbox />);
    expect(screen.queryByLabelText("待办中心")).not.toBeInTheDocument();
  });

  it("列出审批与问答两类挂起项及计数", () => {
    seedPendingItems();
    render(<PendingInbox />);
    expect(screen.getByText("执行 aaw run --stage review")).toBeInTheDocument();
    expect(screen.getByText("评审严格度")).toBeInTheDocument();
    expect(screen.getByText("审批")).toBeInTheDocument();
    expect(screen.getByText("问答")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("多个挂起项可点击切换焦点（aria-current 跟随）", async () => {
    const user = userEvent.setup();
    seedPendingItems();
    render(<PendingInbox />);

    // 首条自动聚焦：审批项带 aria-current
    const list = screen.getByRole("list");
    const firstButton = within(list).getAllByRole("button")[0];
    const secondButton = within(list).getAllByRole("button")[1];
    if (firstButton === undefined || secondButton === undefined) {
      throw new Error("应渲染两条待办");
    }
    expect(firstButton).toHaveAttribute("aria-current", "true");
    expect(secondButton).not.toHaveAttribute("aria-current");

    // 点击第二项切换焦点
    await user.click(secondButton);
    expect(useApprovalStore.getState().activeId).toBe(
      useApprovalStore.getState().pending[1]?.id,
    );
    expect(secondButton).toHaveAttribute("aria-current", "true");
    expect(firstButton).not.toHaveAttribute("aria-current");
  });

  it("点选条目后触发 onSelect 回调（供父组件收起下拉）", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    seedPendingItems();
    render(<PendingInbox onSelect={onSelect} />);

    await user.click(screen.getByText("执行 aaw run --stage review"));
    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});
