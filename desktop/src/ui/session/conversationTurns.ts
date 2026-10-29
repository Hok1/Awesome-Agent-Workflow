import type { SessionItem, TurnState } from "../../stores/sessionStore.ts";
import { stopReasonNotices } from "../../stores/sessionStore.ts";

const interruptedNotices = new Set(Object.values(stopReasonNotices));

export interface ConversationTurn {
  readonly id: string;
  readonly user?: Extract<SessionItem, { kind: "user" }>;
  readonly history: readonly SessionItem[];
  readonly answer?: Extract<SessionItem, { kind: "assistant" }>;
  readonly forceOpen: boolean;
  readonly running: boolean;
}

/** turn 对象的引用稳定性缓存：键为 turn id，值复用条件是全部内容逐项
 * 引用相等（见 flush 内检查）。条目对象在流式期只追加不改动，历史 turn
 * 因此在 chunk 间保持同一引用；旧窗口滚出后旧键被新结果自然覆盖。 */
const turnCache = new Map<string, ConversationTurn>();

/** Presentation only: a user message bounds a turn; no backend state is changed.
 * Inspect the complete turn before windowing so a partial window cannot mistake
 * intermediate prose for a final answer, or lose an earlier failure notice.
 */
export function conversationTurns(
  items: readonly SessionItem[],
  visibleCount: number,
  running: boolean,
  turnState: TurnState,
  showPlans: boolean,
): readonly ConversationTurn[] {
  const start = Math.max(0, items.length - visibleCount);
  const result: ConversationTurn[] = [];
  let from = 0;
  const flush = (end: number) => {
    if (end <= start || from === end) return;
    const first = items[from]!;
    const user = first.kind === "user" ? first : undefined;
    const bodyStart = from + (user ? 1 : 0);
    const body = items.slice(bodyStart, end);
    const isLast = end === items.length;
    const isRunning = isLast && running;
    const abnormal =
      body.some(
        (item) =>
          item.kind === "system" &&
          (item.level === "error" || interruptedNotices.has(item.text)),
      ) ||
      (isLast &&
        (turnState === "failed" ||
          turnState === "cancelled" ||
          turnState === "unknown"));
    let answerIndex = -1;
    for (let i = end - 1; i >= bodyStart; i--) {
      const item = items[i]!;
      if (item.kind === "tool" || item.kind === "thought") break;
      if (item.kind === "assistant" && item.text.trim()) {
        answerIndex = i;
        break;
      }
    }
    const visible = items
      .slice(Math.max(bodyStart, start), end)
      .filter((item) => showPlans || item.kind !== "plan");
    const answer = answerIndex >= start ? items[answerIndex] : undefined;
    const history = visible.filter((item) => item !== answer);
    const forceOpen = isRunning || abnormal || answerIndex === -1;
    const id = user?.id ?? `history-${first.id}`;
    // 引用稳定性缓存：条目对象在流式期只追加不改动，历史 turn 的可见内容
    // 逐项引用相等即整对象复用——memo 化的回合组件因此在流式 chunk 间跳过
    // 重渲染（否则每个 chunk 都重建全部 turn，可见列表全量 reconcile）。
    const cached = turnCache.get(id);
    if (
      cached !== undefined &&
      cached.running === isRunning &&
      cached.forceOpen === forceOpen &&
      cached.user === user &&
      cached.answer === answer &&
      cached.history.length === history.length &&
      cached.history.every((item, index) => item === history[index])
    ) {
      result.push(cached);
      turnCache.set(id, cached);
      return;
    }
    const turn: ConversationTurn = {
      id,
      ...(user && from >= start ? { user } : {}),
      history,
      ...(answer?.kind === "assistant" ? { answer } : {}),
      forceOpen,
      running: isRunning,
    };
    turnCache.set(id, turn);
    result.push(turn);
  };
  for (let i = 0; i < items.length; i++) {
    if (items[i]!.kind === "user") {
      flush(i);
      from = i;
    }
  }
  flush(items.length);
  return result;
}
