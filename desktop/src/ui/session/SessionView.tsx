/**
 * 会话视图：上下文条 + 中央聊天流 + 悬浮输入区（+ 可选的 AAW 侧栏）。
 *
 * - 顶部：上下文条（ContextBar：会话标题 / 项目名 / 连接徽标 / SR 快捷
 *   / 关闭会话，模型与审批模式元信息移至输入区下行）；
 * - 中部：消息流（用户 / 助手 / 思考 / 工具卡 / 系统提示）——**窗口化
 *   渲染**：只挂最近 WINDOW_CHUNK 条，滚动到顶按块向前补载（锚定补载：
 *   前插不把视口顶飞）；**跟随状态机**：贴底时新内容自动滚入，用户上翻
 *   即解除跟随并浮出「回到底部」按钮（带未读新消息计数），回底即恢复
 *   跟随——长会话回看与追新互不打架；
 * - 右侧：AAW 增强面板（workbenchUiStore.isAawOpen）——默认收起，由上下文
 *   条的 SR 按钮或会话头「AAW」入口拉起；AAW 是增强，不是会话的前置条件，
 *   所以它按需出现、看完收起，对话始终占满主区；
 * - 底部：ChatInput（Enter 发送，运行中变圆形「停止」钮；↑/↓ 历史、
 *   @ 文件提及、预填通道见其文件头）；
 * - 空会话：给出常用入口 chips（点击预填输入框，过目后自己发送）；
 * - 时间线 / 消息流 / AAW 面板各自挂局部错误边界：单块崩不白屏全局。
 *
 * 组件只订阅 sessionStore 的选择器；数据折叠全部在 store 层完成。
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  useSessionStore,
  type SessionItem,
} from "../../stores/sessionStore.ts";
import { useApprovalStore } from "../../stores/approvalStore.ts";
import { useWorkspaceStore } from "../../stores/workspaceStore.ts";
import { useWorkbenchUiStore } from "../../stores/workbenchUiStore.ts";
import { useAawStatusStore } from "../../stores/aawStatusStore.ts";
import {
  chatWidthClassOf,
  chatWidthOptions,
  useSettingsStore,
} from "../../stores/settingsStore.ts";
import { btnPrimary } from "../controls.tsx";
import { ScopedErrorBoundary } from "../ErrorBoundary.tsx";
import {
  ArrowDownToLineIcon,
  SparkleIcon,
  WidthFullIcon,
  WidthStandardIcon,
  WidthWideIcon,
  XIcon,
} from "../icons.tsx";
import { AssistantMessage } from "./AssistantMessage.tsx";
import { ChatInput } from "./ChatInput.tsx";
import { PlanCard } from "./PlanCard.tsx";
import { QuestionDock } from "./QuestionDock.tsx";
import { QueueDock } from "./QueueDock.tsx";
import { SessionDock } from "./SessionDock.tsx";
import { TurnStatusRow } from "./InputStatusBar.tsx";
import { Spinner } from "../controls.tsx";
import { openRealWorkspace } from "../realRuntime.ts";
import { SessionAawPanel } from "../workbench/SessionAawPanel.tsx";
import { AawTimeline } from "../workbench/timeline/AawTimeline.tsx";
import type { WizardSubmitResult } from "../workbench/wizardSubmit.ts";
import { prefillComposer } from "./composerPrefill.ts";
import { SystemNotice } from "./SystemNotice.tsx";
import { ThoughtBlock } from "./ThoughtBlock.tsx";
import { ToolCallCard } from "./ToolCallCard.tsx";
import { groupTurnWork } from "./turnGrouping.ts";
import { WorkGroupCard } from "./WorkGroupCard.tsx";
import {
  isNearBottom,
  shouldLoadOlder,
  sliceVisible,
  WINDOW_CHUNK,
} from "./sessionWindow.ts";
import { UserMessage } from "./UserMessage.tsx";

export interface SessionViewProps {
  /** AAW 面板内「启动」分段的首条 prompt 发送通路（组装层注入）。 */
  readonly onSubmitAawPrompt?: (
    prompt: string,
  ) => Promise<WizardSubmitResult> | WizardSubmitResult;
}

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
    case "plan":
      return <PlanCard item={item} />;
    case "system":
      return <SystemNotice item={item} />;
  }
}

/** 时段问候（hero 主标题的一部分；测试以系统时间驱动）。 */
function greetingOfHour(hour: number): string {
  if (hour < 5) {
    return "夜深了";
  }
  if (hour < 9) {
    return "早上好";
  }
  if (hour < 12) {
    return "上午好";
  }
  if (hour < 14) {
    return "中午好";
  }
  if (hour < 18) {
    return "下午好";
  }
  return "晚上好";
}

/** 空会话的 hero（借 ZCode 的空态设计语言）：时段问候 + 一句主旨 +
 * 常用入口 chips（点击预填输入框，过目可改，再自己发送）。 */
function EmptyPrompts({ currentSr }: { readonly currentSr: string | null }) {
  const prompts =
    currentSr !== null
      ? [
          {
            label: `汇报 ${currentSr} 进度`,
            text: `请汇报 ${currentSr} 工作流的当前进度与下一步安排。`,
          },
          { label: "介绍这个项目", text: "请介绍当前项目的结构与主要功能。" },
          {
            label: "梳理可继续的事项",
            text: "请根据当前项目状态，梳理可以继续推进的事项。",
          },
        ]
      : [
          {
            label: "启动一条工作流",
            text: "请从 sr 入口新建一条 AAW 工作流，先与我确认需求。",
          },
          { label: "介绍这个项目", text: "请介绍当前项目的结构与主要功能。" },
          {
            label: "梳理可继续的事项",
            text: "请根据当前项目状态，梳理可以继续推进的事项。",
          },
        ];
  return (
    <div className="flex flex-col items-center gap-4 py-16 text-center">
      <p
        aria-hidden={true}
        className="flex items-center gap-1.5 text-2xs tracking-widest text-ink-faint"
      >
        <SparkleIcon className="h-3.5 w-3.5" />
        AAW
      </p>
      <h2 className="text-lg font-medium text-ink">
        {greetingOfHour(new Date().getHours())}，今天想推进什么？
      </h2>
      <div className="flex flex-wrap items-center justify-center gap-2">
        {prompts.map((prompt, index) => (
          <button
            key={prompt.label}
            type="button"
            style={{ animationDelay: `${index * 60}ms` }}
            onClick={() => {
              prefillComposer(prompt.text);
            }}
            className="chip-in lift press rounded-full border border-line-strong bg-surface px-3.5 py-1.5 text-xs text-ink-mute shadow-elev-1 hover:border-ink-faint hover:text-ink"
          >
            {prompt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function SessionView({ onSubmitAawPrompt }: SessionViewProps = {}) {
  const items = useSessionStore((state) => state.items);
  const isAgentRunning = useSessionStore((state) => state.isAgentRunning);
  const sendPrompt = useSessionStore((state) => state.sendPrompt);
  const enqueuePrompt = useSessionStore((state) => state.enqueuePrompt);
  const requestCancel = useSessionStore((state) => state.requestCancel);
  const activeSessionId = useSessionStore((state) => state.activeSessionId);
  // 挂起计数：有挂起的审批/提问时不再展示「会话为空」空态，
  // 否则与「会话中」标签及弹出的审批模态自相矛盾（04-approval 评审项）。
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
  const currentSr = useAawStatusStore((state) => state.currentSr);
  // 内容宽度档：消息流 / 输入卡 / 停靠坞共用（对齐），就地三档循环
  const chatWidth = useSettingsStore((state) => state.chatWidth);
  const setChatWidth = useSettingsStore((state) => state.setChatWidth);
  const widthClass = chatWidthClassOf(chatWidth);
  const nextWidth =
    chatWidthOptions[
      (chatWidthOptions.findIndex((o) => o.value === chatWidth) + 1) %
        chatWidthOptions.length
    ]?.value ?? "standard";

  // ---- 消息流窗口化 + 跟随状态机 ----
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const [visibleCount, setVisibleCount] = useState(WINDOW_CHUNK);
  const [isFollowing, setIsFollowing] = useState(true);
  const [unseenCount, setUnseenCount] = useState(0);
  const lastLengthRef = useRef(0);
  // 补载锚：loadOlder 前的「距底距离」，补载渲染后恢复（前插不顶飞视口）
  const prependAnchorRef = useRef<number | null>(null);
  // 工作组的展开态（默认全收起——降噪是目的）：会话清空 / 切换时一并复位
  const [openGroups, setOpenGroups] = useState<ReadonlySet<string>>(
    () => new Set(),
  );

  const visibleItems = sliceVisible(items, visibleCount);
  // 轮内已完成工作折叠（作用于窗口化切片之后，不碰锚定与跟随）
  const visibleUnits = useMemo(
    () => groupTurnWork(visibleItems),
    [visibleItems],
  );

  // ---- Esc 全局停止：agent 运行中按 Esc 直接取消当前轮 ----
  // 让位规则（不误停）：IME 组词中；mention 面板 / 审批弹窗 / 提问面板 /
  // 关闭确认 / 项目添加浮层 / 覆盖页 / 时间线抽屉打开时——前四者各自
  // preventDefault 消费掉 Esc，这里按 defaultPrevented 让位；后三者按
  // 状态判断让位。按下的目标在输入框内（含正在编辑的草稿）也照停——
  // 「运行中一律停止」是评审确认的行为。
  useEffect(() => {
    if (!isAgentRunning) {
      return;
    }
    function handleKeyDown(event: KeyboardEvent): void {
      if (
        event.key !== "Escape" ||
        event.defaultPrevented ||
        event.isComposing
      ) {
        return;
      }
      if (useApprovalStore.getState().pending.length > 0) {
        return;
      }
      const ui = useWorkbenchUiStore.getState();
      if (ui.overlay !== null || !ui.isTimelineCollapsed) {
        return;
      }
      event.preventDefault();
      requestCancel();
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isAgentRunning, requestCancel]);

  useEffect(() => {
    const previous = lastLengthRef.current;
    lastLengthRef.current = items.length;
    if (items.length < previous) {
      // 会话清空 / 切换：窗口与跟随态复位
      setVisibleCount(WINDOW_CHUNK);
      setIsFollowing(true);
      setUnseenCount(0);
      setOpenGroups(new Set());
      return;
    }
    if (items.length > previous && !isFollowing) {
      setUnseenCount((count) => count + (items.length - previous));
    }
    if (isFollowing) {
      const element = scrollRef.current;
      if (element !== null) {
        element.scrollTop = element.scrollHeight;
      }
    }
  }, [items, isFollowing]);

  // 锚定补载：前插渲染完成后按「距底距离不变」恢复滚动位置
  useLayoutEffect(() => {
    const anchor = prependAnchorRef.current;
    const element = scrollRef.current;
    if (anchor === null || element === null) {
      return;
    }
    prependAnchorRef.current = null;
    element.scrollTop = element.scrollHeight - anchor;
  }, [visibleCount]);

  const handleScroll = (): void => {
    const element = scrollRef.current;
    if (element === null) {
      return;
    }
    const nearBottom = isNearBottom(
      element.scrollTop,
      element.scrollHeight,
      element.clientHeight,
    );
    if (nearBottom) {
      if (!isFollowing) {
        setIsFollowing(true);
        setUnseenCount(0);
      }
    } else if (isFollowing) {
      setIsFollowing(false);
    }
    if (
      prependAnchorRef.current === null &&
      shouldLoadOlder(element.scrollTop, items.length - visibleCount)
    ) {
      prependAnchorRef.current = element.scrollHeight - element.scrollTop;
      setVisibleCount((count) => Math.min(items.length, count + WINDOW_CHUNK));
    }
  };

  const backToBottom = (): void => {
    const element = scrollRef.current;
    if (element !== null) {
      if (typeof element.scrollTo === "function") {
        // 平滑回底（跟随滚入保持直跳，流式内容不拖影）
        element.scrollTo({ top: element.scrollHeight, behavior: "smooth" });
      } else {
        element.scrollTop = element.scrollHeight;
      }
    }
    setIsFollowing(true);
    setUnseenCount(0);
  };

  return (
    <div className="flex h-full min-h-0">
      <section
        aria-label="会话视图"
        className="flex h-full min-h-0 min-w-0 flex-1 flex-col bg-base"
      >
        <ScopedErrorBoundary
          scope="流程时间线"
          resetKey={contextPath ?? "none"}
        >
          <AawTimeline />
        </ScopedErrorBoundary>
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
        {/* 消息流：窗口化渲染（最近 WINDOW_CHUNK 条，贴顶补载）+ 跟随
            状态机（贴底自动滚入；上翻解除并给回底按钮）；relative 承载
            回底按钮 */}
        <div className="relative min-h-0 flex-1">
          {/* 宽度切换：右上角图标按钮三档循环（标准 / 宽 / 全宽），档位持久化 */}
          <button
            type="button"
            aria-label={`内容宽度：${
              chatWidthOptions.find((option) => option.value === chatWidth)?.label ?? "标准"
            }`}
            title={`内容宽度：${
              chatWidthOptions.find((option) => option.value === chatWidth)?.label ?? "标准"
            }（点击切换为${
              chatWidthOptions.find((option) => option.value === nextWidth)?.label ?? "标准"
            }）`}
            onClick={() => {
              setChatWidth(nextWidth);
            }}
            className="absolute right-3 top-2 z-10 rounded-md border border-line bg-surface/80 p-1 text-ink-faint backdrop-blur transition-colors hover:border-ink-faint hover:text-ink-soft"
          >
            {chatWidth === "wide" ? (
              <WidthWideIcon className="h-3.5 w-3.5" />
            ) : chatWidth === "full" ? (
              <WidthFullIcon className="h-3.5 w-3.5" />
            ) : (
              <WidthStandardIcon className="h-3.5 w-3.5" />
            )}
          </button>
          <div
            ref={scrollRef}
            onScroll={handleScroll}
            role="log"
            aria-live="polite"
            aria-label="消息流"
            className="h-full overflow-x-hidden overflow-y-auto px-6 py-5"
          >
            <ScopedErrorBoundary
              scope="消息流"
              resetKey={activeSessionId ?? "none"}
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
                    项审批/提问待处理——请回应弹窗或停靠面板中的提问。
                  </p>
                ) : (
                  <EmptyPrompts currentSr={currentSr} />
                )
              ) : (
                <ol className={`mx-auto flex list-none flex-col gap-5 p-0 ${widthClass}`}>
                  {visibleUnits.map((unit) =>
                    unit.kind === "item" ? (
                      <li key={unit.id}>
                        <SessionItemView item={unit.item} />
                      </li>
                    ) : (
                      <li key={unit.id}>
                        <WorkGroupCard
                          unit={unit}
                          expanded={openGroups.has(unit.id)}
                          onToggle={() => {
                            setOpenGroups((current) => {
                              const next = new Set(current);
                              if (next.has(unit.id)) {
                                next.delete(unit.id);
                              } else {
                                next.add(unit.id);
                              }
                              return next;
                            });
                          }}
                          renderItem={(item) => (
                            <SessionItemView item={item} />
                          )}
                        />
                      </li>
                    ),
                  )}
                  {/* 轮次相位行长在消息流末尾：思考中 / 工具运行中 n / 生成中 */}
                  <TurnStatusRow />
                </ol>
              )}
            </ScopedErrorBoundary>
          </div>
          {!isFollowing && items.length > 0 ? (
            <button
              type="button"
              onClick={backToBottom}
              aria-label="回到底部"
              className="absolute bottom-3 left-1/2 z-10 -translate-x-1/2 rounded-full border border-line-strong bg-surface px-3 py-1 text-xs text-ink-mute shadow-lg transition-colors hover:text-ink"
            >
              <ArrowDownToLineIcon className="h-3 w-3" />
              回到底部
              {unseenCount > 0 ? `（${unseenCount} 条新消息）` : ""}
            </button>
          ) : null}
        </div>
        {turnError !== null && !isAgentRunning ? (
          <div
            role="alert"
            className={`mx-auto mb-2 flex w-full flex-wrap items-center gap-3 rounded-lg border border-line bg-surface px-4 py-2.5 text-sm text-danger-ink ${widthClass}`}
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
              className="rounded p-1.5 text-ink-faint hover:text-ink"
            >
              <XIcon className="h-3 w-3" />
            </button>
          </div>
        ) : null}
        {/* 会话停靠坞：问答 > 队列——队列永远紧挨输入框；任务步骤在
            消息流内（PlanCard），不占停靠坞 */}
        <SessionDock>
          {/* 结构化问答：不弹窗、不遮会话——回答所需上下文就在上方 */}
          <QuestionDock />
          {/* 排队消息：运行中「稍后发送」，取消/出错后挂起等放行 */}
          <QueueDock />
        </SessionDock>
        <ChatInput
          isAgentRunning={isAgentRunning}
          disabled={isConnecting}
          onSend={sendPrompt}
          onEnqueue={enqueuePrompt}
          onCancel={requestCancel}
        />
      </section>
      {/* AAW 增强面板：默认收起，按需展开；展开时对话仍占主区。
          未注入发送通路时（孤立渲染 / 测试）给一个如实失败的兜底，
          不让开关变成没反应的死按钮 */}
      {isAawOpen ? (
        <ScopedErrorBoundary scope="AAW 面板" resetKey={contextPath ?? "none"}>
          <SessionAawPanel
            onSubmitAawPrompt={
              onSubmitAawPrompt ??
              (() => ({ ok: false, reason: NO_SUBMIT_PATH }))
            }
            onClose={toggleAaw}
          />
        </ScopedErrorBoundary>
      ) : null}
    </div>
  );
}
