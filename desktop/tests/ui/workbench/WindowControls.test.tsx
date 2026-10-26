/**
 * 自绘窗口控制：Tauri 环境渲染三钮并调 getCurrentWindow 的对应方法；
 * 非 Tauri 环境不渲染（测试 / 浏览器无窗口 API）。
 */
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const minimize = vi.fn();
const toggleMaximize = vi.fn();
const close = vi.fn();

vi.mock("@tauri-apps/api/window", () => ({
  getCurrentWindow: (): {
    minimize: () => Promise<void>;
    toggleMaximize: () => Promise<void>;
    close: () => Promise<void>;
  } => ({
    // 真实 API 返回 Promise；返回 void 的话组件里的 task.catch 会炸成
    // 未处理异常（vitest 报 Unhandled Errors）
    minimize: () => {
      minimize();
      return Promise.resolve();
    },
    toggleMaximize: () => {
      toggleMaximize();
      return Promise.resolve();
    },
    close: () => {
      close();
      return Promise.resolve();
    },
  }),
}));

import { WindowControls } from "../../../src/ui/workbench/WindowControls.tsx";

type MutableWindow = Record<string, unknown>;

beforeEach(() => {
  minimize.mockClear();
  toggleMaximize.mockClear();
  close.mockClear();
});

afterEach(() => {
  delete (window as unknown as MutableWindow).__TAURI_INTERNALS__;
});

describe("WindowControls", () => {
  it("Tauri 环境：三钮各调对应窗口方法", () => {
    (window as unknown as MutableWindow).__TAURI_INTERNALS__ = {};
    render(<WindowControls />);
    fireEvent.click(screen.getByRole("button", { name: "最小化窗口" }));
    expect(minimize).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "切换窗口大小" }));
    expect(toggleMaximize).toHaveBeenCalledTimes(1);
    // 关闭走 window.close() → Rust CloseRequested → 关闭守卫同路
    fireEvent.click(screen.getByRole("button", { name: "关闭窗口" }));
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("非 Tauri 环境不渲染", () => {
    render(<WindowControls />);
    expect(
      screen.queryByRole("button", { name: "最小化窗口" }),
    ).not.toBeInTheDocument();
  });
});
