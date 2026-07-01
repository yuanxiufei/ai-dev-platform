use tauri::AppHandle;

pub fn init(_app: &AppHandle) -> anyhow::Result<()> {
    log::info!("Settings system initialized");
    Ok(())
}
