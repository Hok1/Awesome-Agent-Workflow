/**
 * 工具调用卡片：
 * - 折叠态一行 = 状态徽标（运行中带脉动点）+ 工具类型小标 + 工具名 +
 *   摘要（输入摘要与结果摘要由 store 层算好，组件只渲染；有结果后优先
 *   展示结果一行）+ 耗时（运行中实时跳动，终态定格；旧快照缺时刻不显示）；
 * - 展开态按工具类型定制：edit 类输入段替换为 diff/新内容预览
 *   （EditDiffView，批准前一眼看到改成什么），execute 类输出段替换为
 *   终端视图（TerminalOutput：5 行窗口 + 吸底跟随 + 上滚冻结）；
 *   其余保持完整 JSON 输入 / 输出，输入 / 输出段各带复制按钮；
 * - 运行中展开盯进度的卡，跑完**自动收起**（长轮次里盯过就还回去，
 *   不让历史工具卡把会话撑爆）；失败的保持展开——原因需要被人看到。
 */
import { useEffect, useMemo, useRef, useState } from "react";
import type { ToolCallItem } from "../../stores/sessionStore.ts";
import { ChevronRightIcon } from "../icons.tsx";
import { formatClock, formatDuration } from "./clock.ts";
import { CopyButton } from "./CopyButton.tsx";
import { extractEditPayload } from "./editDiff.ts";
import { EditDiffView } from "./EditDiffView.tsx";
import { TerminalOutput } from "./TerminalOutput.tsx";

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

/** 工具类型小标（read/edit/execute/search/fetch/other）。 */
const kindLabels: Readonly<Record<string, string>> = {
  read: "读",
  edit: "写",
  execute: "执行",
  search: "搜索",
  fetch: "抓取",
  other: "工具",
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

/** 耗时标签：运行中每秒跳动（首个整秒后出现），终态定格为总耗时；
 *  无时刻（旧快照）不渲染。Date.now 只出现在定时器回调里，渲染保持纯函数。 */
function ElapsedLabel({
  item,
  isRunning,
}: {
  readonly item: ToolCallItem;
  readonly isRunning: boolean;
}) {
  const [now, setNow] = useState<number | null>(null);
  const startedAt = item.startedAt;
  const endedAt = item.endedAt;
  useEffect(() => {
    if (!isRunning || startedAt === null) {
      return;
    }
    const timer = setInterval(() => {
      setNow(Date.now());
    }, 1000);
    return () => {
      clearInterval(timer);
    };
  }, [isRunning, startedAt]);
  if (startedAt === null) {
    return null;
  }
  // pending（等待批准）不算工作耗时：运行中按最近跳动时刻，终态按定格终点
  const end = isRunning ? now : endedAt;
  if (end === null) {
    return null;
  }
  return (
    <span
      className="shrink-0 font-mono text-2xs text-ink-ghost"
      title={isRunning ? "已运行时长" : "总耗时"}
    >
      {formatDuration(Math.max(0, end - startedAt))}
    </span>
  );
}

export function ToolCallCard({ item }: { readonly item: ToolCallItem }) {
  const [isOpen, setIsOpen] = useState(false);
  // 运行中→完成的瞬变自动收起（失败不收：输出是排障现场）
  const prevStatusRef = useRef(item.status);
  useEffect(() => {
    const previous = prevStatusRef.current;
    prevStatusRef.current = item.status;
    if (previous === "in_progress" && item.status === "completed") {
      setIsOpen(false);
    }
  }, [item.status]);
  const badge = item.status === null ? unknownBadge : statusBadges[item.status];
  const isRunning = item.status === "in_progress" || item.status === null;
  // 摘要优先级：有结果给结果行（完成/失败的结论比输入重要），无结果给输入行
  const hasResult =
    item.status === "completed" || item.status === "failed"
      ? item.resultSummary.length > 0
      : false;
  const summaryText = hasResult ? item.resultSummary : item.inputSummary;
  const summaryRedundant = hasResult
    ? false
    : isSummaryRedundant(item.title, item.inputSummary);
  const kindLabel =
    item.toolKind === null ? null : (kindLabels[item.toolKind] ?? "工具");
  // edit 类的改动载荷：形状认识则输入段让位给 diff 视图，否则回落 JSON
  const editPayload = useMemo(
    () => (item.toolKind === "edit" ? extractEditPayload(item.rawInput) : null),
    [item.toolKind, item.rawInput],
  );
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
        // hover 时间戳：发起时刻（HH:MM:SS）；旧快照无时刻则不显示
        title={formatClock(item.startedAt) ?? undefined}
        className="flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-surface"
      >
        <span
          className={`flex shrink-0 items-center gap-1 rounded border px-1 py-0 text-2xs leading-4 ${badge.className}`}
        >
          {isRunning ? (
            <span className="inline-block size-1 animate-pulse rounded-full bg-current" />
          ) : null}
          {badge.label}
        </span>
        {kindLabel !== null ? (
          <span className="shrink-0 rounded bg-base px-1 py-0 text-2xs leading-4 text-ink-faint">
            {kindLabel}
          </span>
        ) : null}
        {/* 标题与摘要同行：各自截断省略，标题最多占一半宽度，
            长标题不把摘要挤出卡片 */}
        <span className="max-w-[50%] shrink-0 truncate font-mono text-2xs text-ink">
          {item.title}
        </span>
        {!summaryRedundant && summaryText.length > 0 ? (
          <span
            className={`min-w-0 flex-1 truncate font-mono text-2xs ${hasResult ? (item.status === "failed" ? "text-danger-ink/80" : "text-ink-faint") : "text-ink-faint"}`}
            title={summaryText}
          >
            {summaryText}
          </span>
        ) : (
          <span className="min-w-0 flex-1" />
        )}
        <ElapsedLabel item={item} isRunning={isRunning} />
        <ChevronRightIcon
          className={`h-3 w-3 shrink-0 text-ink-ghost transition-transform ${isOpen ? "rotate-90" : ""}`}
        />
      </button>
      {isOpen ? (
        <div className="space-y-2.5 border-t border-line px-3 py-2.5">
          {editPayload !== null ? (
            // edit 类：输入段由 diff/新内容预览替代（批准前一眼看到改成什么）
            <section aria-label="工具改动" className="group">
              <div className="mb-1 flex items-center justify-between text-xs text-ink-faint">
                <p>改动</p>
                <CopyButton
                  getText={() => formatPayload(item.rawInput)}
                  label="复制输入"
                  iconOnly={true}
                  revealOnHover={true}
                />
              </div>
              <EditDiffView payload={editPayload} />
            </section>
          ) : (
            <section aria-label="工具输入" className="group">
              <div className="mb-1 flex items-center justify-between text-xs text-ink-faint">
                <p>输入</p>
                <CopyButton
                  getText={() => formatPayload(item.rawInput)}
                  label="复制输入"
                  iconOnly={true}
                  revealOnHover={true}
                />
              </div>
              <pre className="max-h-72 overflow-auto rounded bg-base/70 p-2.5 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words text-ink-soft">
                {formatPayload(item.rawInput)}
              </pre>
            </section>
          )}
          <section aria-label="工具输出" className="group">
            <div className="mb-1 flex items-center justify-between text-xs text-ink-faint">
              <p>输出</p>
              <CopyButton
                getText={() => formatPayload(item.rawOutput)}
                label="复制输出"
                iconOnly={true}
                revealOnHover={true}
              />
            </div>
            {item.toolKind === "execute" ? (
              // execute 类：终端输出视图（5 行窗口 + 吸底跟随 + 上滚冻结）
              <TerminalOutput
                text={formatPayload(item.rawOutput)}
                failed={item.status === "failed"}
              />
            ) : (
              <pre
                className={`max-h-72 overflow-auto rounded bg-base/70 p-2.5 font-mono text-xs leading-relaxed whitespace-pre-wrap break-words ${item.status === "failed" ? "text-danger-ink" : "text-ink-soft"}`}
              >
                {formatPayload(item.rawOutput)}
              </pre>
            )}
          </section>
        </div>
      ) : null}
    </div>
  );
}
