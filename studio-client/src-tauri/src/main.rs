// CodeBuddy IDE - Main Entry Point
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod file_watcher;
mod terminal;
mod git;
mod plugins;
mod shortcuts;
mod settings;

fn main() {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_http::init())
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_os::init())
        .setup(|app| {
            let handle = app.handle().clone();
            
            // Initialize file watcher
            file_watcher::init(&handle)?;
            
            // Initialize plugin system
            plugins::init(&handle)?;

            // Initialize shortcut registry
            shortcuts::init(&handle)?;

            log::info!("CodeBuddy IDE initialized successfully");
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            // File System Commands
            commands::fs::read_directory,
            commands::fs::read_file,
            commands::fs::write_file,
            commands::fs::create_file,
            commands::fs::create_directory,
            commands::fs::delete_path,
            commands::fs::rename_path,
            commands::fs::copy_path,
            commands::fs::move_path,
            commands::fs::search_files,
            commands::fs::search_in_file,
            commands::fs::get_file_info,
            commands::fs::get_recent_files,
            
            // Terminal Commands
            commands::terminal::spawn_shell,
            commands::terminal::write_to_pty,
            commands::terminal::resize_pty,
            commands::terminal::kill_process,
            commands::terminal::list_processes,
            
            // Git Commands
            commands::git::git_status,
            commands::git::git_diff,
            commands::git::git_log,
            commands::git::git_commit,
            commands::git::git_branch,
            commands::git::git_checkout,
            commands::git::git_stash,
            commands::git::git_pull,
            commands::git::git_push,
            
            // Window Commands
            commands::window::toggle_fullscreen,
            commands::window::zoom_in,
            commands::window::zoom_out,
            commands::window::reset_zoom,
            commands::window::open_devtools,
            commands::window::focus_window,
            
            // Plugin Commands
            commands::plugins::list_plugins,
            commands::plugins::enable_plugin,
            commands::plugins::disable_plugin,
            commands::plugins::install_plugin,
            commands::plugins::uninstall_plugin,
            commands::plugins::call_plugin_command,
            
            // Settings Commands
            commands::settings::get_settings,
            commands::settings::save_settings,
            commands::settings::reset_settings,
            commands::settings::export_settings,
            commands::settings::import_settings,
            
            // Search & Replace
            commands::search::global_search,
            commands::search::global_replace,
            commands::search::find_in_files,
            commands::search::replace_in_files,
            
            // System Info
            commands::system::get_system_info,
            commands::system::get_memory_usage,
            commands::system::get_cpu_info,
            commands::system::get_workspace_dir,
        ]);

    builder
        .run(tauri::generate_context!())
        .expect("error while running CodeBuddy IDE");
}
