use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::fs;
use walkdir::WalkDir;
use chrono::{DateTime, Utc};
use anyhow::Result;

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct FileInfo {
    pub name: String,
    pub path: String,
    #[serde(rename = "isDirectory")]
    pub is_directory: bool,
    #[serde(rename = "isFile")]
    pub is_file: bool,
    pub size: u64,
    #[serde(rename = "modifiedTime")]
    pub modified_time: String,
    #[serde(rename = "createdTime")]
    pub created_time: Option<String>,
    pub extension: Option<String>,
    pub readonly: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct ReadDirectoryRequest {
    pub path: String,
    #[serde(rename = "showHidden")]
    pub show_hidden: Option<bool>,
    #[serde(rename = "deep")]
    pub deep: Option<bool>,
    #[serde(rename = "maxDepth")]
    pub max_depth: Option<usize>,
    pub extensions: Option<Vec<String>>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct SearchRequest {
    pub path: String,
    pub pattern: String,
    #[serde(rename = "includePatterns")]
    pub include_patterns: Option<Vec<String>>,
    #[serde(rename = "excludePatterns")]
    pub exclude_patterns: Option<Vec<String>>,
    #[serde(rename = "useRegex")]
    pub use_regex: Option<bool>,
    #[serde(rename = "caseSensitive")]
    pub case_sensitive: Option<bool>,
    #[serde(rename = "wholeWord")]
    pub whole_word: Option<bool>,
    #[serde(rename = "maxResults")]
    pub max_results: Option<usize>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct SearchResult {
    pub file: String,
    pub line: u32,
    pub column: u32,
    pub text: String,
    #[serde(rename = "matchLength")]
    pub match_length: usize,
    #[serde(rename = "previewBefore")]
    pub preview_before: String,
    #[serde(rename = "previewAfter")]
    pub preview_after: String,
}

/// Read directory contents
#[tauri::command]
pub async fn read_directory(request: ReadDirectoryRequest) -> Result<Vec<FileInfo>, String> {
    let path = Path::new(&request.path);
    
    if !path.exists() {
        return Err(format!("Path does not exist: {}", request.path));
    }

    let show_hidden = request.show_hidden.unwrap_or(false);
    let extensions = request.extensions.as_ref();
    let mut entries = Vec::new();

    if let Ok(read_dir) = fs::read_dir(path) {
        for entry in read_dir.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            
            // Skip hidden files unless requested
            if !show_hidden && name.starts_with('.') {
                continue;
            }
            
            let metadata = match entry.metadata() {
                Ok(m) => m,
                Err(_) => continue,
            };

            let is_dir = metadata.is_dir();
            let is_file = metadata.is_file();
            let ext = if is_file {
                Path::new(&name).extension()
                    .map(|e| e.to_string_lossy().to_string())
                    .filter(|e| !e.is_empty())
            } else { None };

            // Filter by extension
            if let Some(exts) = extensions {
                if let Some(ref file_ext) = ext {
                    if !exts.iter().any(|e| e.eq_ignore_ascii_case(file_ext)) {
                        continue;
                    }
                } else if !exts.contains(&"*".to_string()) {
                    continue;
                }
            }

            let modified_time = metadata.modified()
                .ok()
                .and_then(|t| DateTime::<Utc>::from(t).to_rfc3339().into())
                .unwrap_or_else(|| String::new());

            let created_time = metadata.created()
                .ok()
                .map(|t| DateTime::<Utc>::from(t).to_rfc3339());

            entries.push(FileInfo {
                name,
                path: entry.path().to_string_lossy().to_string(),
                is_directory: is_dir,
                is_file,
                size: metadata.len(),
                modified_time,
                created_time,
                extension: ext,
                readonly: metadata.permissions().readonly(),
            });
        }
    }

    // Sort: directories first, then alphabetically
    entries.sort_by(|a, b| {
        match (a.is_directory, b.is_directory) {
            (true, false) => std::cmp::Ordering::Less,
            (false, true) => std::cmp::Ordering::Greater,
            _ => a.name.to_lowercase().cmp(&b.name.to_lowercase()),
        }
    });

    Ok(entries)
}

/// Read file content
#[tauri::command]
pub async fn read_file(path: String, encoding: Option<String>) -> Result<String, String> {
    let _encoding = encoding.unwrap_or_else(|| "utf-8".to_string());
    fs::read_to_string(&path)
        .map_err(|e| format!("Failed to read file: {}", e))
}

/// Write file content
#[tauri::command]
pub async fn write_file(path: String, content: String) -> Result<(), String> {
    // Create parent directories if needed
    if let Some(parent) = Path::new(&path).parent() {
        if !parent.exists() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("Failed to create directory: {}", e))?;
        }
    }
    
    fs::write(&path, content.as_bytes())
        .map_err(|e| format!("Failed to write file: {}", e))
}

/// Create new file
#[tauri::command]
pub async fn create_file(path: String) -> Result<FileInfo, String> {
    let p = Path::new(&path);
    
    if let Some(parent) = p.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to create parent dir: {}", e))?;
    }

    File::create(p)
        .map_err(|e| format!("Failed to create file: {}", e))?;

    get_file_info(path).await
}

/// Create new directory
#[tauri::command]
pub async fn create_directory(path: String) -> Result<FileInfo, String> {
    fs::create_dir_all(&path)
        .map_err(|e| format!("Failed to create directory: {}", e))?;
    
    get_file_info(path).await
}

/// Delete file or directory
#[tauri::command]
pub async fn delete_path(path: String, recursive: Option<bool>) -> Result<(), String> {
    let recursive = recursive.unwrap_or(true);
    let p = Path::new(&path);

    if p.is_dir() && recursive {
        fs::remove_dir_all(p)
    } else if p.is_dir() {
        fs::remove_dir(p)
    } else {
        fs::remove_file(p)
    }.map_err(|e| format!("Failed to delete {}: {}", path, e))
}

/// Rename or move path
#[tauri::command]
pub async fn rename_path(old_path: String, new_path: String) -> Result<FileInfo, String> {
    if let Some(parent) = Path::new(&new_path).parent() {
        if !parent.exists() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("Failed to create parent dir: {}", e))?;
        }
    }

    fs::rename(&old_path, &new_path)
        .map_err(|e| format!("Failed to rename: {}", e))?;

    get_file_info(new_path).await
}

#[tauri::command]
pub async fn copy_path(src: String, dst: String) -> Result<FileInfo, String> {
    let src_p = Path::new(&src);
    let dst_p = Path::new(&dst);

    if src_p.is_dir() {
        copy_dir_recursive(src_p, dst_p)?;
    } else {
        if let Some(parent) = dst_p.parent() {
            fs::create_dir_all(parent)
                .map_err(|e| format!("Failed to create parent dir: {}", e))?;
        }
        fs::copy(src_p, dst_p)
            .map_err(|e| format!("Failed to copy: {}", e))?;
    }

    get_file_info(dst).await
}

fn copy_dir_recursive(src: &Path, dst: &Path) -> Result<()> {
    fs::create_dir_all(dst)?;
    for entry in WalkDir::new(src).min_depth(1) {
        let entry = entry.map_err(|e| e.to_string())?;
        let dest_path = dst.join(entry.file_name());
        if entry.path().is_dir() {
            fs::create_dir_all(&dest_path)?;
        } else {
            fs::copy(entry.path(), &dest_path)?;
        }
    }
    Ok(())
}

/// Move path
#[tauri::command]
pub async fn move_path(src: String, dst: String) -> Result<FileInfo, String> {
    rename_path(src, dst).await
}

/// Search files in directory
#[tauri::command]
pub async fn search_files(request: SearchRequest) -> Result<Vec<String>, String> {
    let mut results = Vec::new();
    let pattern = if request.use_regex.unwrap_or(false) {
        regex::Regex::new(&request.pattern)
            .map_err(|e| format!("Invalid regex: {}", e))?
    } else {
        let escaped = regex::escape(&request.pattern);
        regex::Regex::new(&escaped)
            .map_err(|e| format!("Invalid pattern: {}", e))?
    };
    
    let case_insensitive = !request.case_sensitive.unwrap_or(false);
    let search_pattern = if case_insensitive {
        regex::RegexBuilder::new(&request.pattern)
            .case_insensitive(true)
            .build()
            .map_err(|e| format!("Invalid pattern: {}", e))?
    } else {
        pattern.clone()
    };

    let max_results = request.max_results.unwrap_or(1000);
    let walker = WalkDir::new(&request.path)
        .follow_links(false)
        .into_iter()
        .filter_entry(|e| {
            if let Some(excludes) = &request.exclude_patterns {
                let name = e.file_name().to_string_lossy();
                !excludes.any(|p| name.contains(&p.replace("*", "")))
            } else {
                true
            }
        });

    for entry in walker {
        if results.len() >= max_results {
            break;
        }
        
        if let Ok(entry) = entry {
            if entry.file_type().is_file() {
                let name = entry.file_name().to_string_lossy().to_string();
                
                if let Some(includes) = &request.include_patterns {
                    if !includes.iter().any(|p| {
                        if p.starts_with('.') {
                            name.ends_with(p)
                        } else {
                            name.contains(&p.replace(".", ""))
                        }
                    }) {
                        continue;
                    }
                }

                if search_pattern.is_match(&name) {
                    results.push(entry.path().to_string_lossy().to_string());
                }
            }
        }
    }

    Ok(results)
}

/// Search content within files
#[tauri::command]
pub async fn search_in_file(request: SearchRequest) -> Result<Vec<SearchResult>, String> {
    let mut results = Vec::new();
    let max_results = request.max_results.unwrap_or(500);
    
    let re_builder = if request.case_sensitive.unwrap_or(false) {
        regex::RegexBuilder::new(&request.pattern)
    } else {
        regex::RegexBuilder::new(&request.pattern).case_insensitive(true)
    };
    
    let re = re_builder
        .dot_matches_new_line(false)
        .build()
        .map_err(|e| format!("Invalid regex: {}", e))?;

    let walker = WalkDir::new(&request.path)
        .follow_links(false)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| {
            if !e.file_type().is_file() {
                return false;
            }
            if let Some(excludes) = &request.exclude_patterns {
                let name = e.file_name().to_string_lossy();
                !excludes.iter().any(|p| {
                    let clean_p = p.trim_start_matches('*').trim_start_matches('.');
                    name.ends_with(clean_p) || name.contains(clean_p)
                })
            } else {
                true
            }
        });

    for entry in walker {
        if results.len() >= max_results {
            break;
        }

        let path_str = entry.path().to_string_lossy().to_string();

        if let Ok(content) = fs::read_to_string(entry.path()) {
            for (line_idx, line) in content.lines().enumerate() {
                for m in re.find_iter(line) {
                    if results.len() >= max_results {
                        break;
                    }

                    let start = m.start().saturating_sub(20);
                    let end = (m.end() + 20).min(line.len());

                    results.push(SearchResult {
                        file: path_str.clone(),
                        line: (line_idx + 1) as u32,
                        column: (m.start() + 1) as u32,
                        text: m.as_str().to_string(),
                        match_length: m.len(),
                        preview_before: line[start..m.start()].to_string(),
                        preview_after: line[m.end()..end].to_string(),
                    });
                }
            }
        }
    }

    Ok(results)
}

/// Get detailed file information
#[tauri::command]
pub async fn get_file_info(path: String) -> Result<FileInfo, String> {
    let p = Path::new(&path);
    let metadata = p.metadata()
        .map_err(|e| format!("Cannot read metadata: {}", e))?;
    
    let name = p.file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_default();

    let is_dir = metadata.is_dir();
    let is_file = metadata.is_file();
    let ext = if is_file {
        p.extension().map(|e| e.to_string_lossy().to_string()).filter(|e| !e.is_empty())
    } else { None };

    let modified_time = metadata.modified()
        .ok()
        .and_then(|t| DateTime::<Utc>::from(t).to_rfc3339().into())
        .unwrap_or_default();

    let created_time = metadata.created()
        .ok()
        .map(|t| DateTime::<Utc>::from(t).to_rfc3339());

    Ok(FileInfo {
        name,
        path: p.to_string_lossy().to_string(),
        is_directory: is_dir,
        is_file,
        size: metadata.len(),
        modified_time,
        created_time,
        extension: ext,
        readonly: metadata.permissions().readonly(),
    })
}

/// Get recently accessed files
#[tauri::command]
pub async fn get_recent_files(limit: Option<u32>) -> Result<Vec<FileInfo>, String> {
    // This would typically be implemented with OS-specific APIs
    // For now, return empty list - the frontend tracks recent files
    Ok(Vec::new())
}
