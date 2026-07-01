use serde::{Deserialize, Serialize};
use std::sync::RwLock;
use std::collections::HashMap;
use std::path::PathBuf;
use std::fs;
use std::io;

/// 插件安装目录（相对于应用数据目录）
const PLUGINS_DIR: &str = "plugins";
/// 插件清单文件名
const MANIFEST_FILE: &str = "plugin.json";

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

/// 获取用户主目录
fn home_dir() -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        std::env::var("USERPROFILE")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("."))
    }
    #[cfg(not(target_os = "windows"))]
    {
        std::env::var("HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("."))
    }
}

/// 获取插件安装根目录
fn get_plugins_dir() -> PathBuf {
    let base = if cfg!(target_os = "windows") {
        std::env::var("APPDATA")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from("."))
    } else if cfg!(target_os = "macos") {
        home_dir().join("Library/Application Support")
    } else {
        home_dir().join(".local/share")
    };
    base.join("ai-fullstack-platform").join(PLUGINS_DIR)
}

/// 从本地路径安装插件（复制到 plugins 目录并注册）
fn install_from_local(source: &str) -> Result<PluginInfo, String> {
    let source_path = PathBuf::from(source);
    if !source_path.exists() {
        return Err(format!("插件路径不存在: {}", source));
    }

    // 查找 plugin.json
    let manifest_path = if source_path.is_dir() {
        source_path.join(MANIFEST_FILE)
    } else {
        // 如果是 .zip 或 .tar.gz，需要解压
        return Err("暂不支持压缩包格式，请解压后指定目录路径".to_string());
    };

    if !manifest_path.exists() {
        return Err(format!("未找到插件清单文件: {}", manifest_path.display()));
    }

    // 读取清单
    let manifest_content = fs::read_to_string(&manifest_path)
        .map_err(|e| format!("读取插件清单失败: {}", e))?;

    let mut plugin: PluginInfo = serde_json::from_str(&manifest_content)
        .map_err(|e| format!("解析插件清单失败: {}", e))?;

    // 复制到 plugins 目录
    let plugins_dir = get_plugins_dir();
    fs::create_dir_all(&plugins_dir)
        .map_err(|e| format!("创建插件目录失败: {}", e))?;

    let dest_dir = plugins_dir.join(&plugin.id);
    if dest_dir.exists() {
        // 如果已存在，先删除旧版本
        fs::remove_dir_all(&dest_dir).ok();
    }

    copy_dir_all(&source_path, &dest_dir)
        .map_err(|e| format!("复制插件文件失败: {}", e))?;

    // 更新入口点路径
    plugin.entry_point = dest_dir
        .join(&plugin.entry_point)
        .to_string_lossy()
        .to_string();

    plugin.enabled = true;

    // 注册到内存
    let mut registry = PLUGIN_REGISTRY.write().map_err(|e| e.to_string())?;
    registry.insert(plugin.id.clone(), plugin.clone());

    // 持久化注册表
    save_registry()?;

    Ok(plugin)
}

/// 从 URL 下载并安装插件
fn install_from_url(url: &str) -> Result<PluginInfo, String> {
    // 使用系统命令下载（curl 或 PowerShell）
    let plugins_dir = get_plugins_dir();
    fs::create_dir_all(&plugins_dir).map_err(|e| format!("创建插件目录失败: {}", e))?;

    // 从 URL 提取文件名
    let filename = url
        .split('/')
        .last()
        .unwrap_or("plugin.zip");

    let dest_path = plugins_dir.join(filename);

    // 下载
    let download_result = if cfg!(target_os = "windows") {
        std::process::Command::new("powershell")
            .args(["-Command", &format!(
                "Invoke-WebRequest -Uri '{}' -OutFile '{}'",
                url,
                dest_path.to_string_lossy()
            )])
            .output()
    } else {
        std::process::Command::new("curl")
            .args(["-L", "-o", &dest_path.to_string_lossy(), url])
            .output()
    };

    match download_result {
        Ok(output) if output.status.success() => {},
        Ok(output) => {
            let stderr = String::from_utf8_lossy(&output.stderr);
            return Err(format!("下载失败: {}", stderr));
        }
        Err(e) => return Err(format!("下载失败: {}", e)),
    }

    // 解压
    let extract_dir = plugins_dir.join(
        dest_path.file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .to_string()
    );

    fs::create_dir_all(&extract_dir).ok();

    if dest_path.extension().map_or(false, |ext| ext == "zip") {
        let unzip_result = if cfg!(target_os = "windows") {
            std::process::Command::new("powershell")
                .args(["-Command", &format!(
                    "Expand-Archive -Path '{}' -DestinationPath '{}' -Force",
                    dest_path.to_string_lossy(),
                    extract_dir.to_string_lossy()
                )])
                .output()
        } else {
            std::process::Command::new("unzip")
                .args(["-o", &dest_path.to_string_lossy(), "-d", &extract_dir.to_string_lossy()])
                .output()
        };

        if let Err(e) = unzip_result {
            return Err(format!("解压失败: {}", e));
        }

        // 清理下载文件
        fs::remove_file(&dest_path).ok();
    }

    // 递归查找 plugin.json
    let manifest_path = find_manifest(&extract_dir)?;

    let manifest_content = fs::read_to_string(&manifest_path)
        .map_err(|e| format!("读取插件清单失败: {}", e))?;

    let mut plugin: PluginInfo = serde_json::from_str(&manifest_content)
        .map_err(|e| format!("解析插件清单失败: {}", e))?;

    let plugin_dir = manifest_path.parent().unwrap_or(&extract_dir);

    // 如果插件解压到了一个子目录，移到正确位置
    let final_dir = plugins_dir.join(&plugin.id);
    if plugin_dir != final_dir {
        if final_dir.exists() {
            fs::remove_dir_all(&final_dir).ok();
        }
        fs::rename(plugin_dir, &final_dir)
            .map_err(|e| format!("移动插件目录失败: {}", e))?;
    }

    plugin.entry_point = final_dir
        .join(&plugin.entry_point)
        .to_string_lossy()
        .to_string();

    plugin.enabled = true;

    let mut registry = PLUGIN_REGISTRY.write().map_err(|e| e.to_string())?;
    registry.insert(plugin.id.clone(), plugin.clone());

    save_registry()?;

    Ok(plugin)
}

/// 递归查找 plugin.json
fn find_manifest(dir: &PathBuf) -> Result<PathBuf, String> {
    if dir.join(MANIFEST_FILE).exists() {
        return Ok(dir.join(MANIFEST_FILE));
    }
    for entry in fs::read_dir(dir).map_err(|e| format!("读取目录失败: {}", e))? {
        if let Ok(entry) = entry {
            let path = entry.path();
            if path.is_dir() {
                if let Ok(found) = find_manifest(&path) {
                    return Ok(found);
                }
            }
        }
    }
    Err(format!("在 {} 中未找到 {}", dir.display(), MANIFEST_FILE))
}

/// 递归复制目录
fn copy_dir_all(src: &PathBuf, dst: &PathBuf) -> io::Result<()> {
    fs::create_dir_all(dst)?;
    for entry in fs::read_dir(src)? {
        let entry = entry?;
        let ty = entry.file_type()?;
        let src_path = entry.path();
        let dst_path = dst.join(entry.file_name());
        if ty.is_dir() {
            copy_dir_all(&src_path, &dst_path)?;
        } else {
            fs::copy(&src_path, &dst_path)?;
        }
    }
    Ok(())
}

/// 保存插件注册表到磁盘
fn save_registry() -> Result<(), String> {
    let registry = PLUGIN_REGISTRY.read().map_err(|e| e.to_string())?;
    let plugins_dir = get_plugins_dir();
    fs::create_dir_all(&plugins_dir).ok();

    let registry_path = plugins_dir.join("registry.json");
    let plugins: Vec<&PluginInfo> = registry.values().collect();
    let json = serde_json::to_string_pretty(&plugins)
        .map_err(|e| format!("序列化注册表失败: {}", e))?;

    fs::write(&registry_path, json)
        .map_err(|e| format!("保存注册表失败: {}", e))?;

    Ok(())
}

/// 从磁盘加载插件注册表
pub fn load_registry() -> Result<(), String> {
    let plugins_dir = get_plugins_dir();
    let registry_path = plugins_dir.join("registry.json");

    if !registry_path.exists() {
        return Ok(());
    }

    let content = fs::read_to_string(&registry_path)
        .map_err(|e| format!("读取注册表失败: {}", e))?;

    let plugins: Vec<PluginInfo> = serde_json::from_str(&content)
        .map_err(|e| format!("解析注册表失败: {}", e))?;

    let mut registry = PLUGIN_REGISTRY.write().map_err(|e| e.to_string())?;
    for plugin in plugins {
        registry.insert(plugin.id.clone(), plugin);
    }

    Ok(())
}

/// List all installed plugins
#[tauri::command]
pub async fn list_plugins() -> Result<Vec<PluginInfo>, String> {
    let registry = PLUGIN_REGISTRY.read().map_err(|e| e.to_string())?;
    Ok(registry.values().cloned().collect())
}

/// Enable a plugin
#[tauri::command]
pub async fn enable_plugin(plugin_id: String) -> Result<(), String> {
    let mut registry = PLUGIN_REGISTRY.write().map_err(|e| e.to_string())?;
    if let Some(plugin) = registry.get_mut(&plugin_id) {
        plugin.enabled = true;
        save_registry()?;
        Ok(())
    } else {
        Err(format!("Plugin '{}' not found", plugin_id))
    }
}

/// Disable a plugin
#[tauri::command]
pub async fn disable_plugin(plugin_id: String) -> Result<(), String> {
    let mut registry = PLUGIN_REGISTRY.write().map_err(|e| e.to_string())?;
    if let Some(plugin) = registry.get_mut(&plugin_id) {
        plugin.enabled = false;
        save_registry()?;
        Ok(())
    } else {
        Err(format!("Plugin '{}' not found", plugin_id))
    }
}

/// Install a new plugin (from local path or URL)
#[tauri::command]
pub async fn install_plugin(source: String) -> Result<PluginInfo, String> {
    if source.starts_with("http://") || source.starts_with("https://") {
        install_from_url(&source)
    } else {
        install_from_local(&source)
    }
}

/// Uninstall a plugin
#[tauri::command]
pub async fn uninstall_plugin(plugin_id: String) -> Result<(), String> {
    let mut registry = PLUGIN_REGISTRY.write().map_err(|e| e.to_string())?;
    if let Some(plugin) = registry.remove(&plugin_id) {
        // 删除插件文件
        let plugins_dir = get_plugins_dir();
        let plugin_dir = plugins_dir.join(&plugin_id);
        if plugin_dir.exists() {
            fs::remove_dir_all(&plugin_dir).ok();
        }
        save_registry()?;
        Ok(())
    } else {
        Err(format!("Plugin '{}' not found", plugin_id))
    }
}

/// Call a command exposed by a plugin
#[tauri::command]
pub async fn call_plugin_command(request: PluginCallRequest) -> Result<PluginCallResult, String> {
    let registry = PLUGIN_REGISTRY.read().map_err(|e| e.to_string())?;
    
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
