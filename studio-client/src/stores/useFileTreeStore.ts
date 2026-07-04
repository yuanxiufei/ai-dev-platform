// ============================================
// File Tree Store — workspace file system
// ============================================
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { FileEntry } from '@/types/ide'
import { extToLang, isTauriEnv } from './shared'

function fileInfoToEntry(info: {
  name: string
  path: string
  isDirectory?: boolean
  isFile?: boolean
  extension?: string
  size?: number
}): FileEntry {
  const isDir = info.isDirectory ?? false
  const ext = info.extension ?? ''
  return {
    name: info.name,
    path: info.path,
    isDir,
    children: isDir ? [] : undefined,
    language: ext ? (extToLang[ext.toLowerCase()] ?? 'plaintext') : undefined,
    expanded: false,
    size: info.size ?? 0,
  }
}

function buildDemoFileTree(): FileEntry[] {
  // ✅ 模拟 Tauri 端真实 src-tauri 结构 — 用于浏览器无 Tauri 时的可视化测试
  return [
    {
      name: 'src-tauri',
      path: 'src-tauri',
      isDir: true,
      expanded: true,
      children: [
        { name: 'gen', path: 'src-tauri/gen', isDir: true, expanded: true,
          children: [
            { name: 'schemas', path: 'src-tauri/gen/schemas', isDir: true, expanded: false, children: [] },
          ] },
        { name: 'icons', path: 'src-tauri/icons', isDir: true, expanded: false, children: [
            { name: '128x128.png', path: 'src-tauri/icons/128x128.png', isDir: false, language: 'plaintext' },
            { name: '128x128@2x.png', path: 'src-tauri/icons/128x128@2x.png', isDir: false, language: 'plaintext' },
            { name: '32x32.png', path: 'src-tauri/icons/32x32.png', isDir: false, language: 'plaintext' },
            { name: 'icon.icns', path: 'src-tauri/icons/icon.icns', isDir: false, language: 'plaintext' },
            { name: 'icon.ico', path: 'src-tauri/icons/icon.ico', isDir: false, language: 'plaintext' },
            { name: 'icon.png', path: 'src-tauri/icons/icon.png', isDir: false, language: 'plaintext' },
          ] },
        { name: 'src', path: 'src-tauri/src', isDir: true, expanded: false, children: [
            { name: 'commands', path: 'src-tauri/src/commands', isDir: true, expanded: false, children: [
              { name: 'fs.rs', path: 'src-tauri/src/commands/fs.rs', isDir: false, language: 'rust' },
              { name: 'git.rs', path: 'src-tauri/src/commands/git.rs', isDir: false, language: 'rust' },
            ] },
            { name: 'file_watcher.rs', path: 'src-tauri/src/file_watcher.rs', isDir: false, language: 'rust' },
            { name: 'git.rs', path: 'src-tauri/src/git.rs', isDir: false, language: 'rust' },
            { name: 'main.rs', path: 'src-tauri/src/main.rs', isDir: false, language: 'rust' },
            { name: 'plugins.rs', path: 'src-tauri/src/plugins.rs', isDir: false, language: 'rust' },
            { name: 'settings.rs', path: 'src-tauri/src/settings.rs', isDir: false, language: 'rust' },
            { name: 'shortcuts.rs', path: 'src-tauri/src/shortcuts.rs', isDir: false, language: 'rust' },
            { name: 'terminal.rs', path: 'src-tauri/src/terminal.rs', isDir: false, language: 'rust' },
          ] },
        { name: 'target', path: 'src-tauri/target', isDir: true, expanded: false, children: [
            { name: '.rustc_info.json', path: 'src-tauri/target/.rustc_info.json', isDir: false, language: 'json' },
            { name: 'CACHEDIR.TAG', path: 'src-tauri/target/CACHEDIR.TAG', isDir: false, language: 'plaintext' },
            { name: 'debug', path: 'src-tauri/target/debug', isDir: true, expanded: false, children: [] },
          ] },
        { name: 'build.rs', path: 'src-tauri/build.rs', isDir: false, language: 'rust' },
        { name: 'Cargo.lock', path: 'src-tauri/Cargo.lock', isDir: false, language: 'toml' },
        { name: 'Cargo.toml', path: 'src-tauri/Cargo.toml', isDir: false, language: 'toml' },
        { name: 'tauri.conf.json', path: 'src-tauri/tauri.conf.json', isDir: false, language: 'json' },
        { name: 'welcome.html', path: 'src-tauri/welcome.html', isDir: false, language: 'html' },
      ],
    },
  ]
}

export const useFileTreeStore = defineStore('fileTree', () => {
  const workspaceRoot = ref('')
  const fileTree = ref<FileEntry[]>([])
  const selectedFilePath = ref<string | null>(null)

  async function loadDirectoryChildren(parentPath: string): Promise<FileEntry[]> {
    if (!isTauriEnv()) return []
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const files = await invoke<any[]>('read_directory', {
        request: { path: parentPath, showHidden: false },
      })
      return files.map(fileInfoToEntry)
    } catch (e) {
      console.warn(`[IDE] Failed to read directory: ${parentPath}`, e)
      return []
    }
  }

  async function initFileTree(rootPath?: string): Promise<void> {
    console.log('[fileTree] initFileTree called, isTauriEnv:', isTauriEnv(), 'rootPath:', rootPath, 'currentLength:', fileTree.value.length)
    if (!isTauriEnv()) {
      fileTree.value = buildDemoFileTree()
      console.log('[fileTree] set demo tree, new length:', fileTree.value.length)
      return
    }
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      let root = rootPath ?? workspaceRoot.value
      if (!root) root = await invoke<string>('get_workspace_dir')
      workspaceRoot.value = root
      const files = await invoke<any[]>('read_directory', {
        request: { path: root, showHidden: false },
      })
      fileTree.value = files.map(fileInfoToEntry)
    } catch (e) {
      console.warn('[IDE] Failed to init file tree, falling back to demo', e)
      fileTree.value = buildDemoFileTree()
    }
  }

  async function toggleExpand(entry: FileEntry): Promise<void> {
    if (!entry.isDir) return
    if (!entry.expanded && entry.children?.length === 0 && entry.path) {
      entry.children = await loadDirectoryChildren(entry.path)
    }
    entry.expanded = !entry.expanded
  }

  async function refreshEntry(entry: FileEntry): Promise<void> {
    if (!entry.isDir || !entry.path) return
    entry.children = await loadDirectoryChildren(entry.path)
  }

  function findEntryByPath(entries: FileEntry[], targetPath: string): FileEntry | null {
    for (const e of entries) {
      if (e.path === targetPath) return e
      if (e.children?.length) {
        const found = findEntryByPath(e.children, targetPath)
        if (found) return found
      }
    }
    return null
  }

  function findParentEntry(entries: FileEntry[], childPath: string): FileEntry | null {
    for (const e of entries) {
      if (e.isDir && e.children) {
        if (e.children.some((c) => c.path === childPath)) return e
        const found = findParentEntry(e.children, childPath)
        if (found) return found
      }
    }
    return null
  }

  async function createFileEntry(parentDir: string, fileName: string): Promise<FileEntry | null> {
    // 处理空 parentDir: 避免生成 /filename 这样带前缀斜杠的路径
    const cleanParent = parentDir.replace(/[\\/]$/, '')
    const filePath = cleanParent ? `${cleanParent}/${fileName}` : fileName
    if (isTauriEnv()) {
      try {
        const { invoke } = await import('@tauri-apps/api/core')
        const info = await invoke<any>('create_file', { path: filePath })
        return fileInfoToEntry(info)
      } catch (e) {
        console.warn(`[IDE] Failed to create file: ${filePath}`, e)
        return null
      }
    }
    // Browser/demo mode: create entry in-memory
    const ext = fileName.split('.').pop()?.toLowerCase() ?? ''
    return {
      name: fileName,
      path: filePath,
      isDir: false,
      language: ext ? (extToLang[ext] ?? 'plaintext') : 'plaintext',
      size: 0,
    }
  }

  async function createFolderEntry(
    parentDir: string,
    folderName: string,
  ): Promise<FileEntry | null> {
    const cleanParent = parentDir.replace(/[\\/]$/, '')
    const dirPath = cleanParent ? `${cleanParent}/${folderName}` : folderName
    if (isTauriEnv()) {
      try {
        const { invoke } = await import('@tauri-apps/api/core')
        const info = await invoke<any>('create_directory', { path: dirPath })
        return fileInfoToEntry(info)
      } catch (e) {
        console.warn(`[IDE] Failed to create directory: ${dirPath}`, e)
        return null
      }
    }
    // Browser/demo mode: create entry in-memory
    return {
      name: folderName,
      path: dirPath,
      isDir: true,
      children: [],
      expanded: false,
      size: 0,
    }
  }

  async function deleteFileEntry(filePath: string): Promise<boolean> {
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      await invoke('delete_path', { path: filePath, recursive: true })
      return true
    } catch (e) {
      console.warn(`[IDE] Failed to delete: ${filePath}`, e)
      return false
    }
  }

  async function renameFileEntry(oldPath: string, newName: string): Promise<FileEntry | null> {
    const parent = oldPath.replace(/[\\/][^\\/]+$/, '')
    const newPath = `${parent}/${newName}`
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const info = await invoke<any>('rename_path', {
        oldPath,
        new_path: newPath,
      })
      return fileInfoToEntry(info)
    } catch (e) {
      console.warn(`[IDE] Failed to rename: ${oldPath} -> ${newPath}`, e)
      return null
    }
  }

  /** VSCode: Expand tree to reveal a file path */
  function expandToPath(targetPath: string): void {
    const parts = targetPath.split(/[/\\]/).filter(Boolean)
    let current = fileTree.value
    let accumulated = ''
    for (const part of parts) {
      accumulated = accumulated ? `${accumulated}/${part}` : part
      const entry = current.find(e => e.name === part || e.path === accumulated)
      if (entry?.isDir && entry.children) {
        entry.expanded = true
        current = entry.children
      } else if (!entry?.isDir) {
        break // reached file, stop
      } else {
        break
      }
    }
  }

  return {
    workspaceRoot,
    fileTree,
    selectedFilePath,
    initFileTree,
    toggleExpand,
    findEntryByPath,
    findParentEntry,
    refreshEntry,
    createFileEntry,
    createFolderEntry,
    deleteFileEntry,
    renameFileEntry,
    expandToPath,
  }
})
