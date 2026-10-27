/**
 * 输入历史环：去重顶词、上限 100、空文不记；工作区 scope 的持久化与切换。
 */
import { beforeEach, describe, expect, it } from "vitest";

import {
  getPromptHistory,
  recordPrompt,
  resetPromptHistoryForTests,
  setPromptHistoryScope,
} from "../../../src/ui/session/promptHistory.ts";

const KEY_A = `aaw-desktop/prompt-history/${encodeURIComponent("D:/work-a")}`;
const KEY_B = `aaw-desktop/prompt-history/${encodeURIComponent("D:/work-b")}`;

describe("promptHistory", () => {
  it("按发送顺序记录，最近在后", () => {
    resetPromptHistoryForTests();
    recordPrompt("第一条");
    recordPrompt("第二条");
    expect(getPromptHistory()).toEqual(["第一条", "第二条"]);
  });

  it("重复发送顶词去重（不产生相邻重复）", () => {
    resetPromptHistoryForTests();
    recordPrompt("a");
    recordPrompt("b");
    recordPrompt("a");
    expect(getPromptHistory()).toEqual(["b", "a"]);
  });

  it("空白不记录；上限 100 条", () => {
    resetPromptHistoryForTests();
    recordPrompt("   ");
    expect(getPromptHistory()).toEqual([]);
    for (let i = 0; i < 120; i++) {
      recordPrompt(`p${i}`);
    }
    const history = getPromptHistory();
    expect(history).toHaveLength(100);
    expect(history[0]).toBe("p20");
    expect(history[99]).toBe("p119");
  });
});

describe("promptHistory 工作区 scope 持久化", () => {
  beforeEach(() => {
    window.localStorage.clear();
    resetPromptHistoryForTests();
  });

  it("记录随 scope 落盘；切换工作区互不可见，切回即恢复", () => {
    setPromptHistoryScope("D:/work-a");
    recordPrompt("a-1");
    expect(JSON.parse(window.localStorage.getItem(KEY_A) as string)).toEqual([
      "a-1",
    ]);

    setPromptHistoryScope("D:/work-b");
    expect(getPromptHistory()).toEqual([]);
    recordPrompt("b-1");
    expect(JSON.parse(window.localStorage.getItem(KEY_B) as string)).toEqual([
      "b-1",
    ]);

    setPromptHistoryScope("D:/work-a");
    expect(getPromptHistory()).toEqual(["a-1"]);
  });

  it("scope 为 null 时纯内存不落盘；损坏数据按空历史处理", () => {
    recordPrompt("mem");
    expect(window.localStorage.getItem(KEY_A)).toBeNull();

    window.localStorage.setItem(KEY_B, "{bad json");
    setPromptHistoryScope("D:/work-b");
    expect(getPromptHistory()).toEqual([]);
  });
});
