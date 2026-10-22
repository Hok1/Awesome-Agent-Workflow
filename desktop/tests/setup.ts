/**
 * Vitest 全局 setup：
 * - 挂载 @testing-library/jest-dom 匹配器；
 * - 显式注册 cleanup（vitest 未开 globals 时 RTL 不会自动清理 DOM）。
 */
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
});
