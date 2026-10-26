/**
 * 输入历史（↑/↓ 翻已发送的 prompt）：模块级环，最近优先。
 *
 * 只记录经 ChatInput 发送的文本（向导 / 面板发送不经过它，不勉强）；
 * 重复发送同文只记一次（顶到最前，去重）；上限 100 条。
 * 纯数据模块（无订阅）——ChatInput 的按键处理直接命令式读写。
 */
const MAX_ENTRIES = 100;

const entries: string[] = [];

/** 记录一次发送（空文本与重复顶词都收敛为单条）。 */
export function recordPrompt(text: string): void {
  const trimmed = text.trim();
  if (trimmed.length === 0) {
    return;
  }
  const index = entries.lastIndexOf(trimmed);
  if (index !== -1) {
    entries.splice(index, 1);
  }
  entries.push(trimmed);
  if (entries.length > MAX_ENTRIES) {
    entries.splice(0, entries.length - MAX_ENTRIES);
  }
}

/** 只读快照（最近在后）。 */
export function getPromptHistory(): readonly string[] {
  return entries;
}

/** 测试复位。 */
export function resetPromptHistoryForTests(): void {
  entries.length = 0;
}
