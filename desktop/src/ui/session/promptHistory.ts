/**
 * 输入历史（↑/↓ 翻已发送的 prompt）：最近优先，按工作区持久化到
 * localStorage（`aaw-desktop/prompt-history/<encodeURIComponent(path)>`）。
 *
 * 只记录经 ChatInput 发送的文本（向导 / 面板发送不经过它，不勉强）；
 * 重复发送同文只记一次（顶到最前，去重）；上限 100 条。
 * 纯数据模块（无订阅）——ChatInput 的按键处理直接命令式读写；
 * scope 未设置（null，如测试环境）时退化为纯内存环，行为与旧版一致。
 */
const MAX_ENTRIES = 100;
const STORAGE_PREFIX = "aaw-desktop/prompt-history/";

const entries: string[] = [];
let scopeKey: string | null = null;

function storageKeyOf(workspacePath: string): string {
  return `${STORAGE_PREFIX}${encodeURIComponent(workspacePath)}`;
}

/** 载入失败（损坏 / 配额满 / 隐私模式）一律按无历史处理，不阻断输入。 */
function loadFromStorage(key: string): void {
  try {
    const raw = window.localStorage.getItem(key);
    if (raw === null) {
      return;
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return;
    }
    for (const entry of parsed) {
      if (typeof entry === "string" && entry.length > 0) {
        entries.push(entry);
      }
    }
    if (entries.length > MAX_ENTRIES) {
      entries.splice(0, entries.length - MAX_ENTRIES);
    }
  } catch {
    // 读取失败不影响内存环，继续空历史起步
  }
}

/** 写入失败静默降级（本会话仍可 ↑ 回溯，重启后丢失而已）。 */
function persistToStorage(): void {
  if (scopeKey === null) {
    return;
  }
  try {
    window.localStorage.setItem(scopeKey, JSON.stringify(entries));
  } catch {
    // localStorage 不可用：退化为纯内存
  }
}

/** 切换持久化 scope（null = 纯内存）；切换时载入该工作区的历史。 */
export function setPromptHistoryScope(workspacePath: string | null): void {
  const next = workspacePath === null ? null : storageKeyOf(workspacePath);
  if (next === scopeKey) {
    return;
  }
  scopeKey = next;
  entries.length = 0;
  if (next !== null) {
    loadFromStorage(next);
  }
}

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
  persistToStorage();
}

/** 只读快照（最近在后）。 */
export function getPromptHistory(): readonly string[] {
  return entries;
}

/** 测试复位（scope 一并清空，回到纯内存态）。 */
export function resetPromptHistoryForTests(): void {
  entries.length = 0;
  scopeKey = null;
}
