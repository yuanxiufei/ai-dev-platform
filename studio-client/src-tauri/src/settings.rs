use tauri::AppHandle;

pub fn init(app: &AppHandle) -> anyhow::Result<()> {
    log::info!("Settings system initialized");
    Ok(())
}
