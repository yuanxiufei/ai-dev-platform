use tauri::AppHandle;
use std::collections::HashMap;
use std::sync::{Arc, Mutex};

pub struct TerminalSession {
    pub id: String,
    pub shell: String,
    pub cwd: String,
}

pub fn init(app: &AppHandle) -> Result<()> {
    log::info!("Terminal manager initialized");
    Ok(())
}
