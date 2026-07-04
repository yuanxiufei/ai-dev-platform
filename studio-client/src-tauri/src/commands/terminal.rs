use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::process::{Command, Stdio, Child};
use std::sync::Arc;
use parking_lot::Mutex;
use tauri::{AppHandle, Emitter};
use std::io::{BufRead, BufReader};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShellConfig {
    pub shell: Option<String>,
    #[serde(rename = "cwd")]
    pub cwd: Option<String>,
    pub env: Option<HashMap<String, String>>,
    #[serde(rename = "cols")]
    pub cols: Option<u16>,
    #[serde(rename = "rows")]
    pub rows: Option<u16>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessInfo {
    pub id: u32,
    pub command: String,
    #[serde(rename = "cwd")]
    pub cwd: String,
    pub status: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TerminalOutput {
    pub pid: u32,
    pub data: String,
    #[serde(rename = "isError")]
    pub is_error: bool,
    #[serde(rename = "timestamp")]
    pub timestamp: u64,
}

/// Process registry: PID → (Child, AppHandle for event emission)
struct ProcessEntry {
    child: Child,
    app_handle: AppHandle,
}

lazy_static::lazy_static! {
    static ref PROCESSES: Arc<Mutex<HashMap<u32, ProcessEntry>>> = Arc::new(Mutex::new(HashMap::new()));
}

/// Spawn a shell process and start forwarding stdout/stderr as Tauri events
#[tauri::command]
pub async fn spawn_shell(app: AppHandle, config: ShellConfig) -> Result<ProcessInfo, String> {
    let shell = config.shell.unwrap_or_else(|| {
        if cfg!(target_os = "windows") { "powershell.exe".to_string() }
        else { "bash".to_string() }
    });

    let mut cmd = Command::new(&shell);
    cmd.stdin(Stdio::piped())
       .stdout(Stdio::piped())
       .stderr(Stdio::piped());

    if let Some(cwd) = &config.cwd {
        cmd.current_dir(cwd);
    }

    if let Some(env) = &config.env {
        for (k, v) in env {
            cmd.env(k, v);
        }
    }

    // PowerShell: no profile for faster startup
    if cfg!(target_os = "windows") && shell.contains("powershell") {
        cmd.arg("-NoLogo").arg("-NoProfile");
    }

    let cwd_display = config.cwd.clone().unwrap_or_else(|| ".".to_string());

    let mut child = cmd.spawn()
        .map_err(|e| format!("Failed to spawn {}: {}", shell, e))?;

    let pid = child.id();

    // Take stdout/stderr for async reading
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();

    // Store process
    {
        let mut procs = PROCESSES.lock();
        procs.insert(pid, ProcessEntry {
            child,
            app_handle: app.clone(),
        });
    }

    // Spawn stdout reader thread
    if let Some(stdout) = stdout {
        let app_clone = app.clone();
        std::thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                match line {
                    Ok(text) => {
                        let _ = app_clone.emit("terminal-output", TerminalOutput {
                            pid,
                            data: format!("{}\r\n", text),
                            is_error: false,
                            timestamp: std::time::SystemTime::now()
                                .duration_since(std::time::UNIX_EPOCH)
                                .unwrap_or_default()
                                .as_millis() as u64,
                        });
                    }
                    Err(_) => break,
                }
            }
            // Process ended → emit exit event
            let _ = app_clone.emit("terminal-exit", serde_json::json!({ "pid": pid }));
        });
    }

    // Spawn stderr reader thread
    if let Some(stderr) = stderr {
        let app_clone = app.clone();
        std::thread::spawn(move || {
            let reader = BufReader::new(stderr);
            for line in reader.lines() {
                if let Ok(text) = line {
                    let _ = app_clone.emit("terminal-output", TerminalOutput {
                        pid,
                        data: format!("{}\r\n", text),
                        is_error: true,
                        timestamp: std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap_or_default()
                            .as_millis() as u64,
                    });
                }
            }
        });
    }

    Ok(ProcessInfo {
        id: pid,
        command: format!("{} ({})", shell, cwd_display),
        cwd: cwd_display,
        status: "running".to_string(),
    })
}

/// Write input to the process stdin
#[tauri::command]
pub async fn write_to_pty(pid: u32, data: String) -> Result<(), String> {
    let mut procs = PROCESSES.lock();

    if let Some(entry) = procs.get_mut(&pid) {
        use std::io::Write;
        if let Some(stdin) = entry.child.stdin.as_mut() {
            stdin.write_all(data.as_bytes())
                .map_err(|e| format!("Failed to write to process: {}", e))?;
            stdin.flush()
                .map_err(|e| format!("Failed to flush: {}", e))?;
            Ok(())
        } else {
            Err("Process stdin not available".to_string())
        }
    } else {
        Err(format!("Process {} not found", pid))
    }
}

/// Resize terminal (no-op for piped processes, placeholder)
#[tauri::command]
pub async fn resize_pty(_pid: u32, cols: u16, rows: u16) -> Result<(), String> {
    log::info!("Terminal resize requested: {}x{}", cols, rows);
    Ok(())
}

/// Kill a process and its children
#[tauri::command]
pub async fn kill_process(pid: u32) -> Result<(), String> {
    let mut procs = PROCESSES.lock();

    if let Some(mut entry) = procs.remove(&pid) {
        entry.child.kill()
            .map_err(|e| format!("Failed to kill process {}: {}", pid, e))?;
        // Also try to kill process tree on Windows
        #[cfg(target_os = "windows")]
        {
            let _ = std::process::Command::new("taskkill")
                .args(["/F", "/T", "/PID", &pid.to_string()])
                .output();
        }
        Ok(())
    } else {
        Err(format!("Process {} not found", pid))
    }
}

/// List all active terminal processes
#[tauri::command]
pub async fn list_processes() -> Result<Vec<ProcessInfo>, String> {
    let procs = PROCESSES.lock();
    let result: Vec<ProcessInfo> = procs.iter().map(|(&pid, _)| {
        ProcessInfo {
            id: pid,
            command: "shell".to_string(),
            cwd: ".".to_string(),
            status: "running".to_string(),
        }
    }).collect();
    Ok(result)
}
