/**
 * 工具调用卡片：折叠态一行摘要、展开看完整输入输出、状态徽标。
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ToolCallCard } from "../../../src/ui/session/ToolCallCard.tsx";
import type { ToolCallItem } from "../../../src/stores/sessionStore.ts";

function makeItem(overrides: Partial<ToolCallItem> = {}): ToolCallItem {
  return {
    kind: "tool",
    id: "tool-1",
    toolCallId: "t1",
    title: "run_command npm test",
    toolKind: "execute",
    status: "in_progress",
    rawInput: { command: "npm test", cwd: "desktop" },
    rawOutput: undefined,
    inputSummary: "command=npm test · cwd=desktop",
    resultSummary: "",
    ...overrides,
  };
}

describe("ToolCallCard", () => {
  it("折叠态一行：状态徽标 + 工具名 + 输入摘要，不显示完整 JSON", () => {
    render(<ToolCallCard item={makeItem()} />);
    expect(screen.getByText("运行中")).toBeInTheDocument();
    expect(screen.getByText("run_command npm test")).toBeInTheDocument();
    expect(
      screen.getByText("command=npm test · cwd=desktop"),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("工具输入")).not.toBeInTheDocument();
  });

  it("点击展开显示完整 JSON 输入与输出，再点收起", async () => {
    render(
      <ToolCallCard
        item={makeItem({
          status: "completed",
          rawOutput: "3 passed in 1.2s",
        })}
      />,
    );
    const toggle = screen.getByRole("button", { name: /run_command npm test/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const input = screen.getByLabelText("工具输入");
    expect(input).toHaveTextContent('"command": "npm test"');
    expect(screen.getByLabelText("工具输出")).toHaveTextContent(
      "3 passed in 1.2s",
    );
    await userEvent.click(toggle);
    expect(screen.queryByLabelText("工具输入")).not.toBeInTheDocument();
  });

  it("对象型输出按美化的 JSON 呈现", async () => {
    render(
      <ToolCallCard
        item={makeItem({
          status: "completed",
          rawOutput: { files: ["a.ts"] },
          resultSummary: '{"files":["a.ts"]}',
        })}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: /run_command npm test/ }),
    );
    expect(screen.getByLabelText("工具输出")).toHaveTextContent('"files": [');
    expect(screen.getByLabelText("工具输出")).toHaveTextContent('"a.ts"');
  });

  it("失败状态徽标为「失败」，输出区红色呈现", async () => {
    render(
      <ToolCallCard
        item={makeItem({
          status: "failed",
          rawOutput: "exit 1",
          resultSummary: "exit 1",
        })}
      />,
    );
    expect(screen.getByText("失败")).toBeInTheDocument();
    // 折叠行给出结果摘要（resultSummary）
    expect(screen.getByTitle("exit 1")).toBeInTheDocument();
    await userEvent.click(
      screen.getByRole("button", { name: /run_command npm test/ }),
    );
    expect(screen.getByLabelText("工具输出")).toHaveTextContent("exit 1");
  });

  it("运行中展开盯进度的卡，完成时自动收起（长轮次不留展开的历史卡）", async () => {
    const { rerender } = render(<ToolCallCard item={makeItem()} />);
    // 展开盯运行
    await userEvent.click(screen.getByRole("button", { name: /run_command/ }));
    expect(screen.getByLabelText("工具输入")).toBeInTheDocument();

    // 完成：自动收起
    rerender(
      <ToolCallCard
        item={makeItem({
          status: "completed",
          rawOutput: "ok",
          resultSummary: "exit 0",
        })}
      />,
    );
    expect(screen.queryByLabelText("工具输入")).not.toBeInTheDocument();
  });

  it("失败不自动收起：输出是排障现场，需要被人看到", async () => {
    const { rerender } = render(<ToolCallCard item={makeItem()} />);
    await userEvent.click(screen.getByRole("button", { name: /run_command/ }));

    rerender(
      <ToolCallCard
        item={makeItem({
          status: "failed",
          rawOutput: "boom",
          resultSummary: "exit 1",
        })}
      />,
    );
    expect(screen.getByLabelText("工具输出")).toBeInTheDocument();
  });

  it("status 缺省（null）时显示「已发起」", () => {
    render(<ToolCallCard item={makeItem({ status: null })} />);
    expect(screen.getByText("已发起")).toBeInTheDocument();
  });
});
