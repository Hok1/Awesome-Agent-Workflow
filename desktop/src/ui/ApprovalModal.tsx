/**
 * 审批弹窗：模态展示一条挂起的 `session/request_permission`。
 *
 * 展示工具名（`_meta.chrys.tool_name`）、标题、rawInput 摘要（store 已
 * 定型为 inputSummary）与可选的重审原因；选项按钮按 kind 排序渲染——
 * 允许（主操作）→ 本会话总是允许 → 拒绝（危险操作）→ 未知（中性）。
 * chrys 当前只下发 allow_once / reject_once，allow_always 为协议预留，
 * 出现即自动多一枚按钮。
 *
 * 安全默认：默认焦点落在**拒绝一侧**（无拒绝项时落在排序末位）——权限
 * 请求可能在用户于别处打字途中弹出，缺省焦点绝不能是「允许」，否则
 * 用户下一次 Enter 就等于批准。未知 kind（协议演进/私有方言）以中性
 * 样式呈现 agent 的原始 name，绝不渲染成「允许」。
 *
 * 组件只消费 store 的成品数据与 action（约定见 src/ui/README.md）；
 * 决策、日志与回传全部发生在 approvalStore。
 */
import { useEffect } from "react";
import type { PermissionOptionKind } from "../acp/types";
import {
  PERMISSION_KIND_LABELS,
  useApprovalStore,
} from "../stores/approvalStore";
import type { PendingPermission } from "../stores/approvalStore";
import { Badge, btnDanger, btnPrimary, btnSecondary } from "./controls";

/** 按钮渲染顺序：允许在前，拒绝居后，未知（守卫回落）最后。 */
const KIND_ORDER: Readonly<Record<PermissionOptionKind, number>> = {
  allow_once: 0,
  allow_always: 1,
  reject_once: 2,
  reject_always: 3,
  unknown: 4,
};

export function ApprovalModal({ item }: { readonly item: PendingPermission }) {
  const decidePermission = useApprovalStore((state) => state.decidePermission);
  const cancelPermission = useApprovalStore((state) => state.cancelPermission);

  // Esc = 取消回传（chrys 侧视为未批准，与「拒绝」同样安全）
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent): void {
      if (event.key === "Escape") {
        cancelPermission(item.id);
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [cancelPermission, item.id]);

  const sortedOptions = [...item.options].sort(
    (left, right) => KIND_ORDER[left.kind] - KIND_ORDER[right.kind],
  );

  // 默认焦点 = 第一个拒绝项；无拒绝项时退到排序末位（最不可能被误认
  // 为「确认」的位置），把 Enter 的缺省动作钉在安全一侧
  const firstRejectIndex = sortedOptions.findIndex(
    (option) =>
      option.kind === "reject_once" || option.kind === "reject_always",
  );
  const defaultFocusIndex =
    firstRejectIndex >= 0 ? firstRejectIndex : sortedOptions.length - 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="权限审批"
        className="w-full max-w-lg rounded-lg border border-line-strong bg-surface shadow-xl"
      >
        <div className="border-b border-line px-5 py-4">
          <div className="flex items-center gap-2">
            <Badge tone="warn">权限审批</Badge>
            {item.toolName !== null && (
              <code className="text-xs text-ink-mute">{item.toolName}</code>
            )}
            {item.toolKind !== null && (
              <span className="text-xs text-ink-ghost">{item.toolKind}</span>
            )}
            {/* 来源会话：给待办事件补充上下文（来自哪个会话） */}
            <span
              className="ml-auto truncate font-mono text-2xs text-ink-ghost"
              title={`来源会话 ${item.sessionId}`}
            >
              会话 {item.sessionId}
            </span>
          </div>
          <h2 className="mt-2 text-base font-medium leading-relaxed text-ink">
            {item.title.length > 0 ? item.title : item.toolCallId}
          </h2>
        </div>

        <div className="space-y-3 px-5 py-4">
          {item.reason !== null && item.reason.length > 0 && (
            <p className="text-sm leading-relaxed text-warn-ink">
              原因：{item.reason}
            </p>
          )}
          <div>
            <p className="mb-1 text-xs text-ink-faint">工具输入</p>
            {/* pre-wrap + break-all：长命令（带路径 / --data-file）折行而非溢出 */}
            <pre className="rounded-md border border-line bg-base px-3 py-2 font-mono text-xs leading-relaxed whitespace-pre-wrap break-all text-ink-soft">
              {item.inputSummary.length > 0
                ? item.inputSummary
                : "（无输入参数）"}
            </pre>
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-line px-5 py-4">
          {sortedOptions.map((option, index) => (
            <button
              key={option.optionId}
              type="button"
              autoFocus={index === defaultFocusIndex}
              onClick={() => {
                decidePermission(item.id, option.optionId);
              }}
              title={option.name}
              className={optionButtonClass(option.kind)}
            >
              {/* 未知 kind 呈现 agent 的原始 name（表外语义不猜，绝不
                  显示成「允许」）；已知 kind 用统一中文文案 */}
              {option.kind === "unknown"
                ? `未知（${option.name}）`
                : PERMISSION_KIND_LABELS[option.kind]}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/**
 * 选项按钮样式：允许=primary（accent）；总是允许=secondary；拒绝=danger；
 * 未知=secondary（中性描边，不抢主按钮视觉，也不伪装成危险操作）。
 */
function optionButtonClass(kind: PermissionOptionKind): string {
  const size = "px-3 py-1.5 text-sm";
  switch (kind) {
    case "allow_once":
      return `${btnPrimary} ${size}`;
    case "allow_always":
    case "unknown":
      return `${btnSecondary} ${size}`;
    default:
      return `${btnDanger} ${size}`;
  }
}
