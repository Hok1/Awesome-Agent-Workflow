/**
 * 会话条目的时间展示工具：时长（工具卡 / 思考块的耗时）与时钟（hover
 * 时间戳）。从 ThoughtBlock 的私有实现提炼共享——格式保持一致，避免
 * 同屏出现两种「1m05s」。
 */

/** 毫秒 → 人读时长（<1s 保留一位小数，其余取整；≥1s<1m 为 `Ns`，之上 `Nm Ns`）。 */
export function formatDuration(ms: number): string {
  if (ms < 1000) {
    return `${(ms / 1000).toFixed(1)}s`;
  }
  if (ms < 60_000) {
    return `${Math.round(ms / 1000)}s`;
  }
  const minutes = Math.floor(ms / 60_000);
  return `${minutes}m${Math.round((ms % 60_000) / 1000)}s`;
}

/** 时间戳 → `HH:MM:SS`（本地时区）；空值 / 非法值返回 null（调用方不渲染 title）。 */
export function formatClock(input: string | number | null): string | null {
  const date =
    typeof input === "number"
      ? new Date(input)
      : input !== null && input.length > 0
        ? new Date(input)
        : null;
  if (date === null || Number.isNaN(date.getTime())) {
    return null;
  }
  const hh = String(date.getHours()).padStart(2, "0");
  const mm = String(date.getMinutes()).padStart(2, "0");
  const ss = String(date.getSeconds()).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}
