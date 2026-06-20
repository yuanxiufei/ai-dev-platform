use tauri::AppHandle;

pub fn init(app: &AppHandle) -> Result<()> {
    log::info!("Settings system initialized");
    Ok(())
}
