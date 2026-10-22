// Learn more about Tauri commands at https://tauri.app/develop/calling-rust/
mod acp_process;
mod commands;

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
            // ACP agent 长连接子进程（acp_process.rs，事件经 app.emit 广播）
            acp_process::acp_spawn,
            acp_process::acp_stdin_write,
            acp_process::acp_stdin_close,
            acp_process::acp_kill_tree,
            acp_process::acp_release
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
