/**
 * 轻量 toast 通知（全局反馈通道）：复制成功 / 配置保存这类「做了什么、
 * 成了没有」的一过性反馈，不值得弹窗，也不该毫无表示——toast 是中间层。
 *
 * 语义（对齐 ZCode 的自研 toast，按我们的体量裁剪）：
 * - 默认 3 秒自动消失，`durationMs: 0` 表示持续到显式关闭（进度态）；
 * - `dedupeKey`：同业务键的新 toast **替换**旧条目（如「已复制」连点
 *   不堆叠），无键的各自独立堆叠；
 * - 条目只增不删历史——退场由 ToastHost 的定时器驱动 dismiss。
 */
import { create } from "zustand";

import { createLogger } from "../core/logger.ts";

const logger = createLogger("ui");

export type ToastVariant = "info" | "ok" | "warn" | "danger";

export interface ToastInput {
  readonly message: string;
  readonly variant?: ToastVariant;
  /** 自动消失延时；0 = 持续显示直到显式 dismiss。 */
  readonly durationMs?: number;
  /** 业务去重键：同键新条目替换旧条目（不堆叠）。 */
  readonly dedupeKey?: string;
}

export interface ToastItem {
  readonly id: number;
  readonly message: string;
  readonly variant: ToastVariant;
  readonly durationMs: number;
  readonly dedupeKey: string | null;
}

interface ToastState {
  readonly items: readonly ToastItem[];
  readonly push: (input: ToastInput) => void;
  readonly dismiss: (id: number) => void;
}

let nextId = 1;

export const useToastStore = create<ToastState>((set) => ({
  items: [],

  push: (input) => {
    const item: ToastItem = {
      id: nextId++,
      message: input.message,
      variant: input.variant ?? "info",
      durationMs: input.durationMs ?? 3000,
      dedupeKey: input.dedupeKey ?? null,
    };
    set((state) => ({
      // 同 dedupeKey 的旧条目被本条替换；无键的各自追加（不能把别的不带键
      // 条目也滤掉——null !== null 恒 false 的反直觉陷阱）
      items: [
        ...(item.dedupeKey === null
          ? state.items
          : state.items.filter(
              (existing) => existing.dedupeKey !== item.dedupeKey,
            )),
        item,
      ].slice(-5),
    }));
    logger.debug("toast", { message: item.message, variant: item.variant });
  },

  dismiss: (id) => {
    set((state) => ({
      items: state.items.filter((item) => item.id !== id),
    }));
  },
}));

/** 便捷入口：非组件代码（复制、流程编排等）直接调用。 */
export function showToast(input: ToastInput): void {
  useToastStore.getState().push(input);
}
