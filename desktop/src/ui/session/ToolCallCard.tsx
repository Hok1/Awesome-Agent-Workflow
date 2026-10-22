/**
 * 工具调用卡片：
 * - 折叠态一行 = 状态徽标 + 工具名 + 输入一行摘要（摘要由 store 层按
 *   skill-eval wire.py 的优先级算好，组件只渲染）；
 * - 展开态 = 完整 JSON 输入 / 输出（rawOutput 为字符串时按原文呈现）。
 */
import { useState } from "react";
import type { ToolCallItem } from "../../stores/sessionStore.ts";

const statusBadges: Readonly<
  Record<
    NonNullable<ToolCallItem["status"]>,
    { label: string; className: string }
  >
> = {
  pending: { label: "等待", className: "text-ink-mute border-line-strong" },
  in_progress: {
    label: "运行中",
    className: "text-accent-ink border-info-line",
  },
  completed: {
    label: "完成",
    className: "text-ok-ink border-ok-line",
  },
  failed: { label: "失败", className: "text-danger-ink border-danger-line" },
};

/** 未知 / 缺省状态（tool_call 落笔时可能不带 status）。 */
const unknownBadge = {
  label: "已发起",
  className: "text-ink-mute border-line-strong",
};

/** 完整载荷的呈现文本：字符串按原文，其余安全 JSON 美化。 */
function formatPayload(value: unknown): string {
  if (value === undefined || value === null) {
    return "（无）";
  }
  if (typeof value === "string") {
    return value;
  }
  try {
    const text = JSON.stringify(value, null, 2);
    if (typeof text === "string") {
      return text;
    }
  } catch {
    // 循环引用等：落入类型名兜底
  }
  return typeof value;
}

/**
 * 折叠摘要是否与标题重复：chrys 的 title 常由工具名 + 关键参数生成
 * （如 `read_file .sdd/SR-004/state.json`），此时摘要 `path=…` 只是复述。
 * 规则：摘要按 ` · ` 拆段、取各段 `=` 后的值，若值全部出现在标题里
 * 则视为重复，不再展示。
 */
function isSummaryRedundant(title: string, summary: string): boolean {
  if (summary.length === 0) {
    return true;
  }
  const values = summary.split(" · ").map((part) => {
    const eq = part.indexOf("=");
    return eq === -1 ? part : part.slice(eq + 1);
  });
  return values.every((value) => value.length > 0 && title.includes(value));
}

export function ToolCallCard({ item }: { readonly item: ToolCallItem }) {
  const [isOpen, setIsOpen] = useState(false);
  const badge = item.status === null ? unknownBadge : statusBadges[item.status];
  const showSummary = !isSummaryRedundant(item.title, item.inputSummary);
  return (
    <div
      className="w-full overflow-hidden rounded-lg border border-line bg-surface/40"
      data-item-kind="tool"
    >
      <button
        type="button"
        aria-expanded={isOpen}
        onClick={() => {
          setIsOpen((current) => !current);
        }}
        className="flex w-full items-center gap-2.5 px-3 py-1.5 text-left transition-colors hover:bg-surface"
      >
        <span
          className={`shrink-0 rounded border px-1 py-0 text-2xs leading-4 ${badge.className}`}
        >
          {badge.label}
        </span>
        {/* 标题与摘要同行：各自截断省略，标题最多占一半宽度，
            长标题不把摘要挤出卡片 */}
        <span className="max-w-[50%] shrink-0 truncate font-mono text-2xs text-ink">
          {item.title}
        </span>
        {showSummary ? (
          <span
            className="min-w-0 flex-1 truncate font-mono text-2xs text-ink-faint"
            title={item.inputSummary}
          >
            {item.inputSummary}
          </span>
        ) : (
          <span className="min-w-0 flex-1" />
        )}
        <span
          className={`shrink-0 text-2xs text-ink-ghost transition-transform ${isOpen ? "rotate-90" : ""}`}
        >
          ▸
        </span>
      </button>
      {isOpen ? (
        <div className="space-y-2.5 border-t border-line px-3 py-2.5">
          <section aria-label="工具输入">
            <p className="mb-1 text-xs text-ink-faint">输入</p>
            <pre className="max-h-72 overflow-auto rounded bg-base/70 p-2.5 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words text-ink-soft">
              {formatPayload(item.rawInput)}
            </pre>
          </section>
          <section aria-label="工具输出">
            <p className="mb-1 text-xs text-ink-faint">输出</p>
            <pre
              className={`max-h-72 overflow-auto rounded bg-base/70 p-2.5 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words ${item.status === "failed" ? "text-danger-ink" : "text-ink-soft"}`}
            >
              {formatPayload(item.rawOutput)}
            </pre>
          </section>
        </div>
      ) : null}
    </div>
  );
}
