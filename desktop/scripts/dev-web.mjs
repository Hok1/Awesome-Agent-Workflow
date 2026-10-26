/**
 * dev:web 入口：以 AAW_DEV_BRIDGE=1 拉起 vite dev server。
 *
 * 浏览器开发运行时 = vite（含内嵌 dev bridge 插件）。打开终端提示的
 * http://localhost:1420 即以真实 agent / aaw 数据运行应用，前端改动
 * HMR 秒级生效。Ctrl+C 退出时插件会收口全部 agent 子进程。
 */
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

process.env.AAW_DEV_BRIDGE = "1";

const viteBin = fileURLToPath(
  new URL("../node_modules/vite/bin/vite.js", import.meta.url),
);
const child = spawn(process.execPath, [viteBin], {
  stdio: "inherit",
  env: { ...process.env },
});
child.on("exit", (code, signal) => {
  if (signal !== null) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
