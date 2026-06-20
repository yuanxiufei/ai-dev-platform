use tauri::AppHandle;

pub fn init(app: &AppHandle) -> Result<()> {
    log::info!("Git integration initialized");
    Ok(())
}
