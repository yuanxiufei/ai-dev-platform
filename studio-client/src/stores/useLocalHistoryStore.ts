/**
 * useLocalHistoryStore.ts — 本地历史记录 Store
 *
 * 借鉴: VSCode workbench/contrib/localHistory/
 *
 * 能力:
 *   - 文件保存时自动创建快照
 *   - localStorage 持久化 (最多 50 条/文件)
 *   - 快照对比恢复
 */
import { ref, computed } from 'vue'

export interface LocalHistoryEntry {
  id: string
  filePath: string
  timestamp: number
  content: string
  label: string
  size: number
}

const STORAGE_KEY = 'ide_local_history_v1'
const MAX_ENTRIES_PER_FILE = 50
const TOTAL_MAX_ENTRIES = 500

export const useLocalHistoryStore = () => {
  const entries = ref<LocalHistoryEntry[]>(loadEntries())
  const selectedFile = ref<string | null>(null)
  const selectedEntry = ref<LocalHistoryEntry | null>(null)
  const showDiff = ref(false)

  function loadEntries(): LocalHistoryEntry[] {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) return JSON.parse(raw)
    } catch { /* ignore */ }
    return []
  }

  function saveEntries(): void {
    try {
      // Trim to max
      if (entries.value.length > TOTAL_MAX_ENTRIES) {
        entries.value = entries.value.slice(-TOTAL_MAX_ENTRIES)
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.value))
    } catch { /* ignore */ }
  }

  /** Create a snapshot of the current file content */
  function snapshot(filePath: string, content: string, label?: string): string {
    const id = `lh-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
    const entry: LocalHistoryEntry = {
      id, filePath, timestamp: Date.now(),
      content, size: content.length,
      label: label || '自动保存',
    }
    entries.value.push(entry)

    // Limit per file
    const fileEntries = entries.value.filter(e => e.filePath === filePath)
    if (fileEntries.length > MAX_ENTRIES_PER_FILE) {
      const oldest = fileEntries[0]
      entries.value = entries.value.filter(e => e.id !== oldest.id)
    }

    saveEntries()
    return id
  }

  /** Get history entries for a file, sorted newest first */
  const entriesForFile = computed(() =>
    entries.value
      .filter(e => selectedFile.value ? e.filePath === selectedFile.value : true)
      .sort((a, b) => b.timestamp - a.timestamp)
  )

  const fileList = computed(() => {
    const seen = new Set<string>()
    return entries.value
      .filter(e => {
        if (seen.has(e.filePath)) return false
        seen.add(e.filePath)
        return true
      })
      .map(e => ({
        filePath: e.filePath,
        fileName: e.filePath.split(/[\\/]/).pop() || e.filePath,
        lastModified: Math.max(...entries.value.filter(x => x.filePath === e.filePath).map(x => x.timestamp)),
        count: entries.value.filter(x => x.filePath === e.filePath).length,
      }))
      .sort((a, b) => b.lastModified - a.lastModified)
  })

  function selectFile(filePath: string | null): void {
    selectedFile.value = filePath
    selectedEntry.value = null
    showDiff.value = false
  }

  function selectEntry(entry: LocalHistoryEntry): void {
    selectedEntry.value = entry
    showDiff.value = true
  }

  function compareWithCurrent(entry: LocalHistoryEntry, currentContent: string): { original: string; modified: string } {
    return { original: entry.content, modified: currentContent }
  }

  /** Restore file content from history entry */
  function restore(entry: LocalHistoryEntry): string {
    return entry.content
  }

  function removeEntry(id: string): void {
    entries.value = entries.value.filter(e => e.id !== id)
    if (selectedEntry.value?.id === id) {
      selectedEntry.value = null
      showDiff.value = false
    }
    saveEntries()
  }

  function clearFileHistory(filePath: string): void {
    entries.value = entries.value.filter(e => e.filePath !== filePath)
    saveEntries()
  }

  return {
    entries, selectedFile, selectedEntry, showDiff,
    entriesForFile, fileList,
    snapshot, selectFile, selectEntry, compareWithCurrent, restore, removeEntry, clearFileHistory,
  }
}
