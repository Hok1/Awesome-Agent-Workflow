/**
 * 用户消息：右侧气泡，保留换行。
 *
 * 气泡带一层微弱 accent 底色与描边：发言方不再只靠左右对齐区分，
 * 与灰底的 Agent 消息卡扫视时层级分明（配色走 info 语义 token，
 * 双主题各自取浅/深值）。
 */
import type { UserMessageItem } from "../../stores/sessionStore.ts";

export function UserMessage({ item }: { readonly item: UserMessageItem }) {
  return (
    <div className="flex flex-col items-end gap-1" data-item-kind="user">
      <div className="max-w-[85%] rounded-lg bg-info-bg/60 px-4 py-2.5 text-sm leading-7 break-words text-ink ring-1 ring-info-line/70 ring-inset">
        <p className="whitespace-pre-wrap break-words">{item.text}</p>
      </div>
    </div>
  );
}
