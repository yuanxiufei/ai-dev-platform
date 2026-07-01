use tauri::WebviewWindow;

/// Toggle fullscreen mode
#[tauri::command]
pub async fn toggle_fullscreen(window: WebviewWindow) -> Result<(), String> {
    window
        .set_fullscreen(!window.is_fullscreen().unwrap_or(false))
        .map_err(|e| e.to_string())
}

/// Zoom in (scale up)
#[tauri::command]
pub async fn zoom_in(window: WebviewWindow) -> Result<(), String> {
    let scale = window.scale_factor().unwrap_or(1.0);
    let new_scale = (scale + 0.1).min(3.0);
    
    // Tauri v2 doesn't have a direct zoom API - we use CSS transform via JS eval
    let js = format!("document.body.style.zoom = '{}'", new_scale);
    window.eval(&js).map_err(|e| e.to_string())
}

/// Zoom out (scale down)
#[tauri::command]
pub async fn zoom_out(window: WebviewWindow) -> Result<(), String> {
    let scale = window.scale_factor().unwrap_or(1.0);
    let new_scale = (scale - 0.1).max(0.5);
    
    let js = format!("document.body.style.zoom = '{}'", new_scale);
    window.eval(&js).map_err(|e| e.to_string())
}

/// Reset zoom to 100%
#[tauri::command]
pub async fn reset_zoom(window: WebviewWindow) -> Result<(), String> {
    window.eval("document.body.style.zoom = '1'").map_err(|e| e.to_string())
}

/// Open DevTools
#[tauri::command]
pub async fn open_devtools(window: WebviewWindow) -> Result<(), String> {
    window.open_devtools();
    Ok(())
}

/// Focus the window
#[tauri::command]
pub async fn focus_window(window: WebviewWindow) -> Result<(), String> {
    window.set_focus().map_err(|e| e.to_string())
}
