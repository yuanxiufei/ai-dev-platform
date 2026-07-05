<script setup lang="ts">
/**
 * LocalHistoryPanel.vue — 本地历史记录面板
 *
 * 借鉴: VSCode workbench/contrib/localHistory/
 *
 * 能力:
 *   - 列出所有有历史记录的文件
 *   - 点击文件查看历史版本时间线
 *   - 选择版本对比或恢复
 *   - 删除不需要的版本
 *   - 自动保存快照触发器
 */
import { Clock, FileText, ArrowLeftRight, ArrowUpCircle, Trash2, History, Save, X, RefreshCw } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useLocalHistoryStore, type LocalHistoryEntry } from '@/stores/useLocalHistoryStore'
import { useIDEStore } from '@/stores/useIDEStore'

const lhStore = useLocalHistoryStore()
const ideStore = useIDEStore()
const viewMode = ref<'files' | 'entries'>('files')

function formatTime(ts: number): string {
  const d = new Date(ts)
  return d.toLocaleString('zh-CN', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })
}

function formatRelative(ts: number): string {
  const diff = Date.now() - ts
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff/60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff/3600000)}小时前`
  return `${Math.floor(diff/86400000)}天前`
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024*1024) return `${(bytes/1024).toFixed(1)} KB`
  return `${(bytes/(1024*1024)).toFixed(1)} MB`
}

function viewFileHistory(filePath: string): void {
  lhStore.selectFile(filePath)
  viewMode.value = 'entries'
}

function goBack(): void {
  lhStore.selectFile(null)
  viewMode.value = 'files'
}

function restoreEntry(entry: LocalHistoryEntry): void {
  const content = lhStore.restore(entry)
  lhStore.snapshot(entry.filePath, content, '恢复前快照')
  ideStore.openFile(entry.filePath)
}

function compareEntry(entry: LocalHistoryEntry): void {
  lhStore.selectEntry(entry)
  // Open file for comparison
  const tab = ideStore.tabs.find(t => t.filePath === entry.filePath)
  if (tab) {
    tab.originalContent = entry.content
  }
  ideStore.openFile(entry.filePath)
}

function takeSnapshot(): void {
  const tab = ideStore.activeTab
  if (tab && tab.content) {
    lhStore.snapshot(tab.filePath || tab.label, tab.content, '手动快照')
  }
}

const currentSnapshots = computed(() => {
  if (!lhStore.selectedFile) return []
  return lhStore.entriesForFile.value
})
</script>

<template>
  <div class="local-history flex flex-col h-full text-[13px]" style="color:var(--color-ide-text); background:var(--color-ide-surface)">
    <!-- Header -->
    <div class="shrink-0 flex items-center px-3 h-9 gap-2" style="border-bottom:1px solid var(--color-ide-border)">
      <History :size="14" style="color:var(--color-ide-accent)" />
      <span class="text-[12px] font-semibold uppercase tracking-wider">本地历史记录</span>
      <div class="flex-1" />
      <button class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]" title="创建快照" @click="takeSnapshot">
        <Save :size="12" />
      </button>
      <button v-if="viewMode==='entries'" class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]" title="返回" @click="goBack">
        <X :size="12" />
      </button>
    </div>

    <!-- File list view -->
    <div v-if="viewMode==='files'" class="flex-1 overflow-y-auto py-1">
      <div v-if="lhStore.fileList.length === 0" class="flex flex-col items-center justify-center py-16" style="color:var(--color-ide-text-dim)">
        <Clock :size="24" class="mb-2 opacity-20" />
        <p class="text-[12px]">没有本地历史记录</p>
        <p class="text-[10px] opacity-50 mt-1">文件保存时将自动记录</p>
      </div>
      <div v-for="file in lhStore.fileList" :key="file.filePath"
        class="lh-item px-3 py-2 cursor-pointer transition-colors"
        @click="viewFileHistory(file.filePath)">
        <div class="flex items-center gap-1.5">
          <FileText :size="11" class="shrink-0" style="color:var(--color-ide-accent)" />
          <span class="flex-1 truncate font-medium text-[12px]">{{ file.fileName }}</span>
        </div>
        <div class="flex items-center gap-2 mt-0.5 ml-4 text-[10px]" style="color:var(--color-ide-text-dim)">
          <Clock :size="9" />
          <span>{{ formatRelative(file.lastModified) }}</span>
          <span class="opacity-50">{{ file.count }} 个版本</span>
        </div>
      </div>
    </div>

    <!-- Entry list view -->
    <div v-else class="flex-1 overflow-y-auto py-1">
      <div class="px-3 py-1.5 text-[11px] flex items-center gap-1.5" style="border-bottom:1px solid var(--color-ide-border); color:var(--color-ide-text-dim)">
        <FileText :size="10" />
        <span class="truncate">{{ lhStore.selectedFile?.split(/[\\/]/).pop() || '' }}</span>
        <span class="opacity-50">({{ currentSnapshots.length }} 个版本)</span>
        <button class="ml-auto text-[10px] hover:text-red-400 transition-colors" @click="lhStore.selectedFile && lhStore.clearFileHistory(lhStore.selectedFile)">清除全部</button>
      </div>
      <div v-for="entry in currentSnapshots" :key="entry.id"
        class="lh-entry px-3 py-2 cursor-pointer transition-colors group"
        @click="compareEntry(entry)">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-1.5 min-w-0">
            <Save v-if="entry.label==='自动保存'" :size="10" style="color:var(--color-ide-text-dim)" />
            <Clock v-else :size="10" style="color:var(--color-ide-accent)" />
            <span class="text-[12px] truncate" style="color:var(--color-ide-text)">{{ entry.label }}</span>
          </div>
          <span class="text-[10px] shrink-0 ml-2" style="color:var(--color-ide-text-dim)">{{ formatRelative(entry.timestamp) }}</span>
        </div>
        <div class="flex items-center gap-2 mt-0.5 ml-4 text-[10px]" style="color:var(--color-ide-text-dim)">
          <span>{{ formatTime(entry.timestamp) }}</span>
          <span>{{ formatSize(entry.size) }}</span>
        </div>
        <div class="hidden group-hover:flex items-center gap-0.5 mt-0.5 ml-4">
          <button class="lh-action-btn" title="比较" @click.stop="compareEntry(entry)">
            <ArrowLeftRight :size="10" /> 比较
          </button>
          <button class="lh-action-btn" title="恢复" @click.stop="restoreEntry(entry)">
            <ArrowUpCircle :size="10" /> 恢复
          </button>
          <button class="lh-action-btn text-red-400" title="删除" @click.stop="lhStore.removeEntry(entry.id)">
            <Trash2 :size="10" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lh-item { border-bottom: 1px solid color-mix(in srgb, var(--color-ide-border) 30%, transparent); }
.lh-item:hover { background: var(--color-ide-surface-hover); }
.lh-entry { border-bottom: 1px solid color-mix(in srgb, var(--color-ide-border) 20%, transparent); }
.lh-entry:hover { background: var(--color-ide-surface-hover); }
.lh-action-btn {
  display: flex; align-items: center; gap: 2px;
  font-size: 9px; padding: 1px 5px; border-radius: 2px;
  color: var(--color-ide-text-dim);
  transition: all 0.1s;
}
.lh-action-btn:hover { background: var(--color-ide-surface-active); color: var(--color-ide-text); }
</style>
