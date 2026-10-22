/**
 * 输入区（悬浮形态）：不贴边贴底的圆角卡片——外层 `0 20px 16px` 留白，
 * 内部 max-w-4xl 居中，surface 植面 + 圆角 16 + 投影。
 *
 * - 上行：多行文本（透明背景无边框），Enter 发送 / Shift+Enter 换行，
 *   中文输入法组词中的 Enter 不发送；固定初始高度、随内容自动增长
 *   （上限后内部滚动），不暴露原生 resize 手柄；
 * - 下行（border-t 分隔）：左侧模型名短格式（accent 圆点 + 短格式，
 *   悬停见全量）+ 审批模式徽标；右侧圆形发送 / 停止钮——agent 运行中
 *   变「停止」（发取消），空输入与连接建立中禁闭。附件按钮在功能接入
 *   前不占位（看得见却点不动的图标不是入口）。
 */
import { useEffect, useRef, useState, type KeyboardEvent } from "react";

import { useSessionStore } from "../../stores/sessionStore.ts";
import { focusVisibleRing } from "../controls.tsx";

/** 自动增长的高度上限（px）：超过后转入内部滚动。 */
const MAX_HEIGHT_PX = 192;

/** 审批模式徽标配色：手动（琥珀）/ 自动（蓝）/ 全放行（红，提示风险）。 */
const modeBadgeClasses: Readonly<Record<string, string>> = {
  manual: "border-warn-line bg-warn-bg/50 text-warn-ink",
  auto: "border-info-line bg-info-bg/50 text-info-ink",
  bypass: "border-danger-line bg-danger-bg/50 text-danger-ink",
};

/** 模型标识的短格式：裸 hash 只留前 12 位（悬停见全量）。 */
function shortModelLabel(label: string): string {
  return /^[0-9a-f]{16,}$/i.test(label) ? label.slice(0, 12) : label;
}

/** arrow-up：发送（圆形主钮内的箭头）。 */
function ArrowUpIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={true}
      className="h-4 w-4"
    >
      <path d="m5 12 7-7 7 7" />
      <path d="M12 19V5" />
    </svg>
  );
}

/** 停止：运行中的圆形危险钮内的实心方块。 */
function StopIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden={true}
      className="h-3.5 w-3.5"
    >
      <rect x="6" y="6" width="12" height="12" rx="2" />
    </svg>
  );
}

export interface ChatInputProps {
  readonly isAgentRunning: boolean;
  /** ACP 连接建立中：输入与发送一并禁用（无会话可发）。 */
  readonly disabled?: boolean;
  readonly onSend: (text: string) => void;
  readonly onCancel: () => void;
}

export function ChatInput({
  isAgentRunning,
  disabled = false,
  onSend,
  onCancel,
}: ChatInputProps) {
  const [draft, setDraft] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  // 模型与审批模式随会话事件更新，输入区自取（与 SessionView 同源）
  const modelLabel = useSessionStore((state) => state.modelLabel);
  const approvalMode = useSessionStore((state) => state.approvalMode);

  // 自动增长：先瞬时归零再按 scrollHeight 撑开，钳制在 MAX_HEIGHT_PX 内
  useEffect(() => {
    const element = textareaRef.current;
    if (element === null) {
      return;
    }
    element.style.height = "0px";
    element.style.height = `${Math.min(element.scrollHeight, MAX_HEIGHT_PX)}px`;
  }, [draft]);

  const submit = (): void => {
    const trimmed = draft.trim();
    if (trimmed.length === 0 || isAgentRunning || disabled) {
      return;
    }
    onSend(trimmed);
    setDraft("");
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>): void => {
    if (event.key !== "Enter" || event.shiftKey) {
      return;
    }
    // 输入法组词确认的 Enter 不是发送
    if (event.nativeEvent.isComposing) {
      return;
    }
    event.preventDefault();
    submit();
  };

  return (
    /* 悬浮留白：不贴边贴底（左右 20px、底部 16px） */
    <div className="shrink-0" style={{ padding: "0 20px 16px" }}>
      <div className="mx-auto w-full max-w-4xl overflow-hidden rounded-2xl border border-line bg-surface shadow-lg">
        {/* 上行：透明无边框的多行输入 */}
        <div className="px-3.5 pb-1 pt-2.5">
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
            }}
            onKeyDown={handleKeyDown}
            aria-label="消息输入框"
            disabled={disabled}
            placeholder={
              isAgentRunning
                ? "agent 正在处理，可先编辑下一条消息…"
                : "输入消息，Enter 发送，Shift+Enter 换行"
            }
            rows={1}
            className={`max-h-48 min-h-[2.5rem] w-full resize-none overflow-y-auto rounded bg-transparent text-sm leading-6 text-ink placeholder:text-ink-ghost disabled:cursor-not-allowed disabled:opacity-60 ${focusVisibleRing}`}
          />
        </div>
        {/* 下行：左=模型 / 审批模式；右=圆形发送 / 停止钮 */}
        <div className="mt-1 flex items-center gap-1.5 border-t border-line px-2 py-1.5">
          <span
            className="flex min-w-0 items-center gap-1.5 rounded-md px-1.5 py-1 text-xs text-ink-mute"
            title={modelLabel ?? "当前模型"}
          >
            {/* accent 圆点：模型标识的前缀记号 */}
            <span
              aria-hidden={true}
              className="h-1.5 w-1.5 shrink-0 rounded-full bg-sky-500"
            />
            <span className="truncate font-mono">
              {modelLabel === null ? "—" : shortModelLabel(modelLabel)}
            </span>
          </span>
          {approvalMode !== null ? (
            <span
              className={`shrink-0 rounded border px-1.5 py-0.5 text-2xs ${
                modeBadgeClasses[approvalMode.id] ??
                "border-line-strong bg-surface text-ink-mute"
              }`}
              title="审批模式"
            >
              {approvalMode.name}
            </span>
          ) : null}
          <span aria-hidden={true} className="flex-1" />
          {isAgentRunning ? (
            /* 停止：圆形危险钮（同 btnDanger 植面，形状为圆形） */
            <button
              type="button"
              onClick={onCancel}
              aria-label="停止"
              title="停止"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-danger-line bg-danger-bg/40 text-danger-ink transition-colors hover:bg-danger-bg/70"
            >
              <StopIcon />
            </button>
          ) : (
            /* 发送：圆形主钮（同 btnPrimary 植面，形状为圆形） */
            <button
              type="button"
              onClick={submit}
              disabled={disabled || draft.trim().length === 0}
              aria-label="发送"
              title="发送"
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-sky-600 text-white transition-colors hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ArrowUpIcon />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
