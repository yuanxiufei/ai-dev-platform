<script setup lang="ts">/** CodeBuddy IDE — File Tree Component (VSCode Explorer) */
import { ref, computed, nextTick } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import type { FileEntry } from '@/types/ide'
import {
  ChevronDown, ChevronRight, FolderOpen, FolderClosed, FileCode, FileJson,
  FileText, Image as ImgIcon, Archive, File, FileSymlink, FilePlus, FolderPlus,
  Pencil, Trash2, Copy, AtSign,
} from 'lucide-vue-next'

const store = useIDEStore()
const props = defineProps<{ entries?: FileEntry[]; depth?: number }>()
const entries = computed(() => props.entries ?? store.fileTree)

const emit = defineEmits<{
  (e: "mentionFile", path: string, name: string): void
}>()

/** Right-click context menu */
const contextMenu = ref<{ x: number; y: number; entry: FileEntry } | null>(null)

/** 🔥 VSCode: Inline rename (F2) — type new name and press Enter */
const renamingPath = ref<string | null>(null)
const renameValue = ref('')
const renameInputRef = ref<HTMLInputElement | null>(null)

function getIcon(e: FileEntry) {
  if (e.isDir) return e.expanded ? FolderOpen : FolderClosed
  const ext = e.name.split('.').pop()?.toLowerCase() ?? ''
  if (['ts','tsx','js','jsx','py','rs','go','java','c','cpp'].includes(ext)) return FileCode
  if (['json','toml'].includes(ext)) return FileJson
  if (ext === 'md') return FileText
  if (['png','jpg','jpeg','gif','svg','ico','webp'].includes(ext)) return ImgIcon
  if (['zip','tar','gz','rar','7z'].includes(ext)) return Archive
  if (e.name.startsWith('.') || ['lock','gitignore','env','dockerfile','mod'].includes(e.name.toLowerCase())) return FileSymlink
  return File
}
function getColor(e: FileEntry): string {
  if (e.isDir) return '#FBBF24'
  if (e.name === 'App.vue') return '#38BDF8'
  if (e.name === 'main.ts') return '#60A5FA'
  if (e.name === 'style.css') return '#C7C4D7'
  if (e.name === 'package.json') return '#FB923C'
  if (e.name === 'README.md') return '#3B82F6'
  const c: Record<string,string> = {
    ts:'#60A5FA',tsx:'#60A5FA',js:'#f7df1e',jsx:'#61dafb',
    py:'#3776ab',rs:'#dea584',go:'#00add8',java:'#b07219',
    json:'#FB923C',md:'#3B82F6',html:'#E06C75',css:'#264de4',
    vue:'#38BDF8',sh:'#89e05f',yaml:'#cb171e',toml:'#9c4221',
    dockerfile:'#2496ed',
  }
  return c[e.name.split('.').pop()?.toLowerCase() ?? ''] ?? '#90a4ae'
}
function handleClick(e: FileEntry): void {
  if (e.isDir) store.toggleExpand(e)
  else if (e.path) store.openFile(e.path)
}

/** 🔥 VSCode: F2 — start inline rename */
function handleKeydown(ev: KeyboardEvent, entry: FileEntry): void {
  if (ev.key === 'F2' && !entry.isDir) {
    ev.preventDefault(); ev.stopPropagation()
    startRename(entry)
  }
}

function startRename(entry: FileEntry): void {
  renamingPath.value = entry.path
  renameValue.value = entry.name
  nextTick(() => {
    renameInputRef.value?.focus()
    renameInputRef.value?.select()
  })
}

async function commitRename(entry: FileEntry): Promise<void> {
  const newName = renameValue.value.trim()
  if (!newName || newName === entry.name || !entry.path) {
    renamingPath.value = null
    return
  }
  const renamed = await store.renameFileEntry(entry.path, newName)
  if (renamed) {
    const parent = findParent(store.fileTree, entry.path)
    if (parent?.children) await store.refreshEntry(parent)
  }
  renamingPath.value = null
}

function cancelRename(): void {
  renamingPath.value = null
}

/** 🔥 VSCode: Drag & Drop files between folders */
function onFileDragStart(e: DragEvent, entry: FileEntry): void {
  e.dataTransfer!.setData("text/plain", entry.path)
  e.dataTransfer!.effectAllowed = "move"
}
function onFileDragOver(e: DragEvent): void {
  e.preventDefault(); e.dataTransfer!.dropEffect = "move"
}
function onFileDrop(_e: DragEvent, targetDir: FileEntry): void {
  // Placeholder — full file move would require Tauri backend support
  // For now, just visual feedback
}

function handleContextMenu(ev: MouseEvent, entry: FileEntry): void {
  ev.preventDefault()
  contextMenu.value = { x: ev.clientX, y: ev.clientY, entry }
}
function closeContextMenu(): void { contextMenu.value = null }

async function handleCopyPath(): Promise<void> {
  const entry = contextMenu.value?.entry
  if (!entry?.path) return
  try { await navigator.clipboard.writeText(entry.path) } catch { /* ignore */ }
  closeContextMenu()
}

function handleMentionInChat(): void {
  const entry = contextMenu.value?.entry
  if (!entry?.path) return
  emit("mentionFile", entry.path, entry.name)
  closeContextMenu()
}

async function handleNewFile(): Promise<void> {
  const parentDir = contextMenu.value!.entry?.isDir
    ? contextMenu.value!.entry.path
    : contextMenu.value!.entry?.path?.replace(/[/\\][^/\\]+$/, '') ?? store.workspaceRoot
  if (!parentDir) return
  const name = prompt('文件名:')
  if (!name?.trim()) return
  const created = await store.createFileEntry(parentDir, name.trim())
  if (created) {
    const parent = store.findEntryByPath(store.fileTree, parentDir)
    if (parent?.children) {
      parent.children.push(created)
      parent.children.sort((a, b) => {
        if (a.isDir !== b.isDir) return a.isDir ? -1 : 1
        return a.name.toLowerCase().localeCompare(b.name.toLowerCase())
      })
    }
  }
  closeContextMenu()
}

async function handleNewFolder(): Promise<void> {
  const parentDir = contextMenu.value!.entry?.isDir
    ? contextMenu.value!.entry.path
    : contextMenu.value!.entry?.path?.replace(/[/\\][^/\\]+$/, '') ?? store.workspaceRoot
  if (!parentDir) return
  const name = prompt('文件夹名:')
  if (!name?.trim()) return
  const created = await store.createFolderEntry(parentDir, name.trim())
  if (created) {
    const parent = store.findEntryByPath(store.fileTree, parentDir)
    if (parent?.children) {
      parent.children.push(created)
      parent.children.sort((a, b) => {
        if (a.isDir !== b.isDir) return a.isDir ? -1 : 1
        return a.name.toLowerCase().localeCompare(b.name.toLowerCase())
      })
    }
  }
  closeContextMenu()
}

async function handleRename(): Promise<void> {
  const entry = contextMenu.value!.entry
  if (!entry?.path) return
  closeContextMenu()
  startRename(entry)
}

async function handleDelete(): Promise<void> {
  const entry = contextMenu.value!.entry
  if (!entry?.path) return
  const confirm = window.confirm(`删除 "${entry.name}"?`)
  if (!confirm) return
  const ok = await store.deleteFileEntry(entry.path)
  if (ok) {
    const parent = findParent(store.fileTree, entry.path)
    if (parent?.children) await store.refreshEntry(parent)
  }
  closeContextMenu()
}

function findParent(entries: FileEntry[], childPath: string): FileEntry | null {
  for (const e of entries) {
    if (e.isDir && e.children) {
      if (e.children.some(c => c.path === childPath)) return e
      const f = findParent(e.children, childPath)
      if (f) return f
    }
  }
  return null
}
</script>

<template>
  <div class="file-tree text-[13px] select-none py-1">  <!-- was text-xs -->
    <div v-for="entry in entries" :key="entry.path || entry.name"
      class="tree-item group relative flex items-center h-8 pr-2 cursor-pointer transition-colors"  <!-- was h-7 -->
      :style="{ paddingLeft: `${(depth ?? 0) * 12 + 8}px` }"
      :class="[store.selectedFilePath === entry.path ? 'bg-[rgba(192,193,255,0.1)]' : 'hover:bg-[var(--color-ide-surface-hover)]']"
      @click.stop="handleClick(entry)"
      @contextmenu.stop="handleContextMenu($event, entry)"
      @keydown="handleKeydown($event, entry)"
      @dragover="onFileDragOver"
      @drop="onFileDrop($event, entry)">
      <!-- Active left border -->
      <div v-if="store.selectedFilePath === entry.path && renamingPath !== entry.path"
        class="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full shrink-0"
        style="background:#38BDF8;" />
      <span class="w-4 h-4 flex items-center justify-center shrink-0 mr-0.5">
        <component v-if="entry.isDir" :is="entry.expanded ? ChevronDown : ChevronRight" :size="14" style="color:#908FA0;" /><span v-else class="w-3.5" />
      </span>
      <span class="w-4 h-4 flex items-center justify-center mr-1.5 shrink-0"><component :is="getIcon(entry)" :size="15" :style="{ color: getColor(entry) }" /></span>

      <!-- 🔥 VSCode: Inline rename (F2) -->
      <template v-if="renamingPath === entry.path">
        <input
          ref="renameInputRef"
          v-model="renameValue"
          class="flex-1 min-w-0 bg-[#3C3C3C] border border-[var(--color-ide-accent)] rounded px-1 py-0 text-[13px] outline-none text-[var(--color-ide-text)]"
          @blur="commitRename(entry)"
          @keydown.enter="commitRename(entry)"
          @keydown.escape="cancelRename()"
          @click.stop
        />
      </template>
      <!-- Normal label -->
      <span v-else class="truncate flex-1"
        :class="[store.selectedFilePath === entry.path ? 'font-semibold' : '', store.selectedFilePath === entry.path ? 'text-[#C0C1FF]' : 'text-[var(--color-ide-text)]']"
        draggable="true"
        @dragstart="onFileDragStart($event, entry)">
        {{ entry.name }}
      </span>
    </div>
    <template v-for="entry in entries" :key="'ch-' + entry.path">
      <FileTree v-if="entry.isDir && entry.expanded && entry.children?.length" :entries="entry.children" :depth="(depth ?? 0) + 1" />
    </template>

    <!-- 🔥 Context Menu -->
    <Teleport to="body">
      <div v-if="contextMenu" class="fixed z-[300]" :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }" @click.stop>
        <div class="w-48 bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded-[3px] shadow-[0_2px_8px_rgba(0,0,0,0.36)] py-1 text-[13px]">
          <button v-if="!contextMenu.entry?.isDir" class="context-menu-item w-full text-left flex items-center justify-between gap-6"
            @click="contextMenu.entry?.path && store.openFile(contextMenu.entry.path); closeContextMenu()">
            <span>打开</span><kbd>Enter</kbd>
          </button>
          <button v-if="!contextMenu.entry?.isDir" class="context-menu-item w-full text-left flex items-center gap-2"
            @click="handleCopyPath()">
            <Copy :size="13" /> 复制路径
          </button>
          <button v-if="!contextMenu.entry?.isDir" class="context-menu-item w-full text-left flex items-center gap-2"
            @click="handleMentionInChat()">
            <AtSign :size="13" /> @-引用到对话
          </button>
          <hr class="my-1 border-[var(--color-ide-border)]" />
          <button v-if="contextMenu.entry?.isDir" class="context-menu-item w-full text-left flex items-center gap-2" @click="handleNewFile()">
            <FilePlus :size="13" /> 新建文件
          </button>
          <button v-if="contextMenu.entry?.isDir" class="context-menu-item w-full text-left flex items-center gap-2" @click="handleNewFolder()">
            <FolderPlus :size="13" /> 新建文件夹
          </button>
          <button class="context-menu-item w-full text-left flex items-center justify-between gap-6" @click="handleRename()">
            <span><Pencil :size="13" class="inline mr-2"/>重命名</span><kbd>F2</kbd>
          </button>
          <hr class="my-1 border-[var(--color-ide-border)]" />
          <button class="context-menu-item w-full text-left flex items-center justify-between gap-6 text-red-400 hover:text-red-300" @click="handleDelete()">
            <span><Trash2 :size="13" class="inline mr-2"/>删除</span><kbd>Del</kbd>
          </button>
        </div>
      </div>
    </Teleport>
  </div>
</template>
