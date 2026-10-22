/**
 * 结构化问答表单：渲染一批挂起的 `_chrys/request_input` 提问。
 *
 * 每问一张卡片：header 徽标 + 题干 + 选项卡（指示器 + label + description）。
 * multiSelect 的题用 checkbox 语义可多选，单选题用 radio 语义；选项卡
 * 左侧固定自绘 radio/checkbox 指示器，选中态以 accent 描边 + 底色强化，
 * 用户能直接看出选择是否生效。来源说明（徽标 + 来自 caller）只在本
 * 表单头部出现一处，弹窗外壳不再重复。
 *
 * 全部问题都已选择时「提交回答」才可用——chrys 对 answers 的校验
 * （ask_user.py）要求每问恰好一条非空答案，空选提交只会被对端判为取消。
 *
 * 组件持有本地选择状态（纯 UI 态不入 store）；提交/取消调用
 * approvalStore 的 action，由 store 组装响应、写日志并回传。
 * 外壳由 ModalShell 提供，本组件不再自带卡片边框。
 */
import { useState } from "react";
import { useApprovalStore } from "../stores/approvalStore";
import type { PendingQuestions } from "../stores/approvalStore";
import { Badge, btnGhost, btnPrimary, CheckSquare, RadioDot } from "./controls";

/** 只读空集兜底，避免每次渲染新建对象。 */
const emptySelection: ReadonlySet<string> = new Set<string>();

export function QuestionForm({ item }: { readonly item: PendingQuestions }) {
  const submitAnswers = useApprovalStore((state) => state.submitAnswers);
  const cancelQuestions = useApprovalStore((state) => state.cancelQuestions);
  // 题目索引 → 已选 label 集合；父层用 key=item.id 保证切换挂起项时重置
  const [selections, setSelections] = useState<
    Readonly<Record<number, ReadonlySet<string>>>
  >({});

  const allAnswered = item.questions.every(
    (_, index) => (selections[index] ?? emptySelection).size > 0,
  );

  function toggle(index: number, multiSelect: boolean, label: string): void {
    setSelections((previous) => {
      const current = previous[index] ?? emptySelection;
      const next = new Set<string>(current);
      if (next.has(label)) {
        next.delete(label);
      } else if (multiSelect) {
        next.add(label);
      } else {
        next.clear();
        next.add(label);
      }
      return { ...previous, [index]: next };
    });
  }

  function handleSubmit(): void {
    const ordered = item.questions.map((_, index) => [
      ...(selections[index] ?? emptySelection),
    ]);
    submitAnswers(item.id, ordered);
  }

  return (
    <section aria-label="结构化问答">
      <header className="flex items-center gap-2 border-b border-line px-5 py-3">
        <Badge tone="info">结构化提问</Badge>
        <span className="text-xs text-ink-faint">
          {item.questions.length} 问
          {item.callerName !== null && item.callerName.length > 0
            ? ` · 来自 ${item.callerName}`
            : ""}
        </span>
      </header>

      <div className="space-y-4 px-5 py-4">
        {item.questions.map((question, index) => (
          <fieldset key={index} className="rounded-lg border border-line p-4">
            <div className="mb-2 flex items-center gap-2">
              <Badge tone="neutral">
                {question.header.length > 0
                  ? question.header
                  : `问题 ${index + 1}`}
              </Badge>
              {question.multiSelect && (
                <span className="text-xs text-ink-ghost">可多选</span>
              )}
            </div>
            <p className="mb-3 text-sm leading-relaxed text-ink">
              {question.question}
            </p>
            <div className="grid grid-cols-1 gap-2">
              {question.options.map((option) => {
                const isSelected = (selections[index] ?? emptySelection).has(
                  option.label,
                );
                return (
                  <button
                    key={option.label}
                    type="button"
                    role={question.multiSelect ? "checkbox" : "radio"}
                    aria-checked={isSelected}
                    onClick={() => {
                      toggle(index, question.multiSelect, option.label);
                    }}
                    className={`flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2 text-left transition-colors ${
                      isSelected
                        ? "border-sky-600 bg-info-bg/40"
                        : "border-line hover:border-line-strong"
                    }`}
                  >
                    {/* 显式选中指示物：单选圆点 / 多选对勾，暗色下可辨 */}
                    {question.multiSelect ? (
                      <CheckSquare checked={isSelected} />
                    ) : (
                      <RadioDot checked={isSelected} />
                    )}
                    <span className="min-w-0">
                      <span className="block text-sm font-medium text-ink">
                        {option.label}
                      </span>
                      {option.description.length > 0 && (
                        <span className="mt-0.5 block text-xs leading-relaxed text-ink-mute">
                          {option.description}
                        </span>
                      )}
                    </span>
                  </button>
                );
              })}
            </div>
          </fieldset>
        ))}
      </div>

      <footer className="flex items-center justify-between border-t border-line px-5 py-4">
        <p className="text-xs text-ink-ghost">
          所有问题作答后方可提交；取消将整批作废
        </p>
        <div className="flex gap-2">
          {/* 主次分明：主操作 primary（accent），取消弱化为 ghost */}
          <button
            type="button"
            onClick={() => {
              cancelQuestions(item.id);
            }}
            className={`${btnGhost} px-3 py-1.5 text-sm`}
          >
            取消
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!allAnswered}
            className={`${btnPrimary} px-3 py-1.5 text-sm`}
          >
            提交回答
          </button>
        </div>
      </footer>
    </section>
  );
}
