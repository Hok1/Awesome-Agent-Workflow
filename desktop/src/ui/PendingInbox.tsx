/**
 * 待办面板（顶栏「待办」按钮的下拉形态）：列出全部挂起的审批/提问。
 *
 * 多个挂起项并存时在此切换焦点（select），审批弹窗与问答表单渲染
 * 当前焦点项。列表数据与标题均在 approvalStore 定型，组件只渲染；
 * 点选条目后经 onSelect 回调收起下拉（父组件持有开合状态）。
 * 无挂起项时面板不渲染（顶栏按钮同时灰显禁用）。
 */
import { useApprovalStore } from "../stores/approvalStore";
import { Badge } from "./controls";

interface PendingInboxProps {
  /** 点选某条待办（已切换焦点）后的回调（通常用于收起下拉面板）。 */
  readonly onSelect?: () => void;
}

export function PendingInbox({ onSelect }: PendingInboxProps) {
  const pending = useApprovalStore((state) => state.pending);
  const activeId = useApprovalStore((state) => state.activeId);
  const select = useApprovalStore((state) => state.select);

  // 无挂起项：面板不渲染
  if (pending.length === 0) {
    return null;
  }

  return (
    <section
      aria-label="待办中心"
      className="overflow-hidden rounded-lg border border-line-strong bg-surface shadow-xl"
    >
      <header className="flex items-center justify-between border-b border-line px-3 py-2">
        <h2 className="text-xs font-medium text-ink">待办中心</h2>
        <span className="rounded-full bg-raised px-2 py-0.5 text-xs text-ink-soft">
          {pending.length}
        </span>
      </header>

      <ul className="max-h-72 divide-y divide-line overflow-y-auto">
        {pending.map((item) => {
          const isActive = item.id === activeId;
          return (
            <li key={item.id}>
              <button
                type="button"
                onClick={() => {
                  select(item.id);
                  onSelect?.();
                }}
                aria-current={isActive ? "true" : undefined}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left transition-colors ${
                  isActive ? "bg-raised" : "hover:bg-raised/50"
                }`}
              >
                <Badge tone={item.kind === "permission" ? "warn" : "info"}>
                  {item.kind === "permission" ? "审批" : "问答"}
                </Badge>
                <span className="min-w-0 flex-1 truncate text-sm text-ink">
                  {item.inboxTitle}
                </span>
                <span className="shrink-0 font-mono text-xs text-ink-ghost">
                  {item.createdAt.slice(11, 16)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
