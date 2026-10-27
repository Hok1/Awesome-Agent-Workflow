import { memo } from "react";
/**
 * 助手消息：Markdown 渲染 + 流式指示 + 整条复制（复制 Markdown 源文本）。
 */
import type { AssistantMessageItem } from "../../stores/sessionStore.ts";
import { CopyButton } from "./CopyButton.tsx";
import { formatClock } from "./clock.ts";
import { MarkdownView } from "./MarkdownView.tsx";

function AssistantMessageBase({
  item,
}: {
  readonly item: AssistantMessageItem;
}) {
  return (
    // group：复制按钮随卡片 hover 浮现，不再常驻制造噪音
    <div
      className="group flex flex-col items-start gap-1"
      data-item-kind="assistant"
    >
      <div className="flex w-full items-center justify-between">
        <div className="flex items-center gap-2">
          <span
            className="text-xs font-medium text-ink-mute"
            // hover 时间戳：消息落笔时刻；旧快照无时刻则不显示
            title={formatClock(item.createdAt) ?? undefined}
          >
            Agent
          </span>
          {item.isStreaming ? (
            <span
              className="flex items-center gap-1 text-xs text-accent-ink"
              role="status"
            >
              <span className="inline-block size-1.5 animate-pulse rounded-full bg-sky-400" />
              生成中…
            </span>
          ) : null}
        </div>
        <CopyButton
          getText={() => item.text}
          label="复制消息"
          iconOnly={true}
          revealOnHover={true}
        />
      </div>
      <div className="w-full rounded-lg border border-line bg-surface/60 px-4 py-3">
        <MarkdownView text={item.text} />
      </div>
    </div>
  );
}

/** memo：item 引用不变则整树跳过（流式分片只改最后一条的引用）。 */
export const AssistantMessage = memo(AssistantMessageBase);
