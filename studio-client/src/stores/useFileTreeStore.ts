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
  return [
    {
      name: 'my-ai-app',
      path: '',
      isDir: true,
      expanded: true,
      children: [
        {
          name: 'src',
          path: 'src',
          isDir: true,
          expanded: true,
          children: [
            {
              name: 'App.vue',
              path: 'src/App.vue',
              isDir: false,
              language: 'html',
            },
            {
              name: 'main.ts',
              path: 'src/main.ts',
              isDir: false,
              language: 'typescript',
            },
            {
              name: 'style.css',
              path: 'src/style.css',
              isDir: false,
              language: 'css',
            },
            {
              name: 'components',
              path: 'src/components',
              isDir: true,
              expanded: false,
              children: [],
            },
          ],
        },
        {
          name: 'package.json',
          path: 'package.json',
          isDir: false,
          language: 'json',
        },
        {
          name: 'README.md',
          path: 'README.md',
          isDir: false,
          language: 'markdown',
        },
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
    if (!isTauriEnv()) {
      fileTree.value = buildDemoFileTree()
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
    const filePath = `${parentDir.replace(/[\\/]$/, '')}/${fileName}`
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const info = await invoke<any>('create_file', { path: filePath })
      return fileInfoToEntry(info)
    } catch (e) {
      console.warn(`[IDE] Failed to create file: ${filePath}`, e)
      return null
    }
  }

  async function createFolderEntry(
    parentDir: string,
    folderName: string,
  ): Promise<FileEntry | null> {
    const dirPath = `${parentDir.replace(/[\\/]$/, '')}/${folderName}`
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const info = await invoke<any>('create_directory', { path: dirPath })
      return fileInfoToEntry(info)
    } catch (e) {
      console.warn(`[IDE] Failed to create directory: ${dirPath}`, e)
      return null
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
  }
})
