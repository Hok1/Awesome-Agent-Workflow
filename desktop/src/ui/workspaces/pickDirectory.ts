/**
 * 项目目录选择：Tauri 原生对话框优先，dev 浏览器运行时回落 dev bridge。
 *
 * - Tauri webview：@tauri-apps/plugin-dialog（capabilities 已声明
 *   dialog:default）；
 * - dev 浏览器（npm run dev:web）：插件在纯浏览器里必然失败，经 dev
 *   bridge 调 PowerShell 的 FolderBrowserDialog（浏览器自身拿不到
 *   绝对路径，这是唯一途径）；
 * - 其余环境（vitest）：返回 null，由 UI 提示改用手动输入。
 */
import { open } from "@tauri-apps/plugin-dialog";

import { devBridgePost } from "../../dev/bridgeClient.ts";

/** 打开系统目录选择对话框；取消或环境不支持返回 null。 */
export async function pickDirectory(): Promise<string | null> {
  try {
    const selected = await open({
      directory: true,
      multiple: false,
      title: "选择项目目录",
    });
    if (typeof selected === "string") {
      return selected;
    }
    // 真取消（null）：Tauri 环境到此为止；dev 浏览器里插件本就到不了
    // 这一步（纯浏览器下 open 必然 reject 走 catch）
  } catch {
    // 非 Tauri 环境或对话框异常：落到 dev bridge
  }
  // 生产构建折叠 DEV，bridge 分支被摇走
  if (import.meta.env.DEV && !import.meta.env.VITEST) {
    try {
      const wire = await devBridgePost<{ path?: unknown }>("/pick-directory");
      return typeof wire.path === "string" && wire.path !== ""
        ? wire.path
        : null;
    } catch {
      // bridge 未启动 / 非 Windows 无对话框：按取消处理（手动输入兜底）
      return null;
    }
  }
  return null;
}
