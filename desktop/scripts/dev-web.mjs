/**
 * dev:web 入口：启动 vite dev server（含内嵌 dev bridge），就绪后自动
 * 打开浏览器；也是 dev-web.cmd 双击启动的落点。
 *
 * 已有实例在跑时不再起第二个（strictPort 必撞 1420），改为直接打开
 * 浏览器退出。端口探测同时试 IPv4/IPv6 回环——本机 vite 只绑 [::1]。
 * Ctrl+C 退出时插件会收口全部 agent 子进程。
 */
import { spawn } from "node:child_process";
import net from "node:net";
import { fileURLToPath } from "node:url";

const PORT = 1420;
const PAGE_URL = `http://localhost:${PORT}/`;

function tryConnect(host, port, timeoutMs = 400) {
  return new Promise((resolve) => {
    const socket = net.connect({ host, port });
    const settle = (ok) => {
      socket.destroy();
      resolve(ok);
    };
    socket.setTimeout(timeoutMs, () => settle(false));
    socket.once("connect", () => settle(true));
    socket.once("error", () => settle(false));
  });
}

async function isUp() {
  return (
    (await tryConnect("127.0.0.1", PORT)) || (await tryConnect("::1", PORT))
  );
}

function openBrowser() {
  if (process.platform === "win32") {
    spawn("cmd", ["/c", "start", "", PAGE_URL], {
      detached: true,
      stdio: "ignore",
    }).unref();
  } else {
    const opener = process.platform === "darwin" ? "open" : "xdg-open";
    spawn(opener, [PAGE_URL], { detached: true, stdio: "ignore" }).unref();
  }
}

if (await isUp()) {
  console.log(`[dev-web] ${PORT} 已有实例在运行，直接打开浏览器`);
  openBrowser();
  process.exit(0);
}

process.env.AAW_DEV_BRIDGE = "1";
const viteBin = fileURLToPath(
  new URL("../node_modules/vite/bin/vite.js", import.meta.url),
);
const child = spawn(process.execPath, [viteBin], {
  stdio: "inherit",
  env: { ...process.env },
});
console.log(
  `[dev-web] 启动中……就绪后自动打开 ${PAGE_URL}（Ctrl+C 退出并收口 agent 进程）`,
);

// 轮询端口就绪后开一次浏览器（90s 未就绪则提示手动打开）
const deadline = Date.now() + 90_000;
(function poll() {
  if (child.exitCode !== null) {
    return;
  }
  if (Date.now() > deadline) {
    console.log(`[dev-web] 等待超时：请手动打开 ${PAGE_URL}，并查看上方 vite 日志`);
    return;
  }
  void isUp().then((up) => {
    if (up) {
      openBrowser();
    } else {
      setTimeout(poll, 500);
    }
  });
})();

child.on("exit", (code, signal) => {
  if (signal !== null) {
    process.kill(process.pid, signal);
    return;
  }
  process.exit(code ?? 0);
});
