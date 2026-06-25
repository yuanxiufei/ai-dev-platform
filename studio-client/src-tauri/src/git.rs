use tauri::AppHandle;

pub fn init(app: &AppHandle) -> anyhow::Result<()> {
    log::info!("Git integration initialized");
    Ok(())
}
