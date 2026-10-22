/**
 * 项目目录选择：@tauri-apps/plugin-dialog 的薄封装。
 *
 * 仅在 Tauri webview 内可用（capabilities 已声明 dialog:default）；
 * 非 Tauri 环境（浏览器 / 测试）调用返回 null，由 UI 提示改用手动输入。
 */
import { open } from "@tauri-apps/plugin-dialog";

/** 打开系统目录选择对话框；取消或环境不支持返回 null。 */
export async function pickDirectory(): Promise<string | null> {
  try {
    const selected = await open({
      directory: true,
      multiple: false,
      title: "选择项目目录",
    });
    return typeof selected === "string" ? selected : null;
  } catch {
    // 非 Tauri 环境或对话框异常：按取消处理
    return null;
  }
}
