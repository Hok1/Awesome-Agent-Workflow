//! 右栏 Git 只读查询。参数数组调用，输出有界，仓库根与项目范围分离。
use crate::panel_files::{absolute, display_path};
use serde::{Deserialize, Serialize};
use std::{
    collections::HashMap,
    path::{Component, Path, PathBuf},
    process::Stdio,
};
use tokio::io::{AsyncRead, AsyncReadExt};

const OUTPUT_LIMIT: usize = 2 * 1024 * 1024;
async fn drain<R: AsyncRead + Unpin>(mut reader: R) -> Result<(Vec<u8>, bool), String> {
    let mut result = Vec::new();
    let mut truncated = false;
    let mut buffer = [0u8; 8192];
    loop {
        let count = reader.read(&mut buffer).await.map_err(|e| e.to_string())?;
        if count == 0 {
            break;
        }
        let keep = count.min(OUTPUT_LIMIT.saturating_sub(result.len()));
        result.extend_from_slice(&buffer[..keep]);
        truncated |= keep < count;
    }
    Ok((result, truncated))
}

struct Output {
    code: i32,
    text: String,
    error: String,
    truncated: bool,
}
async fn git(cwd: &Path, args: &[&str]) -> Result<Output, String> {
    let mut command = tokio::process::Command::new("git");
    command
        .current_dir(cwd)
        .args([
            "--no-optional-locks",
            "--literal-pathspecs",
            "-c",
            "core.quotepath=false",
            "-c",
            "color.ui=false",
            "-c",
            "diff.external=",
        ])
        .args(args)
        .env("GIT_TERMINAL_PROMPT", "0")
        .env("GIT_PAGER", "cat")
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    #[cfg(target_os = "windows")]
    command.creation_flags(0x0800_0000);
    let mut child = command
        .spawn()
        .map_err(|e| format!("无法启动 Git，请检查是否已安装并加入 PATH：{e}"))?;
    let stdout = child.stdout.take().ok_or("Git stdout 不可用")?;
    let stderr = child.stderr.take().ok_or("Git stderr 不可用")?;
    let result = tokio::time::timeout(std::time::Duration::from_secs(20), async {
        let (out, err, status) = tokio::join!(drain(stdout), drain(stderr), child.wait());
        let (mut bytes, truncated) = out?;
        let (errors, _) = err?;
        // 字节上限可能恰好切在 UTF-8 字符中间；只丢掉这个不完整尾部。
        if truncated {
            if let Err(error) = std::str::from_utf8(&bytes) {
                if error.error_len().is_none() {
                    bytes.truncate(error.valid_up_to());
                }
            }
        }
        Ok::<_, String>(Output {
            code: status.map_err(|e| e.to_string())?.code().unwrap_or(-1),
            text: String::from_utf8(bytes)
                .map_err(|_| "Git 输出包含非 UTF-8 文件名或内容，暂不支持显示".to_string())?,
            error: String::from_utf8_lossy(&errors).into(),
            truncated,
        })
    })
    .await;
    match result {
        Ok(value) => value,
        Err(_) => {
            let _ = child.kill().await;
            let _ = child.wait().await;
            Err("Git 查询超过 20 秒，可手动重试".into())
        }
    }
}

async fn checked(cwd: &Path, args: &[&str]) -> Result<Output, String> {
    let out = git(cwd, args).await?;
    if out.code != 0 {
        return Err(format!("Git 查询失败：{}", out.error.trim()));
    }
    Ok(out)
}

#[derive(Clone, Debug, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Change {
    pub path: String,
    pub old_path: Option<String>,
    pub source: String,
    pub status: String,
    #[serde(default)]
    pub added: u64,
    #[serde(default)]
    pub removed: u64,
}
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Snapshot {
    pub repo_root: Option<String>,
    pub branch: String,
    pub changes: Vec<Change>,
    pub watch_paths: Vec<String>,
    pub upstream: Option<String>,
    pub branch_changes: Vec<Change>,
    pub branch_error: Option<String>,
}

fn within(path: &str, prefix: &str) -> bool {
    prefix.is_empty() || path == prefix || path.starts_with(&format!("{prefix}/"))
}

fn parse_status(text: &str, prefix: &str) -> Result<Vec<Change>, String> {
    let mut tokens = text.split('\0').filter(|s| !s.is_empty());
    let mut changes = Vec::new();
    while let Some(token) = tokens.next() {
        let bytes = token.as_bytes();
        if bytes.len() < 4 || bytes[2] != b' ' {
            return Err("Git 状态格式不完整".into());
        }
        let x = bytes[0] as char;
        let y = bytes[1] as char;
        let path = token[3..].to_string();
        let old = if matches!(x, 'R' | 'C') || matches!(y, 'R' | 'C') {
            Some(tokens.next().ok_or("Git 重命名记录不完整")?.to_string())
        } else {
            None
        };
        if !within(&path, prefix) && !old.as_ref().is_some_and(|p| within(p, prefix)) {
            continue;
        }
        let conflict = x == 'U' || y == 'U' || (x == 'A' && y == 'A') || (x == 'D' && y == 'D');
        if conflict {
            changes.push(Change {
                path,
                old_path: old,
                source: "conflict".into(),
                status: "冲突".into(),
                ..Default::default()
            });
            continue;
        }
        if x == '?' {
            changes.push(Change {
                path,
                old_path: None,
                source: "untracked".into(),
                status: "未跟踪".into(),
                ..Default::default()
            });
            continue;
        }
        for (code, source) in [(x, "staged"), (y, "unstaged")] {
            if code == ' ' || code == '!' {
                continue;
            }
            let source_old = if matches!(code, 'R' | 'C') {
                old.clone()
            } else {
                None
            };
            if !within(&path, prefix) && !source_old.as_ref().is_some_and(|p| within(p, prefix)) {
                continue;
            }
            let status = match code {
                'A' => "新增",
                'D' => "删除",
                'R' => "重命名",
                'C' => "复制",
                'T' => "类型变化",
                _ => "修改",
            };
            changes.push(Change {
                path: path.clone(),
                old_path: source_old,
                source: source.into(),
                status: status.into(),
                ..Default::default()
            });
        }
    }
    Ok(changes)
}

async fn resolve(project: &str) -> Result<Option<(PathBuf, String)>, String> {
    let project = absolute(project)?;
    let result = git(&project, &["rev-parse", "--show-toplevel"]).await?;
    if result.code != 0 {
        if result.error.contains("not a git repository") {
            return Ok(None);
        }
        return Err(result.error);
    }
    let root = absolute(result.text.trim())?;
    let prefix = project
        .strip_prefix(&root)
        .map_err(|_| "所选项目不在解析出的仓库内")?
        .to_string_lossy()
        .replace('\\', "/");
    Ok(Some((root, prefix)))
}

fn parse_numstat(text: &str, source: &str) -> Result<Vec<Change>, String> {
    let mut records = text.split('\0');
    let mut changes = Vec::new();
    while let Some(record) = records.next() {
        if record.is_empty() {
            continue;
        }
        let mut fields = record.splitn(3, '\t');
        let added = fields.next().ok_or("缺少新增统计")?;
        let removed = fields.next().ok_or("缺少删除统计")?;
        let name = fields.next().ok_or("缺少统计路径")?;
        let number = |s: &str| -> Result<u64, String> {
            if s == "-" {
                Ok(0)
            } else {
                s.parse().map_err(|_| "Git 行数统计无效".into())
            }
        };
        let (path, old_path) = if name.is_empty() {
            let old = records.next().ok_or("重命名统计缺少旧路径")?;
            let new = records.next().ok_or("重命名统计缺少新路径")?;
            if old.is_empty() || new.is_empty() {
                return Err("重命名统计缺少路径".into());
            }
            (new.to_string(), Some(old.to_string()))
        } else {
            (name.to_string(), None)
        };
        let added = number(added)?;
        let removed = number(removed)?;
        changes.push(Change {
            status: if old_path.is_some() {
                "重命名"
            } else if added > 0 && removed == 0 {
                "新增"
            } else if removed > 0 && added == 0 {
                "删除"
            } else {
                "修改"
            }
            .into(),
            path,
            old_path,
            source: source.into(),
            added,
            removed,
        });
    }
    Ok(changes)
}

async fn line_stats(
    root: &Path,
    source: &str,
    comparison: Option<&str>,
) -> Result<Vec<Change>, String> {
    let mut args = vec![
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--numstat",
        "-z",
        "--find-renames",
    ];
    if source == "staged" {
        args.push("--cached");
    }
    if let Some(value) = comparison {
        args.push(value);
    }
    args.push("--");
    let output = checked(root, &args).await?;
    if output.truncated {
        return Err("Git 行数统计超过 2 MiB 上限".into());
    }
    parse_numstat(&output.text, source)
}

async fn untracked_lines(path: PathBuf) -> u64 {
    async fn read(path: PathBuf) -> Result<u64, std::io::Error> {
        let metadata = tokio::fs::symlink_metadata(&path).await?;
        if !metadata.is_file() || metadata.len() > 1024 * 1024 {
            return Ok(0);
        }
        let mut file = tokio::fs::File::open(path).await?;
        let mut buffer = vec![0u8; 64 * 1024];
        let (mut size, mut lines, mut last) = (0, 0, b'\n');
        loop {
            let count = file.read(&mut buffer).await?;
            if count == 0 {
                return Ok(lines + u64::from(last != b'\n'));
            }
            size += count;
            if size > 1024 * 1024 || buffer[..count].contains(&0) {
                return Ok(0);
            }
            lines += buffer[..count]
                .iter()
                .filter(|&&byte| byte == b'\n')
                .count() as u64;
            last = buffer[count - 1];
        }
    }
    read(path).await.unwrap_or(0)
}

async fn upstream(root: &Path) -> Option<String> {
    git(
        root,
        &[
            "rev-parse",
            "--abbrev-ref",
            "--symbolic-full-name",
            "@{upstream}",
        ],
    )
    .await
    .ok()
    .filter(|out| out.code == 0)
    .map(|out| out.text.trim().to_string())
}

#[tauri::command]
pub async fn panel_git_status(project: String) -> Result<Snapshot, String> {
    let Some((root, prefix)) = resolve(&project).await? else {
        return Ok(Snapshot {
            repo_root: None,
            branch: String::new(),
            changes: vec![],
            watch_paths: vec![],
            upstream: None,
            branch_changes: vec![],
            branch_error: None,
        });
    };
    let (status, staged, unstaged) = tokio::join!(
        checked(
            &root,
            &["status", "--porcelain=v1", "-z", "--untracked-files=all"]
        ),
        line_stats(&root, "staged", None),
        line_stats(&root, "unstaged", None)
    );
    let status = status?;
    if status.truncated {
        return Err("Git 状态超过 2 MiB 上限".into());
    }
    let stats: HashMap<_, _> = staged?
        .into_iter()
        .chain(unstaged?)
        .map(|c| ((c.source, c.path), (c.added, c.removed)))
        .collect();
    let mut changes = parse_status(&status.text, &prefix)?;
    for change in &mut changes {
        let source = if change.source == "conflict" {
            "unstaged"
        } else {
            &change.source
        };
        if let Some(&(added, removed)) = stats.get(&(source.to_string(), change.path.clone())) {
            change.added = added;
            change.removed = removed;
        }
    }
    let jobs: Vec<_> = changes
        .iter()
        .enumerate()
        .filter(|(_, c)| c.source == "untracked")
        .map(|(index, c)| (index, root.join(&c.path)))
        .collect();
    let mut pending = tokio::task::JoinSet::new();
    for (index, path) in jobs {
        pending.spawn(async move { (index, untracked_lines(path).await) });
        if pending.len() >= 4 {
            let (index, lines) = pending
                .join_next()
                .await
                .unwrap()
                .map_err(|e| e.to_string())?;
            changes[index].added = lines;
        }
    }
    while let Some(result) = pending.join_next().await {
        let (index, lines) = result.map_err(|e| e.to_string())?;
        changes[index].added = lines;
    }
    // 沿用 ZCode Review：无可审查文本的未跟踪文件不出现在审查列表，仍可从文件树访问。
    changes.retain(|c| c.source != "untracked" || c.added > 0 || c.path.ends_with('/'));
    let branch = checked(&root, &["rev-parse", "--abbrev-ref", "HEAD"])
        .await
        .map(|r| r.text.trim().to_string())
        .unwrap_or_else(|_| "尚无提交".into());
    let upstream = upstream(&root).await;
    let (branch_changes, branch_error) = if let Some(base) = &upstream {
        match line_stats(&root, "branch", Some(&format!("{base}...HEAD"))).await {
            Ok(changes) => (
                changes
                    .into_iter()
                    .filter(|c| {
                        within(&c.path, &prefix)
                            || c.old_path.as_ref().is_some_and(|old| within(old, &prefix))
                    })
                    .collect(),
                None,
            ),
            Err(error) => (vec![], Some(error)),
        }
    } else {
        (vec![], None)
    };
    let metadata = checked(
        &root,
        &[
            "rev-parse",
            "--path-format=absolute",
            "--git-dir",
            "--git-common-dir",
        ],
    )
    .await?;
    let mut watch_paths = vec![display_path(&absolute(&project)?)];
    for path in metadata.text.lines() {
        let path = display_path(&absolute(path)?);
        if !watch_paths.contains(&path) {
            watch_paths.push(path);
        }
    }
    Ok(Snapshot {
        repo_root: Some(display_path(&root)),
        branch,
        changes,
        watch_paths,
        upstream,
        branch_changes,
        branch_error,
    })
}

fn safe_relative(path: &str) -> Result<(), String> {
    let path = Path::new(path);
    if path.as_os_str().is_empty()
        || path
            .components()
            .any(|c| !matches!(c, Component::Normal(_)))
    {
        return Err("Git 文件必须使用仓库内的相对路径".into());
    }
    Ok(())
}

#[derive(Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct Diff {
    pub patch: String,
    pub notice: Option<String>,
    pub before_content: Option<String>,
    pub after_content: Option<String>,
}

#[tauri::command]
pub async fn panel_git_diff(project: String, change: Change) -> Result<Diff, String> {
    let Some((root, prefix)) = resolve(&project).await? else {
        return Err("当前项目不是 Git 仓库".into());
    };
    safe_relative(&change.path)?;
    if let Some(old) = &change.old_path {
        safe_relative(old)?;
    }
    if !within(&change.path, &prefix)
        && !change.old_path.as_ref().is_some_and(|p| within(p, &prefix))
    {
        return Err("该变更不属于当前项目范围".into());
    }
    if change.source == "conflict" {
        return Ok(Diff {
            patch: String::new(),
            notice: Some("文件存在合并冲突，请查看当前文件；第一版不提供冲突编辑器".into()),
            ..Default::default()
        });
    }
    if change.source == "untracked" {
        let path = root.join(&change.path);
        // 不跟随未跟踪软链接读取仓库外内容。
        let meta = tokio::fs::symlink_metadata(&path)
            .await
            .map_err(|e| e.to_string())?;
        if meta.is_symlink() || !meta.is_file() {
            return Ok(Diff {
                patch: String::new(),
                notice: Some("未跟踪链接或目录，请在文件面板查看".into()),
                ..Default::default()
            });
        }
        let file = tokio::fs::File::open(&path)
            .await
            .map_err(|e| e.to_string())?;
        let mut bytes = Vec::new();
        file.take(1024 * 1024 + 1)
            .read_to_end(&mut bytes)
            .await
            .map_err(|e| e.to_string())?;
        if bytes.len() > 1024 * 1024 {
            return Ok(Diff {
                patch: String::new(),
                notice: Some("未跟踪文件超过 1 MiB 预览上限".into()),
                ..Default::default()
            });
        }
        if bytes.contains(&0) {
            return Ok(Diff {
                patch: String::new(),
                notice: Some("二进制文件无法显示文本差异".into()),
                ..Default::default()
            });
        }
        let content = String::from_utf8(bytes).map_err(|_| "文件不是有效 UTF-8 编码")?;
        let lines: Vec<_> = content.lines().collect();
        return Ok(Diff {
            patch: format!(
                "--- /dev/null\n+++ b/{}\n@@ -0,0 +1,{} @@\n{}",
                change.path,
                lines.len(),
                lines.iter().map(|s| format!("+{s}\n")).collect::<String>()
            ),
            notice: if content.is_empty() {
                Some("新文件为空".into())
            } else {
                None
            },
            before_content: Some(String::new()),
            after_content: Some(content),
        });
    }
    if !["staged", "unstaged", "branch"].contains(&change.source.as_str()) {
        return Err("不支持的差异来源".into());
    }
    let mut args = vec![
        "diff",
        "--no-ext-diff",
        "--no-textconv",
        "--no-color",
        "--find-renames",
        "--unified=3",
    ];
    if change.source == "staged" {
        args.push("--cached");
    }
    let base = if change.source == "branch" {
        let base = upstream(&root).await.ok_or("当前分支没有跟踪上游")?;
        Some(
            checked(&root, &["merge-base", &base, "HEAD"])
                .await?
                .text
                .trim()
                .to_string(),
        )
    } else {
        None
    };
    if let Some(base) = &base {
        args.push(base);
        args.push("HEAD");
    }
    args.push("--");
    args.push(&change.path);
    if let Some(old) = &change.old_path {
        args.push(old);
    }
    let result = checked(&root, &args).await?;
    let notice = if result.truncated {
        Some("差异超过 2 MiB，以下仅显示截断内容".into())
    } else if result.text.lines().any(|line| {
        (line.starts_with("Binary files ") && line.ends_with(" differ"))
            || line == "GIT binary patch"
    }) {
        Some("二进制文件无法显示文本差异".into())
    } else if result.text.is_empty() {
        Some("此项已无差异，请刷新变更列表".into())
    } else {
        None
    };
    let (before_content, after_content) = if notice.is_none() {
        full_contents(&root, &change, base.as_deref())
            .await
            .unwrap_or((None, None))
    } else {
        (None, None)
    };
    Ok(Diff {
        patch: result.text,
        notice,
        before_content,
        after_content,
    })
}

// 只有两侧读取都成功才提供全文，失败时保留原始 patch，不能把读取失败伪装成空文件。
async fn blob(root: &Path, revision: &str, path: &str) -> Result<String, String> {
    let object = format!("{revision}:{path}");
    let exists = git(root, &["ls-tree", "-z", revision, "--", path]).await?;
    if exists.code == 0 && exists.text.is_empty() {
        return Ok(String::new());
    }
    // 初始仓库没有 HEAD，暂存的新文件的旧内容确实为空。
    if revision == "HEAD" && git(root, &["rev-parse", "--verify", "HEAD"]).await?.code != 0 {
        return Ok(String::new());
    }
    let result = checked(root, &["show", &object]).await?;
    if result.truncated || result.text.len() > 1024 * 1024 || result.text.contains('\0') {
        return Err("全文超限或非文本".into());
    }
    Ok(result.text)
}
async fn index_blob(root: &Path, path: &str) -> Result<String, String> {
    let entries = checked(root, &["ls-files", "-s", "-z", "--", path]).await?;
    if entries.text.is_empty() {
        return Ok(String::new());
    }
    let result = checked(root, &["show", &format!(":{path}")]).await?;
    if result.truncated || result.text.len() > 1024 * 1024 || result.text.contains('\0') {
        return Err("全文超限或非文本".into());
    }
    Ok(result.text)
}
async fn full_contents(
    root: &Path,
    change: &Change,
    base: Option<&str>,
) -> Result<(Option<String>, Option<String>), String> {
    let old = change.old_path.as_deref().unwrap_or(&change.path);
    let (before, after) = if change.source == "branch" {
        (
            blob(root, base.ok_or("缺少比较基线")?, old).await?,
            blob(root, "HEAD", &change.path).await?,
        )
    } else if change.source == "staged" {
        (
            blob(root, "HEAD", old).await?,
            index_blob(root, &change.path).await?,
        )
    } else {
        let before = index_blob(root, old).await?;
        let path = root.join(&change.path);
        let after = match tokio::fs::symlink_metadata(&path).await {
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => String::new(),
            Err(error) => return Err(error.to_string()),
            Ok(meta) => {
                if !meta.is_file() || meta.len() > 1024 * 1024 {
                    return Err("文件不适合全文读取".into());
                }
                let file = tokio::fs::File::open(path)
                    .await
                    .map_err(|e| e.to_string())?;
                let mut bytes = Vec::new();
                file.take(1024 * 1024 + 1)
                    .read_to_end(&mut bytes)
                    .await
                    .map_err(|e| e.to_string())?;
                if bytes.len() > 1024 * 1024 || bytes.contains(&0) {
                    return Err("全文超限或非文本".into());
                }
                String::from_utf8(bytes).map_err(|_| "文件不是 UTF-8")?
            }
        };
        (before, after)
    };
    Ok((Some(before), Some(after)))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn scoped_status_keeps_cross_boundary_renames_and_both_sources() {
        let changes = parse_status(" M other/no.txt\0MM app/中文 name.ts\0R  other/new.ts\0app/old.ts\0?? app/empty\0UU app/conflict\0", "app").unwrap();
        assert_eq!(changes.len(), 5);
        assert_eq!(changes[0].source, "staged");
        assert_eq!(changes[1].source, "unstaged");
        assert_eq!(changes[2].old_path.as_deref(), Some("app/old.ts"));
        assert_eq!(changes[4].source, "conflict");
        assert!(!within("application/file", "app"));
        let moved_out = parse_status("RM other/new.txt\0app/old.txt\0", "app").unwrap();
        assert_eq!(moved_out.len(), 1);
        assert_eq!(moved_out[0].source, "staged");
        assert!(safe_relative("../outside").is_err());
    }

    #[tokio::test]
    async fn real_repository_handles_subdirectory_unborn_rename_and_binary() {
        let base = std::env::temp_dir().join(format!(
            "aaw-panel-git-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(base.join("app")).unwrap();
        std::fs::create_dir_all(base.join("other")).unwrap();
        checked(&base, &["init"]).await.unwrap();
        checked(&base, &["config", "user.name", "Panel Test"])
            .await
            .unwrap();
        checked(&base, &["config", "user.email", "panel@example.invalid"])
            .await
            .unwrap();
        let project = display_path(&base.join("app"));
        std::fs::write(base.join("app/中文 name.txt"), "before\n").unwrap();
        std::fs::write(base.join("other/hidden.txt"), "other\n").unwrap();
        std::fs::write(base.join("app/empty.txt"), "").unwrap();
        let initial = panel_git_status(project.clone()).await.unwrap();
        assert_eq!(initial.changes.len(), 1);
        assert_eq!(initial.changes[0].added, 1);
        assert!(initial.upstream.is_none());
        checked(&base, &["add", "."]).await.unwrap();
        let staged = panel_git_status(project.clone()).await.unwrap();
        assert!(
            staged
                .changes
                .iter()
                .all(|change| change.source == "staged")
        );
        let initial_diff = panel_git_diff(
            project.clone(),
            staged
                .changes
                .iter()
                .find(|c| c.path.ends_with("name.txt"))
                .unwrap()
                .clone(),
        )
        .await
        .unwrap();
        assert!(initial_diff.patch.contains("+before"));
        assert_eq!(initial_diff.before_content.as_deref(), Some(""));
        assert_eq!(initial_diff.after_content.as_deref(), Some("before\n"));
        checked(&base, &["commit", "-m", "fixture"]).await.unwrap();
        checked(&base, &["mv", "app/中文 name.txt", "other/moved.txt"])
            .await
            .unwrap();
        std::fs::write(base.join("app/binary.dat"), [0, 255, 1]).unwrap();
        let updated = panel_git_status(project.clone()).await.unwrap();
        let renamed = updated
            .changes
            .iter()
            .find(|c| c.status == "重命名")
            .unwrap()
            .clone();
        assert_eq!(renamed.old_path.as_deref(), Some("app/中文 name.txt"));
        assert!(
            panel_git_diff(project.clone(), renamed)
                .await
                .unwrap()
                .patch
                .contains("rename")
        );
        assert!(
            !updated
                .changes
                .iter()
                .any(|c| c.path.ends_with("binary.dat"))
        );
        let binary = Change {
            path: "app/binary.dat".into(),
            source: "untracked".into(),
            ..Default::default()
        };
        assert!(
            panel_git_diff(project, binary)
                .await
                .unwrap()
                .notice
                .unwrap()
                .contains("二进制")
        );
        // 仅清理本测试创建的独立临时仓库。
        assert!(base.starts_with(std::env::temp_dir()));
        std::fs::remove_dir_all(base).unwrap();
    }

    #[test]
    fn numstat_handles_binary_rename_and_tabs_in_names() {
        let changes = parse_numstat(
            "12\t3\t中文\tname.txt\0-\t-\tpicture.png\00\t0\t\0old.txt\0new.txt\0",
            "branch",
        )
        .unwrap();
        assert_eq!(changes.len(), 3);
        assert_eq!((changes[0].added, changes[0].removed), (12, 3));
        assert_eq!(changes[0].path, "中文\tname.txt");
        assert_eq!(changes[1].added, 0);
        assert_eq!(changes[2].old_path.as_deref(), Some("old.txt"));
        assert_eq!(changes[2].path, "new.txt");
        assert!(parse_numstat("1\t2\t\0old\0", "staged").is_err());
    }

    #[tokio::test]
    async fn staged_worktree_and_diverged_branch_use_separate_baselines() {
        let base = std::env::temp_dir().join(format!(
            "aaw-panel-stats-{}-{}",
            std::process::id(),
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&base).unwrap();
        checked(&base, &["init", "-b", "main"]).await.unwrap();
        checked(&base, &["config", "user.name", "Panel Test"])
            .await
            .unwrap();
        checked(&base, &["config", "user.email", "panel@example.invalid"])
            .await
            .unwrap();
        checked(&base, &["config", "core.autocrlf", "false"])
            .await
            .unwrap();
        std::fs::write(base.join("file.txt"), "base\n").unwrap();
        checked(&base, &["add", "."]).await.unwrap();
        checked(&base, &["commit", "-m", "base"]).await.unwrap();
        checked(&base, &["branch", "tracking"]).await.unwrap();
        checked(&base, &["branch", "--set-upstream-to=tracking"])
            .await
            .unwrap();
        std::fs::write(base.join("file.txt"), "base\nlocal\n").unwrap();
        checked(&base, &["commit", "-am", "local"]).await.unwrap();
        checked(&base, &["switch", "tracking"]).await.unwrap();
        std::fs::write(base.join("upstream-only.txt"), "remote\n").unwrap();
        checked(&base, &["add", "."]).await.unwrap();
        checked(&base, &["commit", "-m", "upstream diverged"])
            .await
            .unwrap();
        checked(&base, &["switch", "main"]).await.unwrap();
        std::fs::write(base.join("file.txt"), "staged\nlocal\n").unwrap();
        checked(&base, &["add", "."]).await.unwrap();
        std::fs::write(
            base.join("file.txt"),
            "staged\nlocal\nworktree\nBinary files a differ\n",
        )
        .unwrap();
        let project = display_path(&base);
        let snapshot = panel_git_status(project.clone()).await.unwrap();
        let staged = snapshot
            .changes
            .iter()
            .find(|c| c.source == "staged")
            .unwrap();
        let unstaged = snapshot
            .changes
            .iter()
            .find(|c| c.source == "unstaged")
            .unwrap();
        assert_eq!((staged.added, staged.removed), (1, 1));
        assert_eq!((unstaged.added, unstaged.removed), (2, 0));
        assert_eq!(snapshot.branch_changes.len(), 1); // 三点比较不把上游独有提交当作本地删除。
        assert_eq!(snapshot.branch_changes[0].added, 1);
        let diff = panel_git_diff(project.clone(), snapshot.branch_changes[0].clone())
            .await
            .unwrap();
        assert_eq!(diff.before_content.as_deref(), Some("base\n"));
        assert_eq!(diff.after_content.as_deref(), Some("base\nlocal\n"));
        let diff = panel_git_diff(project.clone(), staged.clone())
            .await
            .unwrap();
        assert_eq!(diff.after_content.as_deref(), Some("staged\nlocal\n"));
        let diff = panel_git_diff(project.clone(), unstaged.clone())
            .await
            .unwrap();
        assert_eq!(diff.before_content.as_deref(), Some("staged\nlocal\n"));
        assert!(diff.after_content.unwrap().contains("worktree"));
        assert!(diff.notice.is_none()); // 正文中的二进制提示字样不是 Git 二进制标头。
        checked(&base, &["mv", "file.txt", "renamed.txt"])
            .await
            .unwrap();
        let renamed = panel_git_status(project.clone()).await.unwrap();
        let working = renamed
            .changes
            .iter()
            .find(|c| c.source == "unstaged")
            .unwrap();
        assert!(working.old_path.is_none());
        assert_eq!(
            panel_git_diff(project.clone(), working.clone())
                .await
                .unwrap()
                .before_content
                .as_deref(),
            Some("staged\nlocal\n")
        );
        std::fs::remove_file(base.join("renamed.txt")).unwrap();
        let deleted = panel_git_status(project.clone()).await.unwrap();
        let working = deleted
            .changes
            .iter()
            .find(|c| c.source == "unstaged")
            .unwrap();
        assert_eq!(
            panel_git_diff(project, working.clone())
                .await
                .unwrap()
                .after_content
                .as_deref(),
            Some("")
        );
        for (name, bytes, expected) in [
            ("tail", b"a\nb".as_slice(), 2),
            ("empty", b"".as_slice(), 0),
            ("binary", b"a\0b".as_slice(), 0),
        ] {
            std::fs::write(base.join(name), bytes).unwrap();
            assert_eq!(untracked_lines(base.join(name)).await, expected);
        }
        std::fs::write(base.join("large"), vec![b'x'; 1024 * 1024 + 1]).unwrap();
        assert_eq!(untracked_lines(base.join("large")).await, 0);
        assert!(base.starts_with(std::env::temp_dir()));
        std::fs::remove_dir_all(base).unwrap();
    }
}
