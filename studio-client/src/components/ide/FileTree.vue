<script setup lang="ts">/** CodeBuddy IDE — File Tree Component */
import { ref, computed } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import type { FileEntry } from '@/types/ide'
import { ChevronDown, ChevronRight, FolderOpen, FolderClosed, FileCode, FileJson, FileText, Image as ImgIcon, Archive, File, FileSymlink, FilePlus, FolderPlus, Pencil, Trash2 } from 'lucide-vue-next'

const store = useIDEStore()
const props = defineProps<{ entries?: FileEntry[]; depth?: number }>()
const entries = computed(() => props.entries ?? store.fileTree)

/** Right-click context menu state */
const contextMenu = ref<{ x: number; y: number; entry: FileEntry | null } | null>(null)
const contextParentEntries = ref<FileEntry[] | null>(null)
const renamingEntry = ref<string | null>(null)
const renameValue = ref('')

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
function handleContextMenu(ev: MouseEvent, entry: FileEntry): void {
  ev.preventDefault()
  contextParentEntries.value = entries.value
  contextMenu.value = { x: ev.clientX, y: ev.clientY, entry }
}
function closeContextMenu(): void { contextMenu.value = null }

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
  const newName = prompt('新名称:', entry.name)
  if (!newName?.trim() || newName.trim() === entry.name) return
  const renamed = await store.renameFileEntry(entry.path, newName.trim())
  if (renamed) {
    const parent = findParent(store.fileTree, entry.path)
    if (parent?.children) await store.refreshEntry(parent)
  }
  closeContextMenu()
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

function closeOnClickOutside(): void {
  document.addEventListener('click', () => contextMenu.value = null, { once: true })
}
</script>

<template>
  <div class="file-tree text-xs select-none py-1">
    <div v-for="entry in entries" :key="entry.path || entry.name"
      class="tree-item group relative flex items-center h-7 pr-2 cursor-pointer transition-colors"
      :style="{ paddingLeft: `${(depth ?? 0) * 12 + 8}px` }"
      :class="[store.selectedFilePath === entry.path ? 'bg-[rgba(192,193,255,0.1)]' : 'hover:bg-[var(--color-ide-surface-hover)]']"
      @click.stop="handleClick(entry)"
      @contextmenu.stop="handleContextMenu($event, entry)">
      <!-- Active left border -->
      <div v-if="store.selectedFilePath === entry.path"
        class="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full shrink-0"
        style="background:#38BDF8;" />
      <span class="w-4 h-4 flex items-center justify-center shrink-0 mr-0.5">
        <component v-if="entry.isDir" :is="entry.expanded ? ChevronDown : ChevronRight" :size="14" style="color:#908FA0;" /><span v-else class="w-3.5" />
      </span>
      <span class="w-4 h-4 flex items-center justify-center mr-1.5 shrink-0"><component :is="getIcon(entry)" :size="15" :style="{ color: getColor(entry) }" /></span>
      <span class="truncate flex-1"
        :class="[store.selectedFilePath === entry.path ? 'font-semibold' : '', store.selectedFilePath === entry.path ? 'text-[#C0C1FF]' : 'text-[var(--color-ide-text)]']">
        {{ entry.name }}
      </span>
    </div>
    <template v-for="entry in entries" :key="'ch-' + entry.path">
      <FileTree v-if="entry.isDir && entry.expanded && entry.children?.length" :entries="entry.children" :depth="(depth ?? 0) + 1" />
    </template>

    <!-- Right-Click Context Menu -->
    <Teleport to="body">
      <div v-if="contextMenu" class="fixed z-[300]" :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }" @click.stop>
        <div class="w-40 bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded-md shadow-xl py-1 text-xs">
          <button v-if="contextMenu.entry?.isDir" class="context-menu-item w-full text-left flex items-center gap-2" @click="handleNewFile()">
            <FilePlus :size="13" /> 新建文件
          </button>
          <button v-if="contextMenu.entry?.isDir" class="context-menu-item w-full text-left flex items-center gap-2" @click="handleNewFolder()">
            <FolderPlus :size="13" /> 新建文件夹
          </button>
          <button class="context-menu-item w-full text-left flex items-center gap-2" @click="handleRename()">
            <Pencil :size="13" /> 重命名
          </button>
          <hr class="my-1 border-[var(--color-ide-border)]" />
          <button class="context-menu-item w-full text-left flex items-center gap-2 text-red-400 hover:text-red-300" @click="handleDelete()">
            <Trash2 :size="13" /> 删除
          </button>
        </div>
      </div>
    </Teleport>
  </div>
</template>
