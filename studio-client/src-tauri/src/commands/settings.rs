use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use std::fs;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct IDESettings {
    // Editor Settings
    #[serde(rename = "editor")]
    pub editor: EditorSettings,
    
    // Appearance
    pub appearance: AppearanceSettings,
    
    // Terminal
    pub terminal: TerminalSettings,
    
    // Keybindings
    pub keybindings: KeybindingsSettings,
    
    // Files
    pub files: FileSettings,
    
    // AI
    pub ai: AISettings,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct EditorSettings {
    #[serde(rename = "fontSize")]
    pub font_size: u32,
    #[serde(rename = "fontFamily")]
    pub font_family: String,
    #[serde(rename = "tabSize")]
    pub tab_size: u32,
    #[serde(rename = "insertSpaces")]
    pub insert_spaces: bool,
    #[serde(rename = "wordWrap")]
    pub word_wrap: String,
    #[serde(rename = "lineNumbers")]
    pub line_numbers: String,
    #[serde(rename = "minimap")]
    pub minimap: bool,
    #[serde(rename = "autoSave")]
    pub auto_save: String,
    #[serde(rename = "formatOnSave")]
    pub format_on_save: bool,
    #[serde(rename = "bracketPairColorization")]
    pub bracket_pair_colorization: bool,
    #[serde(rename = "renderWhitespace")]
    pub render_whitespace: String,
    #[serde(rename = "cursorBlinking")]
    pub cursor_blinking: String,
    #[serde(rename = "scrollBeyondLastLine")]
    pub scroll_beyond_last_line: bool,
}

impl Default for EditorSettings {
    fn default() -> Self {
        Self {
            font_size: 14,
            font_family: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace".to_string(),
            tab_size: 4,
            insert_spaces: true,
            word_wrap: "off".to_string(),
            line_numbers: "on".to_string(),
            minimap: true,
            auto_save: "afterDelay".to_string(),
            format_on_save: true,
            bracket_pair_colorization: true,
            render_whitespace: "selection".to_string(),
            cursor_blinking: "smooth".to_string(),
            scroll_beyond_last_line: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct AppearanceSettings {
    pub theme: String,
    #[serde(rename = "accentColor")]
    pub accent_color: String,
    #[serde(rename = "sidebarWidth")]
    pub sidebar_width: u32,
    #[serde(rename = "panelHeight")]
    pub panel_height: u32,
    #[serde(rename = "zoomLevel")]
    pub zoom_level: f64,
}

impl Default for AppearanceSettings {
    fn default() -> Self {
        Self {
            theme: "codebuddy-dark".to_string(),
            accent_color: "#0078D4".to_string(),
            sidebar_width: 260,
            panel_height: 250,
            zoom_level: 0.0,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct TerminalSettings {
    pub shell: Option<String>,
    #[serde(rename = "fontSize")]
    pub font_size: u32,
    #[serde(rename = "fontFamily")]
    pub font_family: String,
    #[serde(rename = "defaultProfile")]
    pub default_profile: String,
    #[serde(rename = "cursorBlinking")]
    pub cursor_blinking: bool,
    #[serde(rename = "scrollback")]
    pub scrollback: usize,
}

impl Default for TerminalSettings {
    fn default() -> Self {
        Self {
            shell: None,
            font_size: 13,
            font_family: "'Cascadia Code', Consolas, monospace".to_string(),
            default_profile: "powershell".to_string(),
            cursor_blinking: true,
            scrollback: 10000,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct KeybindingsSettings {
    pub custom: Vec<KeybindingEntry>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KeybindingEntry {
    pub key: String,
    pub command: String,
    pub when: Option<String>,
}

impl Default for KeybindingsSettings {
    fn default() -> Self {
        Self { custom: Vec::new() }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct FileSettings {
    #[serde(rename = "excludePatterns")]
    pub exclude_patterns: Vec<String>,
    #[serde(rename = "maxRecentFiles")]
    pub max_recent_files: usize,
    #[serde(rename = "autoDetectIndentation")]
    pub auto_detect_indentation: bool,
}

impl Default for FileSettings {
    fn default() -> Self {
        Self {
            exclude_patterns: vec![
                "**/.git/**".into(), "**/node_modules/**".into(),
                "**/__pycache__/**".into(), "**/*.pyc".into(),
                "**/.next/**".into(), "**/dist/**".into(),
                "**/.DS_Store".into(),
            ],
            max_recent_files: 50,
            auto_detect_indentation: true,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct AISettings {
    pub provider: String,
    pub model: String,
    #[serde(rename = "apiKey")]
    pub api_key: String,
    #[serde(rename = "baseUrl")]
    pub base_url: Option<String>,
    #[serde(rename = "maxTokens")]
    pub max_tokens: u32,
    pub temperature: f64,
}

impl Default for AISettings {
    fn default() -> Self {
        Self {
            provider: "openai".to_string(),
            model: "gpt-4o".to_string(),
            api_key: String::new(),
            base_url: None,
            max_tokens: 4096,
            temperature: 0.7,
        }
    }
}

impl Default for IDESettings {
    fn default() -> Self {
        Self {
            editor: EditorSettings::default(),
            appearance: AppearanceSettings::default(),
            terminal: TerminalSettings::default(),
            keybindings: KeybindingsSettings::default(),
            files: FileSettings::default(),
            ai: AISettings::default(),
        }
    }
}

fn get_settings_path() -> PathBuf {
    dirs::config_dir()
        .unwrap_or_else(|| PathBuf::from("."))
        .join("codebuddy-ide")
        .join("settings.json")
}

/// Get current settings
#[tauri::command]
pub async fn get_settings() -> Result<IDESettings, String> {
    let path = get_settings_path();
    
    if path.exists() {
        let content = fs::read_to_string(&path)
            .map_err(|e| format!("Failed to read settings: {}", e))?;
        
        serde_json::from_str(&content)
            .map_err(|e| format!("Failed to parse settings: {}", e))
    } else {
        Ok(IDESettings::default())
    }
}

/// Save settings
#[tauri::command]
pub async fn save_settings(settings: IDESettings) -> Result<(), String> {
    let path = get_settings_path();
    
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to create config dir: {}", e))?;
    }

    let content = serde_json::to_string_pretty(&settings)
        .map_err(|e| format!("Failed to serialize settings: {}", e))?;

    fs::write(path, content)
        .map_err(|e| format!("Failed to write settings: {}", e))
}

/// Reset settings to defaults
#[tauri::command]
pub async fn reset_settings() -> Result<IDESettings, String> {
    let defaults = IDESettings::default();
    save_settings(defaults.clone()).await?;
    Ok(defaults)
}

/// Export settings to file
#[tauri::command]
pub async fn export_settings(destination: String) -> Result<(), String> {
    let settings = get_settings().await?;
    let content = serde_json::to_string_pretty(&settings)
        .map_err(|e| format!("Serialization error: {}", e))?;
    
    fs::write(&destination, content)
        .map_err(|e| format!("Failed to export settings: {}", e))
}

/// Import settings from file
#[tauri::command]
pub async fn import_settings(source: String) -> Result<IDESettings, String> {
    let content = fs::read_to_string(&source)
        .map_err(|e| format!("Failed to read file: {}", e))?;
    
    let settings: IDESettings = serde_json::from_str(&content)
        .map_err(|e| format!("Invalid settings format: {}", e))?;
    
    save_settings(settings.clone()).await?;
    Ok(settings)
}
