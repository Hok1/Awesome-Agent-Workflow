/**
 * 轮内已完成工作组（折叠卡）：一行「▸ 已工作 2m13s · 6 个步骤」，
 * 默认收起（降噪是目的），点开看组内的思考块与工具卡（原样渲染，
 * 由 SessionView 注入 renderItem）。失败的工具卡不进组（排障现场
 * 要一直可见），因此组内永远只有安静的历史。
 */
import type { ReactNode } from "react";
import type { SessionItem } from "../../stores/sessionStore.ts";
import { ChevronRightIcon } from "../icons.tsx";
import { formatDuration } from "./clock.ts";
import type { TurnUnit } from "./turnGrouping.ts";

export function WorkGroupCard({
  unit,
  expanded,
  onToggle,
  renderItem,
}: {
  readonly unit: Extract<TurnUnit, { kind: "work" }>;
  readonly expanded: boolean;
  readonly onToggle: () => void;
  readonly renderItem: (item: SessionItem) => ReactNode;
}) {
  const count = unit.items.length;
  return (
    <div
      className="w-full overflow-hidden rounded-lg border border-line bg-surface/20"
      data-work-group=""
    >
      <button
        type="button"
        aria-expanded={expanded}
        onClick={onToggle}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-ink-faint transition-colors hover:bg-surface hover:text-ink-soft"
      >
        <span
          className={`shrink-0 text-ink-ghost transition-transform ${expanded ? "rotate-90" : ""}`}
        >
          <ChevronRightIcon className="h-3 w-3" />
        </span>
        <span>
          {unit.elapsedMs !== null ? (
            <>已工作 {formatDuration(unit.elapsedMs)} · </>
          ) : null}
          {count} 个步骤
        </span>
        <span className="min-w-0 flex-1" />
      </button>
      {expanded ? (
        <div className="space-y-3 border-t border-line px-3 py-2.5">
          {unit.items.map((item) => (
            <div key={item.id}>{renderItem(item)}</div>
          ))}
        </div>
      ) : null}
    </div>
  );
}
