/**
 * 输入历史环：去重顶词、上限 100、空文不记。
 */
import { describe, expect, it } from "vitest";

import {
  getPromptHistory,
  recordPrompt,
  resetPromptHistoryForTests,
} from "../../../src/ui/session/promptHistory.ts";

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
