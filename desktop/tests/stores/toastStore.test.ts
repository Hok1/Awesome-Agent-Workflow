/**
 * toast store：入队 / 业务键去重替换 / 手动 dismiss / 栈上限 5。
 */
import { beforeEach, describe, expect, it } from "vitest";

import { useToastStore } from "../../src/stores/toastStore.ts";

beforeEach(() => {
  useToastStore.setState({ items: [] });
});

describe("toastStore", () => {
  it("push 入队并给默认变体与时长", () => {
    useToastStore.getState().push({ message: "已复制" });
    const [item] = useToastStore.getState().items;
    expect(item?.message).toBe("已复制");
    expect(item?.variant).toBe("info");
    expect(item?.durationMs).toBe(3000);
    expect(item?.dedupeKey).toBeNull();
  });

  it("同 dedupeKey 的新条目替换旧条目（不堆叠）", () => {
    const { push } = useToastStore.getState();
    push({ message: "复制中…", dedupeKey: "copy" });
    push({ message: "已复制", variant: "ok", dedupeKey: "copy" });
    const items = useToastStore.getState().items;
    expect(items).toHaveLength(1);
    expect(items[0]?.message).toBe("已复制");
  });

  it("无键条目各自独立；dismiss 按 id 移除", () => {
    const { push, dismiss } = useToastStore.getState();
    push({ message: "a" });
    push({ message: "b" });
    expect(useToastStore.getState().items).toHaveLength(2);
    dismiss(useToastStore.getState().items[0]!.id);
    expect(useToastStore.getState().items.map((i) => i.message)).toEqual(["b"]);
  });

  it("栈上限 5：新条目顶掉最旧的", () => {
    for (let i = 0; i < 7; i++) {
      useToastStore.getState().push({ message: `t${i}` });
    }
    const messages = useToastStore.getState().items.map((item) => item.message);
    expect(messages).toEqual(["t2", "t3", "t4", "t5", "t6"]);
  });
});
