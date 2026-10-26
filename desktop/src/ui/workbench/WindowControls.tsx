/**
 * 自绘窗口控制（无边框标题栏的右端三钮）：最小化 / 最大化切换 / 关闭。
 *
 * 窗口装饰已在 tauri.conf.json 关闭（decorations: false）——顶栏即标题
 * 栏（ContextBar），这三颗钮承担原生标题栏的窗口操作（ZCode 同款形态）。
 * 「关闭」走 window.close() → Rust 的 CloseRequested → 关闭守卫（agent
 * 运行中确认、先收口进程树再销毁），与点系统 ✕ 完全同路。非 Tauri 环境
 * （测试 / 浏览器）不渲染。
 */
import { getCurrentWindow } from "@tauri-apps/api/window";

import { createLogger } from "../../core/logger.ts";
import { isTauriEnv } from "../../core/host.ts";

const logger = createLogger("ui");

/** 最小化：底横线。 */
function MinimizeIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      aria-hidden={true}
      className="h-3 w-3"
    >
      <path d="M5 12h14" />
    </svg>
  );
}

/** 最大化切换：方框（还原态为双框，这里统一用方框表达「窗口大小」）。 */
function MaximizeIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinejoin="round"
      aria-hidden={true}
      className="h-3 w-3"
    >
      <rect x="5" y="5" width="14" height="14" rx="1.5" />
    </svg>
  );
}

/** 关闭：✕。 */
function CloseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      aria-hidden={true}
      className="h-3 w-3"
    >
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  );
}

export function WindowControls() {
  if (!isTauriEnv()) {
    return null;
  }
  const current = getCurrentWindow();
  // 窗口动作失败要留痕（权限缺失 / 平台限制）：静默吞掉的话，按钮
  // 「点了没反应」这类问题在诊断页不可见
  const run = (action: string, task: Promise<void>): void => {
    task.catch((error: unknown) => {
      logger.warn("窗口动作失败", {
        action,
        reason: error instanceof Error ? error.message : String(error),
      });
    });
  };
  const buttonBase =
    "press flex h-7 w-9 shrink-0 items-center justify-center rounded-md text-ink-faint transition-colors hover:bg-raised hover:text-ink";
  return (
    <div
      className="flex shrink-0 items-center gap-0.5 pl-2"
      data-window-controls=""
    >
      <button
        type="button"
        aria-label="最小化窗口"
        title="最小化"
        onClick={() => {
          run("minimize", current.minimize());
        }}
        className={buttonBase}
      >
        <MinimizeIcon />
      </button>
      <button
        type="button"
        aria-label="切换窗口大小"
        title="最大化 / 还原"
        onClick={() => {
          run("toggleMaximize", current.toggleMaximize());
        }}
        className={buttonBase}
      >
        <MaximizeIcon />
      </button>
      <button
        type="button"
        aria-label="关闭窗口"
        title="关闭（agent 运行中会先确认）"
        onClick={() => {
          run("close", current.close());
        }}
        className="press flex h-7 w-9 shrink-0 items-center justify-center rounded-md text-ink-faint transition-colors hover:bg-danger-bg hover:text-danger-ink"
      >
        <CloseIcon />
      </button>
    </div>
  );
}

export default WindowControls;
