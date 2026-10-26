/**
 * 思考过程（agent_thought_chunk）：默认折叠，点击展开。
 *
 * 流式中的标题写「思考中…」（配动点）——状态要能被一眼读到，而不是只有
 * 一枚无文字的灰点；流式结束后折叠行给思考耗时（store 记录的起止时刻，
 * 快照恢复的历史条目没有时刻则不显示）。
 */
import { useState } from "react";
import type { ThoughtItem } from "../../stores/sessionStore.ts";
import { ChevronRightIcon } from "../icons.tsx";

/** 毫秒 → 人读时长（<1s 保留一位小数，其余取整）。 */
function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${(ms / 1000).toFixed(1)}s`;
  }
  if (ms < 60_000) {
    return `${Math.round(ms / 1000)}s`;
  }
  const minutes = Math.floor(ms / 60_000);
  return `${minutes}m${Math.round((ms % 60_000) / 1000)}s`;
}

export function ThoughtBlock({ item }: { readonly item: ThoughtItem }) {
  const [isOpen, setIsOpen] = useState(false);
  const durationMs =
    item.startedAt !== null && item.endedAt !== null
      ? Math.max(0, item.endedAt - item.startedAt)
      : null;
  return (
    <div className="w-full" data-item-kind="thought">
      <button
        type="button"
        aria-expanded={isOpen}
        onClick={() => {
          setIsOpen((current) => !current);
        }}
        className="flex items-center gap-2 text-xs text-ink-faint transition-colors hover:text-ink-soft"
      >
        <span
          className={`inline-block transition-transform ${isOpen ? "rotate-90" : ""}`}
        >
          <ChevronRightIcon className="h-3 w-3" />
        </span>
        {item.isStreaming ? (
          <span className="flex items-center gap-1.5 text-ink-soft">
            <span className="inline-block size-1.5 animate-pulse rounded-full bg-ink-faint" />
            思考中…
          </span>
        ) : (
          <span>思考过程</span>
        )}
        {durationMs !== null && !item.isStreaming ? (
          <span className="text-2xs text-ink-ghost">
            {formatDuration(durationMs)}
          </span>
        ) : null}
      </button>
      {isOpen ? (
        <p className="mt-1.5 border-l-2 border-line pl-3 text-xs leading-6 whitespace-pre-wrap break-words text-ink-faint">
          {item.text}
        </p>
      ) : null}
    </div>
  );
}
