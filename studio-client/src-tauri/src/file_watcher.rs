use tauri::{AppHandle, Emitter};
use notify::{Watcher, RecursiveMode, Event, EventKind, RecommendedWatcher};
use std::path::PathBuf;
use std::sync::Arc;
use parking_lot::Mutex;

#[derive(Clone, serde::Serialize)]
pub struct FileWatchEvent {
    pub paths: Vec<String>,
    pub event_type: String,
    #[serde(rename = "timestamp")]
    pub timestamp: u64,
}

pub fn init(app: &AppHandle) -> Result<()> {
    let app_handle = app.clone();
    let watcher: Arc<Mutex<Option<RecommendedWatcher>>> = Arc::new(Mutex::new(None));
    
    // Create a channel for receiving events
    let (tx, rx) = std::sync::mpsc::channel();
    
    // Spawn watcher thread
    let mut w = Watcher::new(tx, notify::Config::default())
        .map_err(|e| anyhow::anyhow!("Failed to create file watcher: {}", e))?;
    
    // Watch common project directories
    let watch_paths = vec![
        PathBuf::from("."),
    ];
    
    for path in &watch_paths {
        if path.exists() {
            w.watch(path, RecursiveMode::Recursive).ok();
            log::info!("Watching directory: {:?}", path);
        }
    }
    
    *watcher.lock() = Some(w);
    
    // Handle events in a background task
    let handle_clone = app_handle.clone();
    tauri::async_runtime::spawn(async move {
        while let Ok(result) = rx.recv() {
            match result {
                Ok(event) => {
                    let watch_event = match &event.kind {
                        EventKind::Create(_) => FileWatchEvent {
                            paths: event.paths.iter().map(|p| p.to_string_lossy().to_string()).collect(),
                            event_type: "created".to_string(),
                            timestamp: std::time::SystemTime::now()
                                .duration_since(std::time::UNIX_EPOCH)
                                .unwrap_or_default().as_millis() as u64,
                        },
                        EventKind::Modify(_) => FileWatchEvent {
                            paths: event.paths.iter().map(|p| p.to_string_lossy().to_string()).collect(),
                            event_type: "modified".to_string(),
                            timestamp: std::time::SystemTime::now()
                                .duration_since(std::time::UNIX_EPOCH)
                                .unwrap_or_default().as_millis() as u64,
                        },
                        EventKind::Remove(_) => FileWatchEvent {
                            paths: event.paths.iter().map(|p| p.to_string_lossy().to_string()).collect(),
                            event_type: "deleted".to_string(),
                            timestamp: std::time::SystemTime::now()
                                .duration_since(std::time::UNIX_EPOCH)
                                .unwrap_or_default().as_millis() as u64,
                        },
                        _ => continue,
                    };
                    
                    handle_clone.emit("file-watch-event", &watch_event).ok();
                }
                Err(e) => {
                    log::error!("File watcher error: {}", e);
                }
            }
        }
    });
    
    Ok(())
}
