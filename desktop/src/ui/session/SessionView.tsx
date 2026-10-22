/**
 * 会话视图：上下文条 + 中央聊天流 + 悬浮输入区（+ 可选的 AAW 侧栏）。
 *
 * - 顶部：上下文条（ContextBar：会话标题 / 项目名 / 连接徽标 / SR 快捷
 *   / 关闭项目，模型与审批模式元信息移至输入区下行）；
 * - 中部：消息流（用户 / 助手 / 思考 / 工具卡 / 系统提示），接近底部时
 *   随内容自动滚动，用户上翻回看则不强制拉底；
 * - 右侧：AAW 增强面板（workbenchUiStore.isAawOpen）——默认收起，由上下文
 *   条的 SR 按钮或会话头「AAW」入口拉起；AAW 是增强，不是会话的前置条件，
 *   所以它按需出现、看完收起，对话始终占满主区；
 * - 底部：ChatInput（Enter 发送，运行中变圆形「停止」钮）。
 *
 * 组件只订阅 sessionStore 的选择器；数据折叠全部在 store 层完成。
 */
import { useEffect, useRef } from "react";
import {
  useSessionStore,
  type SessionItem,
} from "../../stores/sessionStore.ts";
import { useApprovalStore } from "../../stores/approvalStore.ts";
import { useWorkspaceStore } from "../../stores/workspaceStore.ts";
import { useWorkbenchUiStore } from "../../stores/workbenchUiStore.ts";
import { btnPrimary } from "../controls.tsx";
import { AssistantMessage } from "./AssistantMessage.tsx";
import { ChatInput } from "./ChatInput.tsx";
import { Spinner } from "../controls.tsx";
import { openRealWorkspace } from "../realRuntime.ts";
import { SessionAawPanel } from "../workbench/SessionAawPanel.tsx";
import type { WizardSubmitResult } from "../workbench/wizardSubmit.ts";
import { SystemNotice } from "./SystemNotice.tsx";
import { ThoughtBlock } from "./ThoughtBlock.tsx";
import { ToolCallCard } from "./ToolCallCard.tsx";
import { UserMessage } from "./UserMessage.tsx";

export interface SessionViewProps {
  /** AAW 面板内「启动」分段的首条 prompt 发送通路（组装层注入）。 */
  readonly onSubmitAawPrompt?: (
    prompt: string,
  ) => Promise<WizardSubmitResult> | WizardSubmitResult;
}

/** 距底阈值（px）：滚动位置在此范围内才自动跟随新内容。 */
const autoScrollThresholdPx = 80;

/** 无发送通路时向导提交的兜底提示（孤立渲染场景，如实失败不静默）。 */
const NO_SUBMIT_PATH = "当前会话没有可用的发送通道，请重新打开项目后重试";

function SessionItemView({ item }: { readonly item: SessionItem }) {
  switch (item.kind) {
    case "user":
      return <UserMessage item={item} />;
    case "assistant":
      return <AssistantMessage item={item} />;
    case "thought":
      return <ThoughtBlock item={item} />;
    case "tool":
      return <ToolCallCard item={item} />;
    case "system":
      return <SystemNotice item={item} />;
  }
}

export function SessionView({ onSubmitAawPrompt }: SessionViewProps = {}) {
  const items = useSessionStore((state) => state.items);
  const isAgentRunning = useSessionStore((state) => state.isAgentRunning);
  const sendPrompt = useSessionStore((state) => state.sendPrompt);
  const requestCancel = useSessionStore((state) => state.requestCancel);
  // 待办计数：有挂起的审批/提问时不再展示「会话为空」空态，
  // 否则与「会话中」标签及顶栏待办中心自相矛盾（04-approval 评审项）。
  const pendingCount = useApprovalStore((state) => state.pending.length);
  const isConnecting = useSessionStore((state) => state.isConnecting);
  const agentCrashed = useSessionStore((state) => state.agentCrashed);
  const turnError = useSessionStore((state) => state.turnError);
  const clearTurnError = useSessionStore((state) => state.clearTurnError);
  const retryLastPrompt = useSessionStore((state) => state.retryLastPrompt);
  const activePath = useWorkspaceStore((state) => state.activePath);
  // 项目已关闭（activePath 落空）时的空态改为「重新打开项目」入口
  const openWorkspace = useWorkspaceStore((state) => state.openWorkspace);
  const contextPath = useWorkbenchUiStore((state) => state.contextPath);
  const isAawOpen = useWorkbenchUiStore((state) => state.isAawOpen);
  const toggleAaw = useWorkbenchUiStore((state) => state.toggleAaw);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const isNearBottomRef = useRef(true);

  useEffect(() => {
    const element = scrollRef.current;
    if (element !== null && isNearBottomRef.current) {
      element.scrollTop = element.scrollHeight;
    }
  }, [items]);

  const handleScroll = (): void => {
    const element = scrollRef.current;
    if (element === null) {
      return;
    }
    isNearBottomRef.current =
      element.scrollHeight - element.scrollTop - element.clientHeight <=
      autoScrollThresholdPx;
  };

  return (
    <div className="flex h-full min-h-0">
      <section
        aria-label="会话视图"
        className="flex h-full min-h-0 min-w-0 flex-1 flex-col bg-base"
      >
        {agentCrashed !== null ? (
          <div
            role="alert"
            className="flex flex-none flex-wrap items-center gap-3 border-b border-line bg-danger-bg px-4 py-2.5 text-sm text-danger-ink"
          >
            <span className="font-medium">agent 已意外退出</span>
            <span className="text-xs opacity-80">{agentCrashed.reason}</span>
            <span className="flex-1" />
            <button
              type="button"
              onClick={() => {
                if (activePath !== null) {
                  void openRealWorkspace(activePath);
                }
              }}
              className={
                "rounded-md border border-current px-2.5 py-1 text-xs font-medium hover:bg-raised"
              }
            >
              重启并恢复会话
            </button>
            <button
              type="button"
              onClick={() => {
                useWorkbenchUiStore.getState().toggleOverlay("diagnostics");
              }}
              className="rounded-md border border-current px-2.5 py-1 text-xs font-medium hover:bg-raised"
            >
              打开诊断
            </button>
          </div>
        ) : null}
        <div
          ref={scrollRef}
          onScroll={handleScroll}
          role="log"
          aria-live="polite"
          aria-label="消息流"
          className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto px-4 py-4"
        >
          {items.length === 0 && isConnecting ? (
            <div className="flex flex-col items-center justify-center gap-3 py-20 text-sm text-ink-mute">
              <Spinner className="h-6 w-6 text-sky-400" />
              <span>正在连接 agent 并恢复会话上下文…</span>
              <span className="text-xs text-ink-ghost">
                首次启动与恢复通常需要数秒，请稍候
              </span>
            </div>
          ) : items.length === 0 &&
            activePath === null &&
            contextPath !== null ? (
            /* 项目已关闭（无 activePath）：给「重新打开项目」的可行出口，
             替代指路不通的「连接 agent」文案 */
            <div className="flex flex-col items-center gap-3 py-16 text-center">
              <p className="text-sm text-ink-mute">项目已关闭</p>
              <button
                type="button"
                onClick={() => {
                  openWorkspace(contextPath);
                }}
                className={`${btnPrimary} px-3 py-1.5 text-sm`}
              >
                重新打开项目
              </button>
              <p className="text-xs text-ink-ghost">
                将重新连接 agent 并恢复该项目的会话。
              </p>
            </div>
          ) : items.length === 0 ? (
            pendingCount > 0 ? (
              <p className="py-16 text-center text-sm leading-relaxed text-ink-faint">
                会话暂无消息，当前有 {pendingCount}{" "}
                项审批/提问待处理——请回应弹窗，或在顶栏「待办」列表中处理。
              </p>
            ) : (
              <p className="py-16 text-center text-sm text-ink-ghost">
                会话为空。发送第一条消息即可开始。
              </p>
            )
          ) : (
            <ol className="mx-auto flex max-w-4xl list-none flex-col gap-4 p-0">
              {items.map((item) => (
                <li key={item.id}>
                  <SessionItemView item={item} />
                </li>
              ))}
            </ol>
          )}
        </div>
        {turnError !== null && !isAgentRunning ? (
          <div
            role="alert"
            className="mx-auto mb-2 flex w-full max-w-4xl flex-wrap items-center gap-3 rounded-lg border border-line bg-surface px-4 py-2.5 text-sm text-danger-ink"
          >
            <span className="font-medium">
              {turnError.category === "auth"
                ? "模型或密钥配置异常"
                : turnError.category === "timeout"
                  ? "请求超时"
                  : "请求失败"}
            </span>
            <span
              className="min-w-0 flex-1 truncate text-xs text-ink-mute"
              title={turnError.message}
            >
              {turnError.message}
            </span>
            <button
              type="button"
              onClick={retryLastPrompt}
              className={
                "rounded-md border border-line-strong px-2.5 py-1 text-xs font-medium text-ink hover:border-ink-faint hover:bg-raised"
              }
            >
              重试
            </button>
            {turnError.category === "auth" ? (
              <button
                type="button"
                onClick={() => {
                  useWorkbenchUiStore.getState().toggleOverlay("settings");
                }}
                className="rounded-md border border-line-strong px-2.5 py-1 text-xs font-medium text-ink hover:border-ink-faint hover:bg-raised"
              >
                打开设置
              </button>
            ) : null}
            <button
              type="button"
              aria-label="关闭错误提示"
              onClick={clearTurnError}
              className="rounded px-1.5 text-ink-faint hover:text-ink"
            >
              ✕
            </button>
          </div>
        ) : null}
        <ChatInput
          isAgentRunning={isAgentRunning}
          disabled={isConnecting}
          onSend={sendPrompt}
          onCancel={requestCancel}
        />
      </section>
      {/* AAW 增强面板：默认收起，按需展开；展开时对话仍占主区。
          未注入发送通路时（孤立渲染 / 测试）给一个如实失败的兜底，
          不让开关变成没反应的死按钮 */}
      {isAawOpen ? (
        <SessionAawPanel
          onSubmitAawPrompt={
            onSubmitAawPrompt ?? (() => ({ ok: false, reason: NO_SUBMIT_PATH }))
          }
          onClose={toggleAaw}
        />
      ) : null}
    </div>
  );
}
