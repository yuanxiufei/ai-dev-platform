use tauri::{AppHandle, Emitter};
use notify::{RecursiveMode, Event, EventKind, RecommendedWatcher, Config as NotifyConfig, Watcher};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use parking_lot::Mutex;
use std::time::{Instant, Duration};

#[derive(Clone, serde::Serialize)]
pub struct FileWatchEvent {
    pub paths: Vec<String>,
    pub event_type: String,
    #[serde(rename = "timestamp")]
    pub timestamp: u64,
}

/// File watcher state, held in an Arc for background task access
struct WatcherState {
    watcher: Option<RecommendedWatcher>,
    /// Paths and the instant they were last saved by our IDE (to suppress self-triggered events)
    recently_saved: Vec<(String, Instant)>,
    /// Debounce duration: ignore events within this window after our own save
    save_debounce_ms: u64,
}

impl WatcherState {
    fn new() -> Self {
        Self {
            watcher: None,
            recently_saved: Vec::new(),
            save_debounce_ms: 500,
        }
    }

    /// Register a path as just-saved — watcher will suppress Modify events for it
    fn mark_saved(&mut self, path: &str) {
        let normalized = Path::new(path).canonicalize()
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|_| path.to_string());
        self.recently_saved.push((normalized, Instant::now()));
        // Clean up stale entries (older than debounce window)
        let cutoff = Instant::now() - Duration::from_millis(self.save_debounce_ms);
        self.recently_saved.retain(|(_, t)| *t > cutoff);
    }

    /// Check if a path was recently saved by our IDE
    fn was_recently_saved(&mut self, event_paths: &[PathBuf]) -> bool {
        let cutoff = Instant::now() - Duration::from_millis(self.save_debounce_ms);
        self.recently_saved.retain(|(_, t)| *t > cutoff);

        let any_match = event_paths.iter().any(|ep| {
            let p = ep.canonicalize()
                .map(|cp| cp.to_string_lossy().to_string())
                .unwrap_or_else(|_| ep.to_string_lossy().to_string());
            self.recently_saved.iter().any(|(saved, _)| saved == &p)
        });

        if any_match {
            log::debug!("[FileWatcher] Suppressing event for recently-saved path(s)");
        }
        any_match
    }
}

/// Global watcher state — used by write_file to mark saves
static WATCHER_STATE: Mutex<Option<Arc<Mutex<WatcherState>>>> = Mutex::new(None);

/// Called by write_file after a successful save to prevent watcher feedback loop
pub fn notify_saved(path: &str) {
    let guard = WATCHER_STATE.lock();
    if let Some(ref state) = *guard {
        state.lock().mark_saved(path);
    }
}

pub fn init(app: &AppHandle) -> anyhow::Result<()> {
    let app_handle = app.clone();
    let state = Arc::new(Mutex::new(WatcherState::new()));
    
    // Store for external access (write_file will call notify_saved)
    *WATCHER_STATE.lock() = Some(state.clone());
    
    // Create a channel for receiving events
    let (tx, rx) = std::sync::mpsc::channel();
    
    // Create watcher (notify v7 API)
    let mut w = RecommendedWatcher::new(
        move |res: Result<Event, notify::Error>| {
            tx.send(res).ok();
        },
        NotifyConfig::default(),
    ).map_err(|e| anyhow::anyhow!("Failed to create file watcher: {}", e))?;
    
    // Watch common project directories
    let watch_paths = vec![
        PathBuf::from("."),
    ];
    
    for path in &watch_paths {
        let canonical = if let Ok(c) = path.canonicalize() { c } else { path.clone() };
        if canonical.exists() && canonical.is_dir() {
            w.watch(&canonical, RecursiveMode::Recursive).ok();
            log::info!("Watching directory: {:?}", canonical);
        }
    }
    
    state.lock().watcher = Some(w);
    
    // Handle events in a background task
    let handle_clone = app_handle.clone();
    let state_clone = state.clone();
    tauri::async_runtime::spawn(async move {
        while let Ok(result) = rx.recv() {
            match result {
                Ok(event) => {
                    // Suppress Modify events for files we just saved ourself
                    if matches!(&event.kind, EventKind::Modify(_)) {
                        if state_clone.lock().was_recently_saved(&event.paths) {
                            continue;
                        }
                    }

                    let event_type = match &event.kind {
                        EventKind::Create(_) => "created",
                        EventKind::Modify(_) => "modified",
                        EventKind::Remove(_) => "deleted",
                        _ => continue,
                    };

                    let timestamp = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .map(|d| d.as_millis() as u64)
                        .unwrap_or(0);

                    let watch_event = FileWatchEvent {
                        paths: event.paths.iter()
                            .map(|p| p.to_string_lossy().to_string())
                            .collect(),
                        event_type: event_type.to_string(),
                        timestamp,
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
