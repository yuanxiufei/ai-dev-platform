use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::process::{Command, Stdio, Child};
use parking_lot::Mutex;

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

// Store running processes
lazy_static::lazy_static! {
    static ref PROCESSES: Mutex<HashMap<u32, Child>> = Mutex::new(HashMap::new());
}

/// Spawn a new shell process
#[tauri::command]
pub async fn spawn_shell(config: ShellConfig) -> Result<ProcessInfo, String> {
    let shell = config.shell.unwrap_or_else(|| {
        if cfg!(target_os = "windows") { "powershell".to_string() }
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

    // On Windows with PowerShell
    if cfg!(target_os = "windows") && shell.contains("powershell") {
        cmd.args(&["-NoExit", "-Command", "-"]);
    } else {
        cmd.arg("-i");
    }

    match cmd.spawn() {
        Ok(child) => {
            let pid = child.id();
            let info = ProcessInfo {
                id: pid,
                command: format!("{} ({})", shell, config.cwd.unwrap_or_default()),
                cwd: config.cwd.unwrap_or_else(|| ".".to_string()),
                status: "running".to_string(),
            };
            
            PROCESSES.lock().insert(pid, child);
            Ok(info)
        }
        Err(e) => Err(format!("Failed to spawn shell: {}", e)),
    }
}

/// Write input to PTY (terminal)
#[tauri::command]
pub async fn write_to_pty(pid: u32, data: String) -> Result<(), String> {
    let mut processes = PROCESSES.lock();
    
    if let Some(child) = processes.get_mut(&pid) {
        if let Some(stdin) = child.stdin.as_mut() {
            use std::io::Write;
            stdin.write_all(data.as_bytes())
                .map_err(|e| format!("Failed to write to terminal: {}", e))?;
            stdin.flush()
                .map_err(|e| format!("Failed to flush terminal: {}", e))?;
            Ok(())
        } else {
            Err("Terminal stdin not available".to_string())
        }
    } else {
        Err(format!("Process {} not found", pid))
    }
}

/// Resize pseudo-terminal
#[tauri::command]
pub async fn resize_pty(_pid: u32, cols: u16, rows: u16) -> Result<(), String> {
    // In a real implementation, this would call ioctl/pty resize
    log::info!("Resizing terminal to {}x{}", cols, rows);
    Ok(())
}

/// Kill a process
#[tauri::command]
pub async fn kill_process(pid: u32) -> Result<(), String> {
    let mut processes = PROCESSES.lock();
    
    if let Some(mut child) = processes.remove(&pid) {
        child.kill()
            .map_err(|e| format!("Failed to kill process {}: {}", pid, e))?;
        Ok(())
    } else {
        Err(format!("Process {} not found", pid))
    }
}

/// List all active terminal processes
#[tauri::command]
pub async fn list_processes() -> Result<Vec<ProcessInfo>, String> {
    let processes = PROCESSES.lock();
    let result = processes.iter().map(|(&pid, _)| {
        ProcessInfo {
            id: pid,
            command: "shell".to_string(),
            cwd: ".".to_string(),
            status: "running".to_string(),
        }
    }).collect();

    Ok(result)
}
