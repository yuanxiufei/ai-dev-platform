use tauri::AppHandle;

pub struct TerminalSession {
    pub id: String,
    pub shell: String,
    pub cwd: String,
}

pub fn init(_app: &AppHandle) -> anyhow::Result<()> {
    log::info!("Terminal manager initialized");
    Ok(())
}
