/**
 * Toast 宿主：右下角浮层栈（避开底部居中的输入区），每条自带定时退场。
 *
 * - 定时器在条目组件内（store 保持无副作用）；
 * - `durationMs: 0` 的条目不装定时器（持续到显式关闭的进度态）；
 * - 悬停暂停退场（用户正在读）——离开后按剩余时长续走；
 * - aria-live="polite"：屏幕阅读器在空闲时播报，不打断当前任务。
 */
import { useEffect, useRef } from "react";

import { useToastStore, type ToastItem } from "../stores/toastStore.ts";
import { XIcon } from "./icons.tsx";

/** 变体的语义色（边框 + 文字，植面统一用 surface 保持轻）。 */
const variantClass: Readonly<Record<ToastItem["variant"], string>> = {
  info: "border-line-strong text-ink-soft",
  ok: "border-ok-line text-ok-ink",
  warn: "border-warn-line text-warn-ink",
  danger: "border-danger-line text-danger-ink",
};

function ToastEntry({ item }: { readonly item: ToastItem }) {
  const dismiss = useToastStore((state) => state.dismiss);
  const remainingRef = useRef(item.durationMs);
  const startedAtRef = useRef(0);

  useEffect(() => {
    if (item.durationMs === 0) {
      return;
    }
    startedAtRef.current = Date.now();
    let timer: ReturnType<typeof setTimeout> | null = setTimeout(
      () => dismiss(item.id),
      remainingRef.current,
    );
    const pause = (): void => {
      if (timer === null) {
        return;
      }
      clearTimeout(timer);
      timer = null;
      remainingRef.current -= Date.now() - startedAtRef.current;
    };
    const resume = (): void => {
      if (timer !== null) {
        return;
      }
      startedAtRef.current = Date.now();
      timer = setTimeout(
        () => dismiss(item.id),
        Math.max(0, remainingRef.current),
      );
    };
    const host = document.querySelector("[data-toast-host]");
    host?.addEventListener("pointerenter", pause);
    host?.addEventListener("pointerleave", resume);
    return () => {
      if (timer !== null) {
        clearTimeout(timer);
      }
      host?.removeEventListener("pointerenter", pause);
      host?.removeEventListener("pointerleave", resume);
    };
  }, [item.id, item.durationMs, dismiss]);

  return (
    <div
      role="status"
      className={`toast-in pointer-events-auto flex items-center gap-2 rounded-lg border bg-surface px-3 py-2 text-xs shadow-elev-3 ${variantClass[item.variant]}`}
    >
      <span className="min-w-0 max-w-72 break-words">{item.message}</span>
      <button
        type="button"
        aria-label="关闭提示"
        onClick={() => {
          dismiss(item.id);
        }}
        className="shrink-0 rounded p-1 text-ink-faint transition-colors hover:text-ink"
      >
        <XIcon className="h-3 w-3" />
      </button>
    </div>
  );
}

/** 挂在应用根：无条目时零占位。 */
export function ToastHost() {
  const items = useToastStore((state) => state.items);
  if (items.length === 0) {
    return null;
  }
  return (
    <div
      data-toast-host=""
      aria-live="polite"
      className="pointer-events-none fixed right-5 bottom-5 z-50 flex flex-col items-end gap-2"
    >
      {items.map((item) => (
        <ToastEntry key={item.id} item={item} />
      ))}
    </div>
  );
}
