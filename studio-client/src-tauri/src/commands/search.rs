use serde::{Deserialize, Serialize};
use std::path::Path;
use std::fs;
use regex::Regex;
use anyhow::{Result, Context};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GlobalSearchRequest {
    pub path: String,
    pub query: String,
    #[serde(rename = "replaceWith")]
    pub replace_with: Option<String>,
    #[serde(rename = "includePatterns")]
    pub include_patterns: Option<Vec<String>>,
    #[serde(rename = "excludePatterns")]
    pub exclude_patterns: Option<Vec<String>>,
    #[serde(rename = "useRegex")]
    pub use_regex: bool,
    #[serde(rename = "caseSensitive")]
    pub case_sensitive: bool,
    #[serde(rename = "wholeWord")]
    pub whole_word: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GlobalSearchResult {
    pub matches: Vec<FileMatch>,
    #[serde(rename = "totalMatches")]
    pub total_matches: usize,
    #[serde(rename = "filesSearched")]
    pub files_searched: u64,
    #[serde(rename = "elapsedMs")]
    pub elapsed_ms: u128,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FileMatch {
    pub file: String,
    pub line: u32,
    pub column: u32,
    #[serde(rename = "matchText")]
    pub match_text: String,
    #[serde(rename = "matchLength")]
    pub match_length: usize,
    #[serde(rename = "previewBefore")]
    pub preview_before: String,
    #[serde(rename = "previewAfter")]
    pub preview_after: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReplaceResult {
    pub files_modified: Vec<String>,
    #[serde(rename = "totalReplacements")]
    pub total_replacements: usize,
}

/// Perform global search across files
#[tauri::command]
pub async fn global_search(request: GlobalSearchRequest) -> Result<GlobalSearchResult, String> {
    let start_time = std::time::Instant::now();
    
    // Build regex pattern
    let mut pattern_str = request.query.clone();
    
    if request.whole_word {
        pattern_str = format!(r"\b{}\b", pattern_str);
    }

    let re = if request.use_regex {
        Regex::new(&pattern_str)
            .with_context(|| format!("Invalid regex pattern"))
            .map_err(|e| e.to_string())?
    } else {
        let escaped = regex::escape(&pattern_str);
        if !request.case_sensitive {
            Regex::new(&format!("(?i){}", escaped)).map_err(|e| e.to_string())?
        } else {
            Regex::new(&escaped).map_err(|e| e.to_string())?
        }
    };

    let mut all_matches = Vec::new();
    let mut files_searched: u64 = 0;

    // Walk directory tree
    use walkdir::WalkDir;
    let walker = WalkDir::new(&request.path)
        .follow_links(false)
        .into_iter()
        .filter_entry(|e| {
            if let Some(excludes) = &request.exclude_patterns {
                let name = e.file_name().to_string_lossy();
                !excludes.iter().any(|p| is_match_pattern(name.as_ref(), p))
            } else {
                true
            }
        });

    for entry in walker.flatten() {
        if !entry.file_type().is_file() { continue; }
        
        let path_str = entry.path().to_string_lossy().to_string();
        
        // Filter by include patterns
        if let Some(includes) = &request.include_patterns {
            let name = entry.file_name().to_string_lossy();
            if !includes.iter().any(|p| is_match_pattern(name.as_ref(), p)) {
                continue;
            }
        }

        files_searched += 1;

        // Read and search file content
        if let Ok(content) = fs::read_to_string(entry.path()) {
            for (line_idx, line) in content.lines().enumerate() {
                for m in re.find_iter(line) {
                    let preview_start = m.start().saturating_sub(30);
                    let preview_end = (m.end() + 30).min(line.len());
                    
                    all_matches.push(FileMatch {
                        file: path_str.clone(),
                        line: (line_idx + 1) as u32,
                        column: (m.start() + 1) as u32,
                        match_text: m.as_str().to_string(),
                        match_length: m.len(),
                        preview_before: line[preview_start..m.start()].to_string(),
                        preview_after: line[m.end()..preview_end].to_string(),
                    });
                }
            }
        }
    }

    Ok(GlobalSearchResult {
        total_matches: all_matches.len(),
        files_searched: files_searched,
        elapsed_ms: start_time.elapsed().as_millis(),
        matches: all_matches,
    })
}

/// Find in files (simplified version)
#[tauri::command]
pub async fn find_in_files(request: GlobalSearchResult) -> Result<GlobalSearchResult, String> {
    // This delegates to global_search with a different request structure
    Err("Use global_search instead".to_string())
}

/// Replace in files
#[tauri::command]
pub async fn global_replace(request: GlobalSearchRequest) -> Result<ReplaceResult, String> {
    let replacement = request.replace_with.unwrap_or_default();
    let mut modified_files = Vec::new();
    let mut total_replacements = 0;

    let search_result = global_search(request.clone()).await?;
    
    // Group by file
    use std::collections::HashMap;
    let mut file_replacements: HashMap<u32, Vec<(u32, usize, usize)>> = HashMap::new();
    let mut file_paths: HashMap<u32, String> = HashMap::new();
    let mut file_counter = 0;

    for m in search_result.matches {
        if !file_paths.values().any(|p| p == &m.file) {
            file_counter += 1;
            file_paths.insert(file_counter, m.file.clone());
        }
        let fid = file_paths.iter().find(|(_, v)| *v == &m.file).map(|(k, _)| *k).unwrap();
        file_replacements.entry(fid).or_insert_with(Vec::new)
            .push((m.line, m.column as usize, m.match_length));
        total_replacements += 1;
    }

    // Apply replacements (simplified - real implementation would be more careful about overlapping replacements)
    for (_fid, filepath) in &file_paths {
        if let Ok(mut content) = fs::read_to_string(filepath) {
            // Build regex from request
            let re = Regex::new(&regex::escape(&request.query)).unwrap_or_else(|_| Regex::new("").unwrap());
            let new_content = re.replace_all(&content, &replacement).to_string();
            
            if new_content != content {
                fs::write(filepath, &new_content).ok();
                modified_files.push(filepath.clone());
            }
        }
    }

    Ok(ReplaceResult {
        files_modified: modified_files,
        total_replacements,
    })
}

/// Replace in files (alias)
#[tauri::command]
pub async fn replace_in_files(request: GlobalSearchRequest) -> Result<ReplaceResult, String> {
    global_replace(request).await
}

fn is_match_pattern(name: &str, pattern: &str) -> bool {
    let cleaned = pattern.trim_start_matches('*').trim_start_matches('.');
    if pattern.starts_with('*') && pattern.contains('.') {
        name.ends_with(cleaned)
    } else {
        name.contains(cleaned)
    }
}
