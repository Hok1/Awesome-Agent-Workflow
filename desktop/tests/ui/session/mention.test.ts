/**
 * @ 提及纯逻辑：触发检测（@ 段结尾）与候选过滤（子串优先 + 子序列兜底）。
 */
import { describe, expect, it } from "vitest";

import {
  detectMentionTrigger,
  filterMentionFiles,
} from "../../../src/ui/session/mention.ts";

describe("detectMentionTrigger", () => {
  it("行首/空白后的 @ 段命中，返回查询串", () => {
    expect(detectMentionTrigger("@")).toBe("");
    expect(detectMentionTrigger("@sr")).toBe("sr");
    expect(detectMentionTrigger("看一下 @src/ap")).toBe("src/ap");
    expect(detectMentionTrigger("（@aaw")).toBe("aaw");
  });

  it("邮箱 / 文本中段的 @ 不触发", () => {
    expect(detectMentionTrigger(" mail@example.com")).toBeNull();
    expect(detectMentionTrigger("没有符号")).toBeNull();
    expect(detectMentionTrigger("a@b")).toBeNull();
  });

  it("@ 后跟空白即结束触发段", () => {
    expect(detectMentionTrigger("@sr ")).toBeNull();
  });
});

describe("filterMentionFiles", () => {
  const files = [
    "README.md",
    ".sdd/SR-001/state.json",
    "skills/aaw-workflow/SKILL.md",
    "src/ui/session/ChatInput.tsx",
    "docs/architecture.md",
  ];

  it("空查询给前几条；子串匹配按位置排序", () => {
    expect(filterMentionFiles(files, "", 3)).toEqual([
      "README.md",
      ".sdd/SR-001/state.json",
      "skills/aaw-workflow/SKILL.md",
    ]);
    expect(filterMentionFiles(files, "sdd")).toEqual([
      ".sdd/SR-001/state.json",
    ]);
  });

  it("分隔符与大小写不敏感：糙输入也能命中", () => {
    expect(filterMentionFiles(["src/ui/ChatInput.tsx"], "chatinput")).toEqual([
      "src/ui/ChatInput.tsx",
    ]);
    expect(filterMentionFiles(["src\\ui\\Chat.tsx"], "ui/chat")).toEqual([
      "src\\ui\\Chat.tsx",
    ]);
  });

  it("子串落空时子序列兜底；命中上限 8", () => {
    expect(filterMentionFiles(["architecture.md"], "ach")).toEqual([
      "architecture.md",
    ]);
    const many = Array.from({ length: 20 }, (_, i) => `mod${i}.ts`);
    expect(filterMentionFiles(many, "mod")).toHaveLength(8);
  });
});
