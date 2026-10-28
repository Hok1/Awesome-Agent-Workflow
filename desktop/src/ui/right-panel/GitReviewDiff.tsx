import { useEffect, useRef, useState } from "react";
import type { ReviewMatch, ReviewModel } from "../../core/gitReview.ts";

export function GitReviewDiff({
  model,
  query = "",
  match,
  navigation = 0,
  onLocate,
}: {
  model: ReviewModel;
  query?: string;
  match?: ReviewMatch;
  navigation?: number;
  onLocate?: (element: HTMLElement) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [expanded, setExpanded] = useState<ReadonlySet<number>>(new Set());
  const [page, setPage] = useState(0);
  const needle = query.trim().toLocaleLowerCase();
  const pageStart = match ? Math.floor(match.row / 1000) * 1000 : page;
  useEffect(() => {
    const target = match
      ? ref.current?.querySelector<HTMLElement>('[data-current-hit="true"]')
      : null;
    if (target) {
      if (onLocate) onLocate(target);
      else target.scrollIntoView?.({ block: "center", inline: "nearest" });
    }
  }, [match, navigation, pageStart, onLocate]);
  const rows = model.rows;
  const displayed = [];
  for (let i = pageStart; i < Math.min(rows.length, pageStart + 1000); i++) {
    const row = rows[i];
    if (!row) continue;
    if (row.hidden && !needle && !expanded.has(i)) {
      const start = i;
      while (
        i + 1 < Math.min(rows.length, pageStart + 1000) &&
        rows[i + 1]?.hidden &&
        !expanded.has(i + 1)
      )
        i++;
      const end = i;
      displayed.push(
        <button
          key={`context-${start}`}
          className="block w-full bg-info-bg/30 px-3 py-1 text-left text-ink-faint"
          onClick={() =>
            setExpanded((old) => {
              const next = new Set(old);
              for (let n = start; n <= end; n++) next.add(n);
              return next;
            })
          }
        >
          展开 {end - start + 1} 行未修改内容
        </button>,
      );
      continue;
    }
    const text = row.kind === "meta" ? row.text : row.text.slice(1);
    const parts = [];
    let from = 0;
    if (needle && row.kind !== "meta") {
      const lower = text.toLocaleLowerCase();
      for (
        let start = lower.indexOf(needle);
        start !== -1;
        start = lower.indexOf(needle, start + needle.length)
      ) {
        parts.push(text.slice(from, start));
        const current = match?.row === i && match.start === start;
        parts.push(
          <mark
            key={start}
            data-current-hit={current || undefined}
            className={
              current
                ? "bg-amber-400 text-black outline-2 outline-amber-600"
                : "bg-yellow-200 text-black"
            }
          >
            {text.slice(start, start + needle.length)}
          </mark>,
        );
        from = start + needle.length;
      }
    }
    parts.push(text.slice(from));
    displayed.push(
      <div
        key={i}
        className={`flex ${row.kind === "add" ? "bg-ok-bg/50" : row.kind === "del" ? "bg-danger-bg/50" : row.kind === "meta" ? "bg-info-bg/30 text-ink-faint" : ""}`}
      >
        <span className="w-10 shrink-0 select-none pr-2 text-right text-ink-faint">
          {row.old}
        </span>
        <span className="w-10 shrink-0 select-none pr-2 text-right text-ink-faint">
          {row.next}
        </span>
        <span className="w-4 shrink-0 select-none">
          {row.kind === "add" ? "+" : row.kind === "del" ? "−" : ""}
        </span>
        <code className="whitespace-pre pr-3">{parts}</code>
      </div>,
    );
  }
  return (
    <div
      ref={ref}
      aria-label="Git 统一差异"
      className="overflow-x-auto font-mono text-xs leading-6"
    >
      {pageStart > 0 && !match && (
        <button
          className="p-2 text-accent-ink"
          onClick={() => setPage(Math.max(0, pageStart - 1000))}
        >
          上一段
        </button>
      )}
      <div className="w-max min-w-full">{displayed}</div>
      {pageStart + 1000 < rows.length && !match && (
        <button
          className="p-2 text-accent-ink"
          onClick={() => setPage(pageStart + 1000)}
        >
          下一段（共 {rows.length} 行）
        </button>
      )}
    </div>
  );
}
