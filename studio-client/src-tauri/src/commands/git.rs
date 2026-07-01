use serde::{Deserialize, Serialize};
use std::process::Command;
use anyhow::{Result, Context};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GitStatus {
    pub branch: String,
    #[serde(rename = "ahead")]
    pub ahead: usize,
    #[serde(rename = "behind")]
    pub behind: usize,
    pub staged: Vec<GitFileStatus>,
    #[serde(rename = "unstaged")]
    pub unstaged: Vec<GitFileStatus>,
    #[serde(rename = "untracked")]
    pub untracked: Vec<String>,
    pub clean: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GitFileStatus {
    pub path: String,
    pub status: String, // A=added, M=modified, D=deleted, R=renamed
    #[serde(rename = "staged")]
    pub staged: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GitCommitInfo {
    pub hash: String,
    #[serde(rename = "shortHash")]
    pub short_hash: String,
    pub message: String,
    pub author: String,
    pub email: String,
    pub date: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GitBranch {
    pub name: String,
    #[serde(rename = "isCurrent")]
    pub is_current: bool,
    #[serde(rename = "isRemote")]
    pub is_remote: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GitDiff {
    pub path: String,
    #[serde(rename = "oldPath")]
    pub old_path: Option<String>,
    pub status: String,
    pub additions: usize,
    pub deletions: usize,
    #[serde(rename = "hunks")]
    pub hunks: Vec<GitDiffHunk>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GitDiffHunk {
    pub header: String,
    pub lines: Vec<GitDiffLine>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GitDiffLine {
    #[serde(rename = "type")]
    pub line_type: char, // +, -, or space
    pub content: String,
    #[serde(rename = "lineNumber")]
    pub line_number: Option<u32>,
}

fn run_git_command(dir: &str, args: &[&str]) -> Result<String> {
    let output = Command::new("git")
        .current_dir(dir)
        .args(args)
        .output()
        .with_context(|| format!("git {}", args.join(" ")))?;
    
    if output.status.success() {
        Ok(String::from_utf8_lossy(&output.stdout).to_string())
    } else {
        Err(anyhow::anyhow!(
            "git {} failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&output.stderr)
        ))
    }
}

/// Get git repository status
#[tauri::command]
pub async fn git_status(path: String) -> Result<GitStatus, String> {
    let branch_output = run_git_command(&path, &["--no-pager", "branch", "--show-current"])
        .unwrap_or_else(|_| "main".to_string());
    let branch = branch_output.trim().to_string();

    // Get ahead/behind
    let (ahead, behind) = match run_git_command(&path, &["rev-list", "--left-right", "--count", "HEAD...@{u}"]) {
        Ok(output) => {
            let parts: Vec<&str> = output.trim().split('\t').collect();
            (
                parts.get(0).and_then(|s| s.parse().ok()).unwrap_or(0),
                parts.get(1).and_then(|s| s.parse().ok()).unwrap_or(0),
            )
        }
        _ => (0, 0)
    };

    // Parse status output
    let status_output = run_git_command(&path, &["status", "--porcelain"])
        .unwrap_or_default();

    let mut staged = Vec::new();
    let mut unstaged = Vec::new();
    let mut untracked = Vec::new();

    for line in status_output.lines() {
        if line.len() >= 3 {
            let index_status = &line[..1];
            let worktree_status = &line[1..2];
            let file_path = line[3..].trim();
            
            if worktree_status == "?" {
                untracked.push(file_path.to_string());
                continue;
            }

            if index_status != " " && index_status != "?" {
                staged.push(GitFileStatus {
                    path: file_path.to_string(),
                    status: index_status.to_string(),
                    staged: true,
                });
            }
            
            if worktree_status != " " {
                unstaged.push(GitFileStatus {
                    path: file_path.to_string(),
                    status: worktree_status.to_string(),
                    staged: false,
                });
            }
        }
    }

    let clean = staged.is_empty() && unstaged.is_empty() && untracked.is_empty();
    Ok(GitStatus {
        branch,
        ahead,
        behind,
        staged,
        unstaged,
        untracked,
        clean,
    })
}

/// Get diff for a specific file or entire repo
#[tauri::command]
pub async fn git_diff(path: String, file: Option<String>, staged: Option<bool>) -> Result<Vec<GitDiff>, String> {
    let is_staged = staged.unwrap_or(false);
    
    let mut args = vec!["diff"];
    if is_staged { args.push("--cached"); }
    if let Some(f) = &file { args.push(f); }

    let output = run_git_command(&path, &args).map_err(|e| e.to_string())?;
    let diffs = parse_diff_output(&output);

    Ok(diffs)
}

/// Get commit log
#[tauri::command]
pub async fn git_log(path: String, limit: Option<usize>) -> Result<Vec<GitCommitInfo>, String> {
    let limit = limit.unwrap_or(20);
    let format = "%H|%h|%s|%an|%ae|%aI";
    
    let output = run_git_command(
        &path,
        &["log", &format!("-{}", limit), &format!("--format={}", format)]
    ).map_err(|e| e.to_string())?;

    let commits = output
        .lines()
        .filter(|l| !l.is_empty())
        .filter_map(|line| {
            let parts: Vec<&str> = line.split('|').collect();
            if parts.len() >= 6 {
                Some(GitCommitInfo {
                    hash: parts[0].to_string(),
                    short_hash: parts[1].to_string(),
                    message: parts[2].to_string(),
                    author: parts[3].to_string(),
                    email: parts[4].to_string(),
                    date: parts[5].to_string(),
                })
            } else { None }
        })
        .collect();

    Ok(commits)
}

/// Create a new commit
#[tauri::command]
pub async fn git_commit(path: String, message: String, files: Option<Vec<String>>) -> Result<String, String> {
    // Stage files if specified
    if let Some(files) = &files {
        for file in files {
            run_git_command(&path, &["add", file]).ok();
        }
    } else {
        run_git_command(&path, &["add", "-A"]).ok();
    }

    run_git_command(&path, &["commit", "-m", &message])
        .map(|output| output.trim().to_string())
        .map_err(|e| e.to_string())
}

/// List branches
#[tauri::command]
pub async fn git_branch(path: String) -> Result<Vec<GitBranch>, String> {
    let output = run_git_command(&path, &["branch", "-a", "--no-color"])
        .map_err(|e| e.to_string())?;

    let branches = output
        .lines()
        .filter_map(|line| {
            let trimmed = line.trim();
            let is_current = trimmed.starts_with('*');
            let name = trimmed.trim_start_matches('*').trim().trim_start_matches("remotes/");
            
            if name.contains("HEAD") { None } 
            else {
                Some(GitBranch {
                    name: name.to_string(),
                    is_current,
                    is_remote: line.contains("remotes/"),
                })
            }
        })
        .collect();

    Ok(branches)
}

/// Checkout a branch
#[tauri::command]
pub async fn git_checkout(path: String, branch: String, create_new: Option<bool>) -> Result<(), String> {
    if create_new.unwrap_or(false) {
        run_git_command(&path, &["checkout", "-b", &branch])
    } else {
        run_git_command(&path, &["checkout", &branch])
    }.map(|_| ()).map_err(|e| e.to_string())
}

/// Stash changes
#[tauri::command]
pub async fn git_stash(path: String, message: Option<String>, pop: Option<bool>) -> Result<(), String> {
    if pop.unwrap_or(false) {
        run_git_command(&path, &["stash", "pop"])
    } else {
        match &message {
            Some(msg) => run_git_command(&path, &["stash", "push", "-m", msg]),
            None => run_git_command(&path, &["stash"]),
        }
    }.map(|_| ()).map_err(|e| e.to_string())
}

/// Pull from remote
#[tauri::command]
pub async fn git_pull(path: String, remote: Option<String>, branch: Option<String>) -> Result<String, String> {
    let remote = remote.unwrap_or_else(|| "origin".to_string());
    let branch = branch.unwrap_or_default();
    
    if branch.is_empty() {
        run_git_command(&path, &["pull", &remote])
    } else {
        run_git_command(&path, &["pull", &remote, &branch])
    }.map(|o| o).map_err(|e| e.to_string())
}

/// Push to remote
#[tauri::command]
pub async fn git_push(path: String, remote: Option<String>, branch: Option<String>) -> Result<String, String> {
    let remote = remote.unwrap_or_else(|| "origin".to_string());
    let branch = branch.unwrap_or_default();
    
    if branch.is_empty() {
        run_git_command(&path, &["push", &remote])
    } else {
        run_git_command(&path, &["push", &remote, &branch])
    }.map(|o| o).map_err(|e| e.to_string())
}

fn parse_diff_output(output: &str) -> Vec<GitDiff> {
    /// 解析 unified diff 输出为结构化的 GitDiff 列表
    ///
    /// 解析以下格式:
    ///   diff --git a/path b/path
    ///   --- a/path
    ///   +++ b/path
    ///   @@ -a,b +c,d @@ context line
    ///   -removed line
    ///   +added line
    ///    context line
    let mut diffs: Vec<GitDiff> = Vec::new();
    let mut current_diff: Option<GitDiff> = None;
    let mut current_hunk: Option<GitDiffHunk> = None;
    let mut old_line: u32 = 0;
    let mut new_line: u32 = 0;

    for line in output.lines() {
        if line.starts_with("diff --git ") {
            // 保存上一个 diff
            if let Some(diff) = current_diff.take() {
                diffs.push(diff);
            }

            // 解析 diff --git a/path b/path
            let parts: Vec<&str> = line[11..].split_whitespace().collect();
            let path = parts.last().map(|p| p.trim_start_matches("b/")).unwrap_or("unknown");

            current_diff = Some(GitDiff {
                path: path.to_string(),
                old_path: parts.first().map(|p| p.trim_start_matches("a/").to_string()),
                status: "M".to_string(),
                additions: 0,
                deletions: 0,
                hunks: Vec::new(),
            });
            current_hunk = None;
        } else if line.starts_with("--- ") || line.starts_with("+++ ") {
            // 文件头行，可能更新 old_path
            if line.starts_with("--- ") && current_diff.is_some() {
                let path = line[4..].trim().trim_start_matches("a/");
                if path != "/dev/null" {
                    if let Some(ref mut diff) = current_diff {
                        diff.old_path = Some(path.to_string());
                    }
                }
            }
            if line.starts_with("--- /dev/null") {
                if let Some(ref mut diff) = current_diff {
                    diff.status = "A".to_string(); // 新文件
                }
            }
            if line.starts_with("+++ /dev/null") {
                if let Some(ref mut diff) = current_diff {
                    diff.status = "D".to_string(); // 删除文件
                }
            }
        } else if line.starts_with("@@") {
            // 保存上一个 hunk
            if let Some(hunk) = current_hunk.take() {
                if let Some(ref mut diff) = current_diff {
                    diff.hunks.push(hunk);
                }
            }

            // 解析 @@ -a,b +c,d @@
            if let Some(hunk_info) = parse_hunk_header(line) {
                old_line = hunk_info.0;
                new_line = hunk_info.1;
            }

            current_hunk = Some(GitDiffHunk {
                header: line.to_string(),
                lines: Vec::new(),
            });
        } else if line.starts_with('-') && !line.starts_with("---") {
            // 删除的行
            if let Some(ref mut diff) = current_diff {
                diff.deletions += 1;
            }
            if let Some(ref mut hunk) = current_hunk {
                hunk.lines.push(GitDiffLine {
                    line_type: '-',
                    content: line[1..].to_string(),
                    line_number: Some(old_line),
                });
            }
            old_line += 1;
        } else if line.starts_with('+') && !line.starts_with("+++") {
            // 添加的行
            if let Some(ref mut diff) = current_diff {
                diff.additions += 1;
            }
            if let Some(ref mut hunk) = current_hunk {
                hunk.lines.push(GitDiffLine {
                    line_type: '+',
                    content: line[1..].to_string(),
                    line_number: Some(new_line),
                });
            }
            new_line += 1;
        } else if line.starts_with(' ') || line.is_empty() {
            // 上下文行
            if let Some(ref mut hunk) = current_hunk {
                let content = if line.starts_with(' ') {
                    line[1..].to_string()
                } else {
                    String::new()
                };
                hunk.lines.push(GitDiffLine {
                    line_type: ' ',
                    content,
                    line_number: Some(new_line),
                });
            }
            old_line += 1;
            new_line += 1;
        } else if line == "\\ No newline at end of file" {
            // 忽略 "\ No newline at end of file" 标记
            continue;
        }
    }

    // 保存最后一个 hunk
    if let Some(hunk) = current_hunk.take() {
        if let Some(ref mut diff) = current_diff {
            if !hunk.lines.is_empty() {
                diff.hunks.push(hunk);
            }
        }
    }

    // 保存最后一个 diff
    if let Some(diff) = current_diff.take() {
        if !diff.hunks.is_empty() || diff.status == "A" || diff.status == "D" {
            diffs.push(diff);
        }
    }

    diffs
}

/// 解析 hunk 头部 @@ -old_start,old_count +new_start,new_count @@
/// 返回 (old_start, new_start)
fn parse_hunk_header(line: &str) -> Option<(u32, u32)> {
    // 查找 @@ ... @@ 模式
    let inner = line.trim_start_matches('@').trim_end_matches('@').trim();

    // 分割 "-a,b +c,d" 或 "-a +c"
    let parts: Vec<&str> = inner.split_whitespace().collect();
    if parts.len() < 2 {
        return None;
    }

    let old_start = parts[0]
        .trim_start_matches('-')
        .split(',')
        .next()?
        .parse::<u32>()
        .ok()?;

    let new_start = parts[1]
        .trim_start_matches('+')
        .split(',')
        .next()?
        .parse::<u32>()
        .ok()?;

    Some((old_start, new_start))
}
