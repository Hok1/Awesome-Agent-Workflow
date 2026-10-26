// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
mod acp_process;
mod commands;

use tauri::{Emitter, Manager};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        // 工作区目录选择（@tauri-apps/plugin-dialog）
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            commands::run_command,
            commands::path_exists,
            commands::list_dir_names,
            commands::copy_dir,
            commands::read_text_file,
            commands::write_text_file,
            commands::chrys_skills_dir,
            commands::chrys_sessions_dir,
            // 工作区文件列举（@ 提及数据源；跳过依赖目录，深度/条目封顶）
            commands::list_workspace_files,
            // 关闭守卫：前端裁决后经它真正销毁窗口（跳过 CloseRequested）
            commands::force_close,
            // ACP agent 长连接子进程（acp_process.rs，事件经 app.emit 广播）
            acp_process::acp_spawn,
            acp_process::acp_stdin_write,
            acp_process::acp_stdin_close,
            acp_process::acp_kill_tree,
            acp_process::acp_release
        ])
        .on_window_event(|window, event| {
            // 关闭守卫的 Rust 半边：CloseRequested 一律拦下转交前端裁决
            // （空闲 → 先收口 agent 进程树；agent 运行中 / 有挂起审批 →
            // 确认弹窗），前端再经 force_close（destroy）真正关窗——默认
            // 的直接销毁会把 agent 进程树变成孤儿，抱着 chrys 的锁拖慢
            // 下一次启动（Job Object 是它死透时的兜底，不是许可）。
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                let _ = window.app_handle().emit("aaw://close-requested", ());
                api.prevent_close();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
