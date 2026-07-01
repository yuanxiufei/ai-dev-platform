use tauri::AppHandle;

#[allow(dead_code)]
pub fn init(_app: &AppHandle) -> anyhow::Result<()> {
    log::info!("Settings system initialized");
    Ok(())
}
