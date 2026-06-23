<script setup lang="ts">/** CodeBuddy IDE — File Tree Component */
import { computed } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import type { FileEntry } from '@/types/ide'
import { ChevronDown, ChevronRight, FolderOpen, FolderClosed, FileCode, FileJson, FileText, Image as ImgIcon, Archive, File, FileSymlink } from 'lucide-vue-next'

const store = useIDEStore()
const props = defineProps<{ entries?: FileEntry[]; depth?: number }>()
const entries = computed(() => props.entries ?? store.fileTree)

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
  if (e.isDir) return '#dcb67a'
  const c: Record<string,string> = { ts:'#3178c6',tsx:'#3178c6',js:'#f7df1e',jsx:'#61dafb',py:'#3776ab',rs:'#dea584',go:'#00add8',java:'#b07219',json:'#cbcb41',md:'#519aba',html:'#e44d26',css:'#264de4',vue:'#42b883',sh:'#89e05f',yaml:'#cb171e',toml:'#9c4221',dockerfile:'#2496ed' }
  return c[e.name.split('.').pop()?.toLowerCase() ?? ''] ?? '#90a4ae'
}
function handleClick(e: FileEntry): void { if (e.isDir) store.toggleExpand(e); else if (e.path) store.openFile(e.path) }
</script>

<template>
  <div class="file-tree text-xs select-none py-1">
    <div v-for="entry in entries" :key="entry.path || entry.name"
      class="tree-item group flex items-center h-6 pr-2 cursor-pointer transition-colors"
      :style="{ paddingLeft: `${(depth ?? 0) * 12 + 8}px` }"
      :class="[store.selectedFilePath === entry.path ? 'bg-[var(--color-ide-surface-active)]' : 'hover:bg-[var(--color-ide-surface-hover)]']"
      @click.stop="handleClick(entry)">
      <span class="w-4 h-4 flex items-center justify-center shrink-0 mr-0.5">
        <component v-if="entry.isDir" :is="entry.expanded ? ChevronDown : ChevronRight" :size="14" class="text-[var(--color-ide-text-dim)]" /><span v-else class="w-3.5" /></span>
      <span class="w-4 h-4 flex items-center justify-center mr-1.5 shrink-0"><component :is="getIcon(entry)" :size="15" :style="{ color: getColor(entry) }" /></span>
      <span class="truncate flex-1" :class="store.selectedFilePath === entry.path ? 'text-[var(--color-ide-text-bright)]' : 'text-[var(--color-ide-text)]'">{{ entry.name }}</span>
    </div>
    <template v-for="entry in entries" :key="'ch-' + entry.path">
      <FileTree v-if="entry.isDir && entry.expanded && entry.children?.length" :entries="entry.children" :depth="(depth ?? 0) + 1" />
    </template>
  </div>
</template>
