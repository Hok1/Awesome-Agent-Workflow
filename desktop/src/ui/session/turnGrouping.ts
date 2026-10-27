/**
 * 轮内已完成工作的折叠投影（纯函数）：把窗口化切片里的条目流重组为
 * 渲染单元——「轮」以用户消息分界；轮内**连续**的已完成思考块 / 已完成
 * 工具卡（≥2 张才成组，单张折叠反而多点一次）折叠为一个工作组，
 * 组外保留：assistant 文本、流式/运行中条目、失败的工具卡（排障现场）、
 * 系统提示与用户消息。
 *
 * 折叠组的耗时 = 组内各条目起止时刻之和（缺时刻的条目跳过；全缺则
 * 返回 null，展示回落为纯步骤数）。作用在 sessionWindow 切片之后，
 * 不碰补载锚定与跟随状态机。
 */
import type { SessionItem } from "../../stores/sessionStore.ts";

export type TurnUnit =
  | {
      readonly kind: "item";
      readonly id: string;
      readonly item: SessionItem;
    }
  | {
      readonly kind: "work";
      readonly id: string;
      readonly items: readonly SessionItem[];
      /** 组内可计条目的耗时合计；无可计条目为 null。 */
      readonly elapsedMs: number | null;
    };

/** 可折叠的「已完成工作」：封口的思考块 / completed 的工具卡。 */
function isFoldableWork(item: SessionItem): boolean {
  if (item.kind === "thought") {
    return !item.isStreaming;
  }
  if (item.kind === "tool") {
    return item.status === "completed";
  }
  return false;
}

/** 条目耗时：起止俱全才可计，否则 0 贡献（由调用方聚合判断是否有可计项）。 */
function itemElapsedMs(item: SessionItem): number | null {
  if (item.kind === "thought" || item.kind === "tool") {
    const { startedAt, endedAt } = item;
    if (startedAt !== null && endedAt !== null) {
      return Math.max(0, endedAt - startedAt);
    }
  }
  return null;
}

/** 连续可折叠段 ≥2 才成组（单张折叠是负优化：多一次点击零降噪）。 */
const MIN_GROUP_SIZE = 2;

export function groupTurnWork(
  items: readonly SessionItem[],
): readonly TurnUnit[] {
  const units: TurnUnit[] = [];
  let run: SessionItem[] = [];
  const flushRun = (): void => {
    if (run.length === 0) {
      return;
    }
    if (run.length >= MIN_GROUP_SIZE) {
      const elapsed = run
        .map(itemElapsedMs)
        .filter((value): value is number => value !== null);
      units.push({
        kind: "work",
        id: `work-${run[0]?.id ?? "x"}-${run.length}`,
        items: run,
        elapsedMs:
          elapsed.length > 0 ? elapsed.reduce((sum, value) => sum + value, 0) : null,
      });
    } else {
      for (const item of run) {
        units.push({ kind: "item", id: item.id, item });
      }
    }
    run = [];
  };
  for (const item of items) {
    if (isFoldableWork(item)) {
      run.push(item);
    } else {
      flushRun();
      units.push({ kind: "item", id: item.id, item });
    }
  }
  flushRun();
  return units;
}
