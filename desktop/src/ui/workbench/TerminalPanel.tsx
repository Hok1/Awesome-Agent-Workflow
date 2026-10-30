/**
 * 底部终端面板（顶栏终端钮的落点，ZCode Terminal.tsx:289-356 桌面可用子集）：
 *
 * - 形态：内容区底部固定高面板（默认 30%、拖拽手柄可改、clamp
 *   [140px, 容器 50%]，对齐 ZCode AnimatedTerminalPanel 的 defaultSize /
 *   min / max），工具栏行「终端」标题 + 右端 ghost 关闭钮；
 * - 内容：当前活跃会话消息中 execute 类工具项的**只读回放**（复用
 *   TerminalOutput 的吸底跟随 / 上滚冻结语义），按发生序取末尾 20 条；
 * - 能力缺口（如实标注，非 PTY 终端）：desktop 无 PTY / 交互式 shell，
 *   无 shell 标签、无多 tab / Plus 新建钮（ZCode 的 Tabs 与
 *   handleCreateSession 无对应能力）、无 xterm ANSI 主题渲染
 *   （terminalTheme 不适用）——本面板是 execute 工具输出的回放视图。
 */
import { useMemo, useRef, useState } from "react";

import {
  toolResultSummary,
  useSessionStore,
  type SessionItem,
  type ToolCallItem,
} from "../../stores/sessionStore.ts";
import { useWorkbenchUiStore } from "../../stores/workbenchUiStore.ts";
import { formatPayload } from "../session/ToolCallCard.tsx";
import { TerminalOutput } from "../session/TerminalOutput.tsx";
import { XIcon } from "../icons.tsx";

/** 面板最小高度（px，ZCode AnimatedTerminalPanel min 同值）。 */
export const TERMINAL_MIN_HEIGHT_PX = 140;
/** 面板最大高度占容器高度的比例（ZCode max 50% 同值）。 */
export const TERMINAL_MAX_RATIO = 0.5;
/** 回放条数上限（按发生序取末尾）。 */
const REPLAY_LIMIT = 20;

/** 面板高度钳制：[140px, 容器 50%]（导出供测试）。 */
export function clampTerminalHeight(
  value: number,
  containerHeight: number,
): number {
  const max =
    containerHeight > 0
      ? Math.max(TERMINAL_MIN_HEIGHT_PX, containerHeight * TERMINAL_MAX_RATIO)
      : Number.POSITIVE_INFINITY;
  return Math.min(Math.max(TERMINAL_MIN_HEIGHT_PX, value), max);
}

/** execute 类工具项（发生序）。 */
function isExecuteItem(item: SessionItem): item is ToolCallItem {
  return item.kind === "tool" && item.toolKind === "execute";
}

export function TerminalPanel({
  project,
}: {
  readonly project: string | null;
}) {
  const toggleTerminal = useWorkbenchUiStore((state) => state.toggleTerminal);
  const items = useSessionStore((state) => state.items);
  const sectionRef = useRef<HTMLElement | null>(null);
  // null = 未拖拽过，按默认 30% 呈现（ZCode defaultSize 0→展开 30%）
  const [height, setHeight] = useState<number | null>(null);
  const dragRef = useRef<{ startY: number; startHeight: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  const executeItems = useMemo(
    () => items.filter(isExecuteItem).slice(-REPLAY_LIMIT),
    [items],
  );

  function onHandlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = {
      startY: event.clientY,
      startHeight:
        sectionRef.current?.getBoundingClientRect().height ?? 0,
    };
    setDragging(true);
  }

  function onHandlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    const drag = dragRef.current;
    if (drag === null) {
      return;
    }
    const containerHeight =
      sectionRef.current?.parentElement?.clientHeight ?? 0;
    setHeight(
      clampTerminalHeight(
        drag.startHeight + (drag.startY - event.clientY),
        containerHeight,
      ),
    );
  }

  function onHandlePointerUp() {
    dragRef.current = null;
    setDragging(false);
  }

  return (
    <>
      {/* 拖拽手柄：hover 显细横条（ZCode AnimatedTerminalPanel 顶部
          h-1 手柄同款），pointer 拖拽改面板高 */}
      <div
        role="separator"
        aria-label="调整终端面板高度"
        aria-orientation="horizontal"
        className="group relative h-1 w-full shrink-0 cursor-row-resize"
        onPointerDown={onHandlePointerDown}
        onPointerMove={onHandlePointerMove}
        onPointerUp={onHandlePointerUp}
        onPointerCancel={onHandlePointerUp}
      >
        <span
          aria-hidden={true}
          className={`absolute inset-x-0 top-0 h-0.5 rounded-full bg-transparent transition-colors group-hover:bg-line-strong ${
            dragging ? "bg-line-strong" : ""
          }`}
        />
      </div>
      <section
        ref={sectionRef}
        data-testid="terminal-panel"
        aria-label="终端"
        className="flex shrink-0 flex-col gap-2 overflow-hidden border-t border-line bg-base p-3 pb-2"
        style={{ height: height ?? "30%" }}
      >
        {/* 工具栏行：标题 + 右端关闭钮（ZCode :299-354；shell 标签与
            Plus 新建钮省略——无 shell / 多 tab 能力） */}
        <div className="flex shrink-0 items-center gap-2">
          <span className="min-w-0 shrink-0 truncate text-ui-base font-medium text-ink">
            终端
          </span>
          {project === null ? null : (
            <span className="min-w-0 flex-1 truncate text-ui-base text-ink-subtlest">
              {project}
            </span>
          )}
          <div className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              data-testid="terminal-close-button"
              aria-label="关闭终端"
              title="关闭终端"
              onClick={toggleTerminal}
              className="flex size-7 shrink-0 items-center justify-center rounded-lg text-ink transition-colors hover:bg-hover hover:text-ink"
            >
              <XIcon className="h-4 w-4" strokeWidth={2} />
            </button>
          </div>
        </div>
        {/* 输出体：execute 工具输出的只读回放（末尾 20 条，发生序） */}
        <div className="min-h-0 flex-1 overflow-y-auto">
          {executeItems.length === 0 ? (
            <p className="text-ui-base text-ink-subtlest">
              当前会话暂无命令输出
            </p>
          ) : (
            executeItems.map((item) => (
              <div key={item.id} className="flex min-w-0 flex-col gap-1 pb-2">
                <div className="font-mono text-xs text-ink-subtle">
                  {toolResultSummary(item.rawInput)}
                </div>
                <TerminalOutput
                  fill={true}
                  text={formatPayload(item.rawOutput)}
                  failed={item.status === "failed"}
                />
              </div>
            ))
          )}
        </div>
      </section>
    </>
  );
}

export default TerminalPanel;
