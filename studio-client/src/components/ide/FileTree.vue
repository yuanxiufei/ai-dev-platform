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
  if (e.isDir) return '#FBBF24'
  // Figma design colors for my-ai-app project
  if (e.name === 'App.vue') return '#38BDF8'       // sky blue
  if (e.name === 'main.ts') return '#60A5FA'        // blue
  if (e.name === 'style.css') return '#C7C4D7'      // dim gray
  if (e.name === 'package.json') return '#FB923C'   // orange
  if (e.name === 'README.md') return '#3B82F6'      // blue
  const c: Record<string,string> = {
    ts:'#60A5FA',tsx:'#60A5FA',js:'#f7df1e',jsx:'#61dafb',
    py:'#3776ab',rs:'#dea584',go:'#00add8',java:'#b07219',
    json:'#FB923C',md:'#3B82F6',html:'#E06C75',css:'#264de4',
    vue:'#38BDF8',sh:'#89e05f',yaml:'#cb171e',toml:'#9c4221',
    dockerfile:'#2496ed',
  }
  return c[e.name.split('.').pop()?.toLowerCase() ?? ''] ?? '#90a4ae'
}
function handleClick(e: FileEntry): void { if (e.isDir) store.toggleExpand(e); else if (e.path) store.openFile(e.path) }
</script>

<template>
  <div class="file-tree text-xs select-none py-1">
    <div v-for="entry in entries" :key="entry.path || entry.name"
      class="tree-item group relative flex items-center h-7 pr-2 cursor-pointer transition-colors"
      :style="{ paddingLeft: `${(depth ?? 0) * 12 + 8}px` }"
      :class="[store.selectedFilePath === entry.path ? 'bg-[rgba(192,193,255,0.1)]' : 'hover:bg-[var(--color-ide-surface-hover)]']"
      @click.stop="handleClick(entry)">
      <!-- Active left border (Figma: blue indicator for App.vue) -->
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
  </div>
</template>
