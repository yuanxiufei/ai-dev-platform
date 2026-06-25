use tauri::AppHandle;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::sync::{Arc, RwLock};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ShortcutEntry {
    pub key: String,
    pub command: String,
    pub when: Option<String>,
    pub description: String,
    pub category: String,
}

// Default keybindings
pub const DEFAULT_SHORTCUTS: &[(&str, &str, &str, &str)] = &[
    // File
    ("Ctrl+N", "file.new", "", "New File", "File"),
    ("Ctrl+O", "file.open", "", "Open File", "File"),
    ("Ctrl+S", "file.save", "", "Save File", "File"),
    ("Ctrl+Shift+S", "file.saveAs", "", "Save As...", "File"),
    ("Ctrl+W", "file.close", "", "Close Editor", "File"),
    ("Ctrl+Shift+W", "file.closeAll", "", "Close All Editors", "File"),
    
    // Edit
    ("Ctrl+Z", "edit.undo", "", "Undo", "Edit"),
    ("Ctrl+Shift+Z", "edit.redo", "", "Redo", "Edit"),
    ("Ctrl+X", "edit.cut", "", "Cut", "Edit"),
    ("Ctrl+C", "edit.copy", "", "Copy", "Edit"),
    ("Ctrl+V", "edit.paste", "", "Paste", "Edit"),
    ("Ctrl+A", "edit.selectAll", "", "Select All", "Edit"),
    ("Ctrl+F", "edit.find", "", "Find", "Edit"),
    ("Ctrl+H", "edit.replace", "", "Replace", "Edit"),
    ("Ctrl+D", "edit.selectNextOccurrence", "", "Select Next Occurrence", "Edit"),
    ("Ctrl+/", "edit.toggleLineComment", "", "Toggle Line Comment", "Edit"),
    ("Ctrl+[", "edit.indentOutdent", "", "Indent Less", "Edit"),
    ("]", "edit.indentIn", "", "Indent More", "Edit"),
    
    // View
    ("Ctrl+B", "view.toggleSidebar", "", "Toggle Sidebar", "View"),
    ("Ctrl+J", "view.togglePanel", "", "Toggle Panel", "View"),
    ("Ctrl+\\", "view.splitEditor", "", "Split Editor", "View"),
    ("Ctrl+=", "view.zoomIn", "", "Zoom In", "View"),
    ("Ctrl+-", "view.zoomOut", "", "Zoom Out", "View"),
    ("F11", "view.toggleFullscreen", "", "Toggle Fullscreen", "View"),
    
    // Navigation
    ("Ctrl+G", "navigation.gotoLine", "", "Go to Line...", "Navigation"),
    ("Ctrl+P", "navigation.quickOpen", "", "Quick Open File...", "Navigation"),
    ("Ctrl+Shift+E", "navigation.explorerFocus", "", "Focus Explorer", "Navigation"),
    ("Ctrl+Shift+F", "navigation.searchFocus", "", "Focus Search", "Navigation"),
    ("Ctrl+Shift+T", "navigation.reopenClosedTab", "", "Reopen Closed Tab", "Navigation"),
    
    // Terminal
    ("Ctrl+`", "terminal.toggle", "", "Toggle Terminal", "Terminal"),
    ("Ctrl+Shift+`", "terminal.new", "", "New Terminal", "Terminal"),
    
    // AI
    ("Ctrl+K Ctrl+I", "ai.inlineChat", "", "Inline Chat", "AI"),
    ("Ctrl+L", "ai.chatPanel", "", "AI Chat Panel", "AI"),
    
    // General
    ("Ctrl+Shift+P", "commandPalette.show", "", "Show Command Palette", "General"),
    ("Ctrl+,", "settings.open", "", "Open Settings", "General"),
    ("F5", "debug.start", "", "Start Debugging", "Debug"),
    ("F9", "debug.toggleBreakpoint", "", "Toggle Breakpoint", "Debug"),
];

/// Shortcut registry
lazy_static::lazy_static! {
    static ref SHORTCUT_REGISTRY: RwLock<HashMap<String, ShortcutEntry>> = RwLock::new(HashMap::new());
}

pub fn init(app: &AppHandle) -> anyhow::Result<()> {
    let mut registry = SHORTCUT_REGISTRY.write();
    
    // Register all default shortcuts
    for (key, command, when, description, category) in DEFAULT_SHORTCUTS {
        registry.insert(command.to_string(), ShortcutEntry {
            key: key.to_string(),
            command: command.to_string(),
            when: if when.is_empty() { None } else { Some(when.to_string()) },
            description: description.to_string(),
            category: category.to_string(),
        });
    }
    
    log::info!("Shortcut registry initialized with {} entries", DEFAULT_SHORTCUTS.len());
    Ok(())
}

pub fn lookup(key: &str) -> Vec<ShortcutEntry> {
    let registry = SHORTCUT_REGISTRY.read();
    registry.values()
        .filter(|s| s.key == key)
        .cloned()
        .collect()
}
