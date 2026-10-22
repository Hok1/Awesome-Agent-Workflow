//! 工作区管理所需的系统 command：
//! - `run_command`：执行外部命令（chrys / uv / aaw CLI 探测与调用），
//!   可选 cwd 与超时、UTF-8 宽松解码，Windows 下不弹控制台窗口；
//! - `path_exists`：探测文件系统路径存在性（.sdd/ 健康检查项）；
//! - `list_dir_names` / `copy_dir` / `read_text_file` / `write_text_file`：
//!   skills 安装器所需的目录清单与整树复制（对齐仓库根 install.sh 的
//!   「先删后拷」覆盖语义）；
//! - `chrys_skills_dir` / `chrys_sessions_dir`：用户级 chrys 目录解析
//!   （Windows 为 %APPDATA%/chrys/{skills,sessions}，其余为
//!   ~/.chrys/{skills,sessions}）。会话语义与 skills 同源：都在 chrys 的
//!   「配置根」下，只有宿主知道该根在哪，因此解析留在 Rust 侧一处。
//!
//! 前端经 `@tauri-apps/api/core` 的 invoke 调用；`run_command` /
//! `path_exists` 同时满足 `src/core/host.ts` 的 `HostRuntime` 契约
//!（返回形状是 `CommandResult { code, stdout, stderr }` 的超集），
//! `src/aaw/processRunner.ts` 依赖超集字段（ok / failure / durationMs）。

use std::time::Instant;

use serde::Serialize;

/// 单次命令执行结果（与前端 `CliRunResult` 字段一一对应）。
#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CliRunResult {
    /// 退出码为 0 且无执行失败时 true（超时 / 启动失败为 false）。
    pub ok: bool,
    /// 进程退出码；启动失败或超时被杀时为 -1（对齐 CommandResult 语义）。
    pub code: i32,
    /// stdout（UTF-8 宽松解码，坏字节替换为 U+FFFD）。
    pub stdout: String,
    /// stderr（同上）。
    pub stderr: String,
    /// 失败类别："timeout"（超时被杀）| "spawn"（命令不存在等启动失败）| None。
    pub failure: Option<String>,
    /// 实际执行耗时（毫秒）。
    pub duration_ms: u64,
}

/// 执行外部命令并等待退出（host.ts 的 run_command 契约 + cwd / 超时扩展；
/// 不传 cwd / timeoutMs 的调用方按无 cwd、默认 30s 超时执行）。
/// 程序名为空、超时、启动失败都以结构化字段返回，不 panic。
#[tauri::command]
pub async fn run_command(
    program: String,
    args: Vec<String>,
    cwd: Option<String>,
    timeout_ms: Option<u64>,
) -> Result<CliRunResult, String> {
    let started = Instant::now();
    let timeout = std::time::Duration::from_millis(timeout_ms.unwrap_or(30_000));

    if program.is_empty() {
        return Err("program 不能为空".to_string());
    }

    let mut command = tokio::process::Command::new(&program);
    command
        .args(args)
        .stdin(std::process::Stdio::null())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped());
    if let Some(dir) = cwd.as_deref() {
        command.current_dir(dir);
    }
    // Windows：chrys / uv 是控制台程序，不加该 flag 会闪出黑窗
    // （tokio 的 Command 自带 creation_flags，无需 std 的 CommandExt）
    #[cfg(target_os = "windows")]
    {
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = match command.spawn() {
        Ok(child) => child,
        Err(error) => {
            return Ok(CliRunResult {
                ok: false,
                code: -1,
                stdout: String::new(),
                stderr: error.to_string(),
                failure: Some("spawn".to_string()),
                duration_ms: started.elapsed().as_millis() as u64,
            });
        }
    };

    // 并发读 stdout / stderr 并等待退出（读管道与 wait 并行，
    // 避免子进程写满管道缓冲区导致死锁）
    let stdout_pipe = child.stdout.take();
    let stderr_pipe = child.stderr.take();
    let output = async {
        let (stdout, stderr, status) = tokio::join!(
            read_pipe_to_end(stdout_pipe),
            read_pipe_to_end(stderr_pipe),
            child.wait(),
        );
        (stdout, stderr, status)
    };

    match tokio::time::timeout(timeout, output).await {
        Ok((stdout, stderr, Ok(status))) => Ok(CliRunResult {
            ok: status.success(),
            code: status.code().unwrap_or(-1),
            stdout,
            stderr,
            failure: None,
            duration_ms: started.elapsed().as_millis() as u64,
        }),
        Ok((_stdout, _stderr, Err(error))) => Ok(CliRunResult {
            ok: false,
            code: -1,
            stdout: String::new(),
            stderr: error.to_string(),
            failure: Some("spawn".to_string()),
            duration_ms: started.elapsed().as_millis() as u64,
        }),
        Err(_) => {
            // 超时：async 块被丢弃后借用释放，kill 再等待回收，
            // 避免留下孤儿进程（对齐 Python 参考的进程树终止纪律）
            let _ = child.start_kill();
            let _ = child.wait().await;
            Ok(CliRunResult {
                ok: false,
                code: -1,
                stdout: String::new(),
                stderr: format!("命令执行超过 {}ms，已被终止", timeout.as_millis()),
                failure: Some("timeout".to_string()),
                duration_ms: started.elapsed().as_millis() as u64,
            })
        }
    }
}

/// 读子进程管道到 EOF，UTF-8 宽松解码（坏字节替换为 U+FFFD）。
async fn read_pipe_to_end<R>(mut pipe: Option<R>) -> String
where
    R: tokio::io::AsyncRead + Unpin,
{
    use tokio::io::AsyncReadExt;
    let Some(inner) = pipe.as_mut() else {
        return String::new();
    };
    let mut bytes = Vec::new();
    // 读失败（对端提前关闭等）：返回已读到的部分
    let _ = inner.read_to_end(&mut bytes).await;
    String::from_utf8_lossy(&bytes).into_owned()
}

/// 探测路径是否存在（文件或目录均可）。
#[tauri::command]
pub async fn path_exists(path: String) -> Result<bool, String> {
    match tokio::fs::metadata(&path).await {
        Ok(_) => Ok(true),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => Ok(false),
        Err(error) => Err(format!("探测路径 {} 失败：{}", path, error)),
    }
}

/// 列出目录的直接子目录名（不含文件），按名称排序保证清单展示稳定。
#[tauri::command]
pub fn list_dir_names(path: String) -> Result<Vec<String>, String> {
    let entries = std::fs::read_dir(&path)
        .map_err(|error| format!("读取目录失败 {path}: {error}"))?;
    let mut names: Vec<String> = entries
        .filter_map(|entry| entry.ok())
        .filter(|entry| {
            entry.file_type().map(|kind| kind.is_dir()).unwrap_or(false)
        })
        .map(|entry| entry.file_name().to_string_lossy().into_owned())
        .collect();
    names.sort();
    Ok(names)
}

fn copy_dir_recursive(src: &std::path::Path, dst: &std::path::Path) -> std::io::Result<()> {
    std::fs::create_dir_all(dst)?;
    for entry in std::fs::read_dir(src)? {
        let entry = entry?;
        let file_type = entry.file_type()?;
        let target = dst.join(entry.file_name());
        if file_type.is_dir() {
            copy_dir_recursive(&entry.path(), &target)?;
        } else {
            std::fs::copy(entry.path(), target)?;
        }
    }
    Ok(())
}

/// 整树复制 src → dst；dst 已存在时先删除（install.sh 的 rm -rf + cp -R
/// 覆盖语义，供 skills 安装器逐项覆盖安装）。
#[tauri::command]
pub fn copy_dir(src: String, dst: String) -> Result<(), String> {
    let (src, dst) = (std::path::Path::new(&src), std::path::Path::new(&dst));
    if !src.is_dir() {
        return Err(format!("源目录不存在或不是目录：{}", src.display()));
    }
    if dst.exists() {
        std::fs::remove_dir_all(dst).map_err(|error| {
            format!("删除既有目标失败 {}: {error}", dst.display())
        })?;
    }
    copy_dir_recursive(src, dst).map_err(|error| error.to_string())
}

#[tauri::command]
pub fn read_text_file(path: String) -> Result<String, String> {
    std::fs::read_to_string(&path)
        .map_err(|error| format!("读取文件失败 {path}: {error}"))
}

#[tauri::command]
pub fn write_text_file(path: String, contents: String) -> Result<(), String> {
    let target = std::path::Path::new(&path);
    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("创建父目录失败 {}: {error}", parent.display()))?;
    }
    std::fs::write(target, contents)
        .map_err(|error| format!("写入文件失败 {path}: {error}"))
}

/// 用户级 chrys 配置根目录（Windows 用 %APPDATA%，其余平台用 $HOME）。
/// skills 与 sessions 都挂在它下面；环境变量缺失的极端场景回落 `.chrys`，
/// 由界面提示用户检查环境。
fn chrys_root_dir() -> String {
    #[cfg(windows)]
    {
        if let Ok(appdata) = std::env::var("APPDATA") {
            return std::path::Path::new(&appdata)
                .join("chrys")
                .to_string_lossy()
                .replace('\\', "/");
        }
    }
    #[cfg(not(windows))]
    {
        if let Ok(home) = std::env::var("HOME") {
            return format!("{home}/.chrys");
        }
    }
    ".chrys".to_string()
}

/// 用户级 chrys skills 目录（对齐 install.sh chrys 分支的路径解析）。
#[tauri::command]
pub fn chrys_skills_dir() -> String {
    format!("{}/skills", chrys_root_dir())
}

/// 用户级 chrys 会话目录。历史会话记录（`<id>/session.json`）与其只读
/// 索引缓存（`.cache/session_catalog.json`）都在这里；左栏树在项目尚未
/// 连接时据此显示历史会话，不必先 spawn agent。
#[tauri::command]
pub fn chrys_sessions_dir() -> String {
    format!("{}/sessions", chrys_root_dir())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 进程内唯一的临时目录名（不引入 dev-dependency，用 std 能力拼）。
    fn temp_dir(label: &str) -> std::path::PathBuf {
        static COUNTER: std::sync::atomic::AtomicU32 =
            std::sync::atomic::AtomicU32::new(0);
        let seq = COUNTER.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        std::env::temp_dir().join(format!(
            "aaw-desktop-test-{}-{seq}-{label}",
            std::process::id()
        ))
    }

    /// 睡 30s 的命令（跨平台；配合短超时验证超时杀进程语义）。
    fn sleep_args() -> (String, Vec<String>) {
        #[cfg(target_os = "windows")]
        {
            (
                "cmd".to_string(),
                vec![
                    "/c".to_string(),
                    "ping".to_string(),
                    "-n".to_string(),
                    "30".to_string(),
                    "127.0.0.1".to_string(),
                ],
            )
        }
        #[cfg(not(target_os = "windows"))]
        {
            ("sleep".to_string(), vec!["30".to_string()])
        }
    }

    /// 回显一段文本的命令（跨平台）。
    fn echo_args(text: &str) -> (String, Vec<String>) {
        #[cfg(target_os = "windows")]
        {
            ("cmd".to_string(), vec!["/c".to_string(), format!("echo {text}")])
        }
        #[cfg(not(target_os = "windows"))]
        {
            ("echo".to_string(), vec![text.to_string()])
        }
    }

    #[tokio::test]
    async fn run_command_captures_stdout() {
        let (program, args) = echo_args("aaw-desktop-run-command-ok");
        let result = run_command(program, args, None, Some(10_000))
            .await
            .expect("run_command 不应返回 Err");
        assert!(result.ok);
        assert_eq!(result.code, 0);
        assert!(result.failure.is_none());
        assert!(result.stdout.contains("aaw-desktop-run-command-ok"));
    }

    #[tokio::test]
    async fn run_command_reports_spawn_failure() {
        let result = run_command(
            "no-such-aaw-desktop-command-xyz".to_string(),
            vec![],
            None,
            Some(5_000),
        )
        .await
        .expect("run_command 不应返回 Err");
        assert!(!result.ok);
        assert_eq!(result.code, -1);
        assert_eq!(result.failure.as_deref(), Some("spawn"));
    }

    #[tokio::test]
    async fn run_command_times_out_and_kills() {
        let (program, args) = sleep_args();
        let result = run_command(program, args, None, Some(300))
            .await
            .expect("run_command 不应返回 Err");
        assert!(!result.ok);
        assert_eq!(result.code, -1);
        assert_eq!(result.failure.as_deref(), Some("timeout"));
        assert!(result.stderr.contains("已被终止"));
        // 超时路径应按时返回（300ms + 杀进程回收），而不是等满 30s
        assert!(result.duration_ms < 10_000, "实际耗时 {}ms", result.duration_ms);
    }

    #[tokio::test]
    async fn run_command_rejects_empty_program() {
        assert!(run_command(String::new(), vec![], None, None).await.is_err());
    }

    #[test]
    fn copy_dir_replaces_target_tree() {
        let base = temp_dir("copy-dir");
        let src = base.join("src").join("skill");
        let dst = base.join("dst").join("skill");
        std::fs::create_dir_all(src.join("scripts")).expect("创建源目录");
        std::fs::write(src.join("SKILL.md"), "v2").expect("写源文件");
        std::fs::write(src.join("scripts").join("run.py"), "print(1)").expect("写脚本");
        // 目标侧预置旧内容（含目标侧才会有的多余文件），复制后应消失
        std::fs::create_dir_all(&dst).expect("创建目标目录");
        std::fs::write(dst.join("SKILL.md"), "v1").expect("写旧文件");
        std::fs::write(dst.join("stale.txt"), "旧文件").expect("写多余文件");

        copy_dir(
            src.to_string_lossy().into_owned(),
            dst.to_string_lossy().into_owned(),
        )
        .expect("copy_dir 应成功");

        assert_eq!(
            std::fs::read_to_string(dst.join("SKILL.md")).expect("读新文件"),
            "v2"
        );
        assert_eq!(
            std::fs::read_to_string(dst.join("scripts").join("run.py")).expect("读脚本"),
            "print(1)"
        );
        assert!(!dst.join("stale.txt").exists(), "先删后拷：多余文件应消失");

        // 源不存在 → Err
        assert!(copy_dir(
            base.join("missing").to_string_lossy().into_owned(),
            dst.to_string_lossy().into_owned()
        )
        .is_err());

        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn list_dir_names_dirs_only_sorted() {
        let base = temp_dir("list-dir");
        std::fs::create_dir_all(base.join("zz")).expect("创建目录 zz");
        std::fs::create_dir_all(base.join("aa")).expect("创建目录 aa");
        std::fs::write(base.join("file.txt"), "x").expect("写文件（不应入列）");
        let names = list_dir_names(base.to_string_lossy().into_owned())
            .expect("list_dir_names 应成功");
        assert_eq!(names, vec!["aa".to_string(), "zz".to_string()]);
        let _ = std::fs::remove_dir_all(&base);
    }

    #[tokio::test]
    async fn path_exists_true_false() {
        let file = temp_dir("path-exists");
        std::fs::create_dir_all(&file).expect("创建目录");
        assert_eq!(path_exists(file.to_string_lossy().into_owned()).await, Ok(true));
        assert_eq!(
            path_exists(file.join("nope").to_string_lossy().into_owned()).await,
            Ok(false)
        );
        let _ = std::fs::remove_dir_all(&file);
    }

    #[test]
    fn write_then_read_text_file_roundtrip() {
        let base = temp_dir("text-file");
        let file = base.join("nested").join("out.txt");
        write_text_file(
            file.to_string_lossy().into_owned(),
            "内容 line1\nline2".to_string(),
        )
        .expect("写文件应成功（自动建父目录）");
        assert_eq!(
            read_text_file(file.to_string_lossy().into_owned())
                .expect("读文件应成功"),
            "内容 line1\nline2"
        );
        let _ = std::fs::remove_dir_all(&base);
    }

    #[test]
    fn chrys_skills_dir_forward_slashes_and_suffix() {
        let dir = chrys_skills_dir();
        assert!(!dir.is_empty());
        assert!(!dir.contains('\\'), "应统一为 / 分隔：{dir}");
        assert!(dir.ends_with("chrys/skills"), "应落在 chrys/skills：{dir}");
    }

    #[test]
    fn chrys_sessions_dir_shares_root_with_skills() {
        let skills = chrys_skills_dir();
        let sessions = chrys_sessions_dir();
        assert!(!sessions.contains('\\'), "应统一为 / 分隔：{sessions}");
        assert!(
            sessions.ends_with("chrys/sessions"),
            "应落在 chrys/sessions：{sessions}"
        );
        // 两个目录必须同根：由同一个配置根拼出，不能各自解析
        let root = skills.trim_end_matches("/skills");
        assert_eq!(sessions.trim_end_matches("/sessions"), root);
    }
}

/// 关闭守卫确认后的强制关闭：destroy 跳过 CloseRequested 事件直关窗口。
#[tauri::command]
pub fn force_close(window: tauri::WebviewWindow) {
    let _ = window.destroy();
}
