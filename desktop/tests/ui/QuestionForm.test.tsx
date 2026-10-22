/**
 * src/ui/QuestionForm 测试：卡片渲染、单选/多选交互、
 * 提交门禁与取消，全部经真实 approvalStore 生效。
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { QuestionForm } from "../../src/ui/QuestionForm";
import { useApprovalStore } from "../../src/stores/approvalStore";
import type { PendingQuestions } from "../../src/stores/approvalStore";
import type { ChrysRequestInputResult } from "../../src/acp/types";

const QUESTIONS = [
  {
    question: "评审结论采用哪种严格度？",
    header: "评审严格度",
    multiSelect: false,
    options: [
      { label: "标准", description: "阻塞级与建议级问题都列出" },
      { label: "宽松", description: "仅列出阻塞级问题" },
    ],
  },
  {
    question: "报告需要包含哪些附录？",
    header: "报告附录",
    multiSelect: true,
    options: [
      { label: "完整 diff", description: "附上全部改动差异" },
      { label: "测试输出", description: "附上测试运行日志摘要" },
      { label: "耗时统计", description: "附上各阶段执行耗时" },
    ],
  },
];

/** 挂起一批提问并取出定型后的项，可选用 box 捕获回传结果。 */
function seedQuestions(): {
  item: PendingQuestions;
  result: { value: ChrysRequestInputResult | null | undefined };
} {
  const box = {
    value: undefined as ChrysRequestInputResult | null | undefined,
  };
  void useApprovalStore
    .getState()
    .offerQuestions({
      sessionId: "s1",
      requestId: "req-1",
      questions: QUESTIONS,
      callerName: "skill-eval",
    })
    .then((value) => {
      box.value = value;
    });
  const item = useApprovalStore.getState().pending[0];
  if (item === undefined || item.kind !== "questions") {
    throw new Error("应挂起提问项");
  }
  return { item, result: box };
}

beforeEach(() => {
  useApprovalStore.getState().clear();
});

describe("QuestionForm", () => {
  it("按卡片渲染 header、题干、选项与调用方", () => {
    const { item } = seedQuestions();
    render(<QuestionForm item={item} />);
    expect(screen.getByText("评审严格度")).toBeInTheDocument();
    expect(screen.getByText("报告附录")).toBeInTheDocument();
    expect(screen.getByText("评审结论采用哪种严格度？")).toBeInTheDocument();
    expect(screen.getByText("阻塞级与建议级问题都列出")).toBeInTheDocument();
    expect(screen.getByText(/来自 skill-eval/)).toBeInTheDocument();
    // 单选题是 radio 语义，多选题是 checkbox 语义
    expect(screen.getAllByRole("radio")).toHaveLength(2);
    expect(screen.getAllByRole("checkbox")).toHaveLength(3);
  });

  it("未全部作答时提交禁用；作答后可提交并按位回传", async () => {
    const user = userEvent.setup();
    const { item, result } = seedQuestions();
    render(<QuestionForm item={item} />);

    const submit = screen.getByRole("button", { name: "提交回答" });
    expect(submit).toBeDisabled();

    // 只答第一问，第二问未答 → 仍禁用
    await user.click(screen.getByRole("radio", { name: /标准/ }));
    expect(submit).toBeDisabled();

    // 补答第二问（多选两项）→ 可提交
    await user.click(screen.getByRole("checkbox", { name: /完整 diff/ }));
    await user.click(screen.getByRole("checkbox", { name: /耗时统计/ }));
    expect(submit).toBeEnabled();

    await user.click(submit);
    await Promise.resolve();
    expect(result.value).toEqual({
      answers: [{ values: ["标准"] }, { values: ["完整 diff", "耗时统计"] }],
    });
    expect(useApprovalStore.getState().pending).toHaveLength(0);
  });

  it("单选可改选；再点同项取消选择", async () => {
    const user = userEvent.setup();
    const { item } = seedQuestions();
    render(<QuestionForm item={item} />);

    const standard = screen.getByRole("radio", { name: /标准/ });
    const loose = screen.getByRole("radio", { name: /宽松/ });
    await user.click(standard);
    expect(standard).toHaveAttribute("aria-checked", "true");
    await user.click(loose);
    expect(loose).toHaveAttribute("aria-checked", "true");
    expect(standard).toHaveAttribute("aria-checked", "false");
    // 取消选择后提交回到禁用
    await user.click(loose);
    expect(loose).toHaveAttribute("aria-checked", "false");
    expect(screen.getByRole("button", { name: "提交回答" })).toBeDisabled();
  });

  it("多选可勾选/取消勾选", async () => {
    const user = userEvent.setup();
    const { item } = seedQuestions();
    render(<QuestionForm item={item} />);
    const diff = screen.getByRole("checkbox", { name: /完整 diff/ });
    await user.click(diff);
    expect(diff).toHaveAttribute("aria-checked", "true");
    await user.click(diff);
    expect(diff).toHaveAttribute("aria-checked", "false");
  });

  it("取消按钮按 cancelled 回传", async () => {
    const user = userEvent.setup();
    const { item, result } = seedQuestions();
    render(<QuestionForm item={item} />);
    await user.click(screen.getByRole("button", { name: "取消" }));
    await Promise.resolve();
    expect(result.value).toEqual({ cancelled: true });
    expect(useApprovalStore.getState().pending).toHaveLength(0);
  });
});
