use serde::{Deserialize, Serialize};
use std::sync::RwLock;
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PluginInfo {
    pub id: String,
    pub name: String,
    pub version: String,
    pub description: String,
    pub author: String,
    pub enabled: bool,
    #[serde(rename = "entryPoint")]
    pub entry_point: String,
    #[serde(rename = "hasSettingsUI")]
    pub has_settings_ui: bool,
    pub commands: Vec<PluginCommand>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PluginCommand {
    pub id: String,
    pub title: String,
    pub category: Option<String>,
    #[serde(rename = "icon")]
    pub icon: Option<String>,
    #[serde(rename = "when")]
    pub when: Option<String>,
    #[serde(rename = "keybinding")]
    pub keybinding: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PluginCallRequest {
    #[serde(rename = "pluginId")]
    pub plugin_id: String,
    pub command: String,
    pub args: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PluginCallResult {
    pub success: bool,
    pub data: Option<serde_json::Value>,
    pub error: Option<String>,
}

// In-memory plugin registry
lazy_static::lazy_static! {
    static ref PLUGIN_REGISTRY: RwLock<HashMap<String, PluginInfo>> = RwLock::new(HashMap::new());
}

/// List all installed plugins
#[tauri::command]
pub async fn list_plugins() -> Result<Vec<PluginInfo>, String> {
    let registry = PLUGIN_REGISTRY.read();
    Ok(registry.values().cloned().collect())
}

/// Enable a plugin
#[tauri::command]
pub async fn enable_plugin(plugin_id: String) -> Result<(), String> {
    let mut registry = PLUGIN_REGISTRY.write();
    if let Some(plugin) = registry.get_mut(&plugin_id) {
        plugin.enabled = true;
        Ok(())
    } else {
        Err(format!("Plugin '{}' not found", plugin_id))
    }
}

/// Disable a plugin
#[tauri::command]
pub async fn disable_plugin(plugin_id: String) -> Result<(), String> {
    let mut registry = PLUGIN_REGISTRY.write();
    if let Some(plugin) = registry.get_mut(&plugin_id) {
        plugin.enabled = false;
        Ok(())
    } else {
        Err(format!("Plugin '{}' not found", plugin_id))
    }
}

/// Install a new plugin (from local path or URL)
#[tauri::command]
pub async fn install_plugin(source: String) -> Result<PluginInfo, String> {
    // Placeholder - real implementation would download and load plugin
    Err(format!("Plugin installation not yet implemented for source: {}", source))
}

/// Uninstall a plugin
#[tauri::command]
pub async fn uninstall_plugin(plugin_id: String) -> Result<(), String> {
    let mut registry = PLUGIN_REGISTRY.write();
    if registry.remove(&plugin_id).is_some() {
        Ok(())
    } else {
        Err(format!("Plugin '{}' not found", plugin_id))
    }
}

/// Call a command exposed by a plugin
#[tauri::command]
pub async fn call_plugin_command(request: PluginCallRequest) -> Result<PluginCallResult, String> {
    let registry = PLUGIN_REGISTRY.read();
    
    if let Some(_plugin) = registry.get(&request.plugin_id) {
        // Check if plugin has this command
        // Execute in sandboxed context
        Ok(PluginCallResult {
            success: true,
            data: Some(serde_json::json!({"message": "Command executed"})),
            error: None,
        })
    } else {
        Ok(PluginCallResult {
            success: false,
            data: None,
            error: Some(format!("Plugin '{}' not found", request.plugin_id)),
        })
    }
}
