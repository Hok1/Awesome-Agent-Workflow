import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ConversationTurnView } from "../../../src/ui/session/ConversationTurnView.tsx";
import type { ConversationTurn } from "../../../src/ui/session/conversationTurns.ts";

const base: ConversationTurn = {
  id: "u",
  forceOpen: true,
  running: true,
  history: [
    {
      kind: "assistant",
      id: "progress",
      text: "intermediate",
      isStreaming: false,
      createdAt: "",
    },
  ],
  answer: {
    kind: "assistant",
    id: "final",
    text: "final answer",
    isStreaming: false,
    createdAt: "",
  },
};
const renderItem = (item: { id: string }) => <p>{item.id}</p>;

describe("ConversationTurnView", () => {
  it("running is forced open; completion collapses history while answer stays visible", async () => {
    const view = render(
      <ConversationTurnView turn={base} renderItem={renderItem} />,
    );
    expect(screen.getByRole("button", { name: "工作中" })).toBeDisabled();
    // 折叠区内的中间助手文本经 AssistantMessage 渲染（markdown 文本可见）
    expect(screen.getByText("intermediate")).toBeInTheDocument();
    // 中间过程文本不带动作行（复制/时间只属于轮次最终回答，对齐 ZCode）
    expect(
      screen.queryByRole("button", { name: "复制消息" }),
    ).not.toBeInTheDocument();
    view.rerender(
      <ConversationTurnView
        turn={{ ...base, forceOpen: false, running: false }}
        renderItem={renderItem}
      />,
    );
    expect(screen.queryByText("intermediate")).not.toBeInTheDocument();
    expect(screen.getByText("final")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "已处理" }));
    expect(screen.getByText("intermediate")).toBeInTheDocument();
    view.rerender(
      <ConversationTurnView
        turn={{ ...base, forceOpen: false, running: false }}
        renderItem={renderItem}
      />,
    );
    expect(screen.getByText("intermediate")).toBeInTheDocument();
  });
});
