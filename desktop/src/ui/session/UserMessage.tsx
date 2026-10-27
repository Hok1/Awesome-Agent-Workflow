import { memo } from "react";
/**
 * 用户消息：右侧气泡（保留换行）+ hover 浮现的操作行。
 *
 * 操作（弱化呈现，静息不占视觉）：
 * - 「再次发送」：把这条消息填回输入框（可改再发）——ACP 没有消息编辑
 *   语义，诚实的形态是「取回文本」而不是假装原地编辑；
 * - 复制：源文本入剪贴板（CopyButton 自带已复制反馈）。
 */
import type { UserMessageItem } from "../../stores/sessionStore.ts";
import { prefillComposer } from "./composerPrefill.ts";
import { CopyButton } from "./CopyButton.tsx";
import { formatClock } from "./clock.ts";

function UserMessageBase({ item }: { readonly item: UserMessageItem }) {
  return (
    <div className="group flex flex-col items-end gap-1" data-item-kind="user">
      <div
        // hover 时间戳：发送时刻（createdAt 缺省的旧数据不显示）
        title={formatClock(item.createdAt) ?? undefined}
        className="max-w-[85%] rounded-lg bg-info-bg/60 px-4 py-2.5 text-sm leading-6 break-words text-ink ring-1 ring-info-line/70 ring-inset"
      >
        <p className="whitespace-pre-wrap break-words">{item.text}</p>
      </div>
      <div className="flex items-center gap-0.5 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
        <button
          type="button"
          onClick={() => {
            prefillComposer(item.text);
          }}
          aria-label="再次发送"
          title="把这条消息填回输入框，可修改后再发"
          className="rounded px-1.5 py-0.5 text-xs text-ink-faint transition-colors hover:bg-raised hover:text-ink-soft"
        >
          再次发送
        </button>
        <CopyButton getText={() => item.text} label="复制消息" />
      </div>
    </div>
  );
}

/** memo：item 引用不变则整树跳过（流式分片只改最后一条的引用）。 */
export const UserMessage = memo(UserMessageBase);
