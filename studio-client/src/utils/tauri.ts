/** Tauri IPC Bridge — Frontend <-> Rust Backend */
import { invoke } from '@tauri-apps/api/core'
import { listen, UnlistenFn } from '@tauri-apps/api/event'
import { getCurrentWindow } from '@tauri-apps/api/window'

export interface FileInfo { name: string; path: string; isDirectory: boolean; isFile: boolean; size: number; modifiedTime: string; createdTime?: string; extension?: string; readonly: boolean }
export interface SearchResult { file: string; line: number; column: number; text: string; matchLength: number; previewBefore: string; previewAfter: string }
export interface ProcessInfo { id: number; command: string; cwd: string; status: string }
export interface GitStatus { branch: string; ahead: number; behind: number; staged: any[]; unstaged: any[]; untracked: string[]; clean: boolean }
export interface GitCommitInfo { hash: string; shortHash: string; message: string; author: string; email: string; date: string }
export interface GitBranch { name: string; isCurrent: boolean; isRemote: boolean }
export interface PluginInfo { id: string; name: string; version: string; description: string; author: string; enabled: boolean; entryPoint: string; hasSettingsUI: boolean; commands: any[] }
export interface IDESettings { editor: any; appearance: any; terminal: any; keybindings: any; files: any; ai: any }

const fs = {
  readDirectory: (path: string, options?: any) => invoke<FileInfo[]>('read_directory', { request: { path, ...options } }),
  readFile: (path: string) => invoke<string>('read_file', { path }),
  writeFile: (path: string, content: string) => invoke<void>('write_file', { path, content }),
  createFile: (path: string) => invoke<FileInfo>('create_file', { path }),
  createDirectory: (path: string) => invoke<FileInfo>('create_directory', { path }),
  deletePath: (path: string, recursive?: boolean) => invoke<void>('delete_path', { path, recursive }),
  renamePath: (oldPath: string, newPath: string) => invoke<FileInfo>('rename_path', { oldPath, new_path: newPath }),
  copyPath: (src: string, dst: string) => invoke<FileInfo>('copy_path', { src, dst }),
  searchFiles: (params: any) => invoke<string[]>('search_files', { request: params }),
  searchInFile: (params: any) => invoke<SearchResult[]>('search_in_file', { request: params }),
  getFileInfo: (path: string) => invoke<FileInfo>('get_file_info', { path }),
}

const terminal = {
  spawnShell: (config?: any) => invoke<ProcessInfo>('spawn_shell', { config: config || {} }),
  writeToPty: (pid: number, data: string) => invoke<void>('write_to_pty', { pid, data }),
  resizePty: (pid: number, cols: number, rows: number) => invoke<void>('resize_pty', { pid, cols, rows }),
  killProcess: (pid: number) => invoke<void>('kill_process', { pid }),
  listProcesses: () => invoke<ProcessInfo[]>('list_processes'),
}

const git = {
  getStatus: (path: string) => invoke<GitStatus>('git_status', { path }),
  getLog: (path: string, limit?: number) => invoke<GitCommitInfo[]>('git_log', { path, limit }),
  commit: (path: string, message: string, files?: string[]) => invoke<string>('git_commit', { path, message, files }),
  listBranches: (path: string) => invoke<GitBranch[]>('git_branch', { path }),
  checkout: (path: string, branch: string, createNew?: boolean) => invoke<void>('git_checkout', { path, branch, create_new: createNew }),
  push: (path: string, remote?: string, branch?: string) => invoke<string>('git_push', { path, remote, branch }),
  pull: (path: string, remote?: string, branch?: string) => invoke<string>('git_pull', { path, remote, branch }),
}

const plugins = {
  list: () => invoke<PluginInfo[]>('list_plugins'),
  enable: (id: string) => invoke<void>('enable_plugin', { pluginId: id }),
  disable: (id: string) => invoke<void>('disable_plugin', { pluginId: id }),
  callCommand: (pluginId: string, command: string, args?: any) => invoke<any>('call_plugin_command', { request: { pluginId, command, args } }),
}

const settings = {
  get: () => invoke<IDESettings>('get_settings'),
  save: (s: IDESettings) => invoke<void>('save_settings', { settings: s }),
  reset: () => invoke<IDESettings>('reset_settings'),
}

const events = {
  onFileWatchEvent: (cb: (e: any) => void): Promise<UnlistenFn> => listen('file-watch-event', cb),
}

export const TauriAPI = { fs, terminal, git, window: { toggleFullscreen: () => getCurrentWindow().then(w => invoke<void>('toggle_fullscreen', { window: w })) }, plugins, settings, events, invoke }
export default TauriAPI
