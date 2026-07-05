<script setup lang="ts">
/**
 * CallHierarchyPanel.vue — 调用层次结构面板
 *
 * 借鉴: VSCode workbench/contrib/callHierarchy/
 *
 * 能力:
 *   - 显示传入调用 (谁调用了当前函数)
 *   - 显示传出调用 (当前函数调用了谁)
 *   - 树形展开/折叠
 *   - 点击跳转到源文件位置
 */
import { ArrowDown, ArrowUp, GitFork, RefreshCw, ChevronRight, FunctionSquare, FileCode, ArrowRight } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useCallHierarchyStore, type CallHierarchyItem } from '@/stores/useCallHierarchyStore'
import { useIDEStore } from '@/stores/useIDEStore'

const store = useCallHierarchyStore()
const ideStore = useIDEStore()
const activeTab = ref<'incoming' | 'outgoing'>('incoming')
const expandedIds = ref<Set<string>>(new Set())

const items = computed(() => activeTab.value === 'incoming' ? store.incomingCalls : store.outgoingCalls)

function toggleExpand(id: string): void {
  if (expandedIds.value.has(id)) expandedIds.value.delete(id)
  else expandedIds.value.add(id)
}

function goToSymbol(item: CallHierarchyItem): void {
  if (item.file) ideStore.openFile(item.file)
  // 滚动到对应行
  setTimeout(() => {
    const editor = document.querySelector('.monaco-editor')
    if (editor) {
      const lineEl = editor.querySelector(`.view-line:nth-child(${item.line})`)
      lineEl?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }, 300)
}

function refresh(): void {
  const tab = ideStore.activeTab
  if (tab && tab.content) {
    const word = getCurrentWord()
    if (word) {
      store.setCurrentSymbol(word)
      store.parseCallHierarchy(tab.content, word, tab.language || 'plaintext')
    }
  }
}

function getCurrentWord(): string {
  // Try to get word at cursor or active symbol
  if (store.currentSymbol) return store.currentSymbol
  // Try from active file
  const tab = ideStore.activeTab
  if (tab) {
    const name = tab.filePath?.split(/[\\/]/).pop()?.replace(/\.\w+$/, '')
    if (name) return name
  }
  return ''
}

const resolvedItems = ref<CallHierarchyItem[]>([])
refresh()
</script>

<template>
  <div class="call-hierarchy flex flex-col h-full text-[13px]" style="color:var(--color-ide-text); background:var(--color-ide-surface)">
    <!-- Header -->
    <div class="shrink-0 flex items-center px-3 h-9 gap-2" style="border-bottom:1px solid var(--color-ide-border)">
      <GitFork :size="14" style="color:var(--color-ide-accent)" />
      <span class="text-[12px] font-semibold uppercase tracking-wider">调用层次结构</span>
      <div class="flex-1" />
      <button class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]" title="刷新" @click="refresh">
        <RefreshCw :size="12" :class="{ 'animate-spin': store.isLoading }" />
      </button>
    </div>

    <!-- Current Symbol -->
    <div v-if="store.currentSymbol" class="shrink-0 px-3 py-1.5 text-[11px]" style="border-bottom:1px solid var(--color-ide-border); color:var(--color-ide-text-dim)">
      符号: <span class="font-semibold" style="color:var(--color-ide-accent)">{{ store.currentSymbol }}</span>
    </div>

    <!-- Tab toggle -->
    <div class="shrink-0 flex border-b" style="border-color:var(--color-ide-border)">
      <button class="ch-tab flex-1" :class="{ active: activeTab==='incoming' }" @click="activeTab='incoming'">
        <ArrowDown :size="11" /> 传入调用 ({{ store.incomingCalls.length }})
      </button>
      <button class="ch-tab flex-1" :class="{ active: activeTab==='outgoing' }" @click="activeTab='outgoing'">
        <ArrowUp :size="11" /> 传出调用 ({{ store.outgoingCalls.length }})
      </button>
    </div>

    <!-- Call list -->
    <div class="flex-1 overflow-y-auto py-1">
      <div v-if="store.isLoading" class="flex items-center justify-center py-12">
        <div class="flex gap-1.5">
          <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:0ms"/>
          <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:150ms"/>
          <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:300ms"/>
        </div>
      </div>

      <div v-else-if="items.length === 0" class="flex flex-col items-center justify-center py-12" style="color:var(--color-ide-text-dim)">
        <GitFork :size="24" class="mb-2 opacity-20" />
        <p class="text-[12px]">没有{{ activeTab==='incoming'?'传入':'传出' }}调用</p>
        <p class="text-[10px] opacity-50 mt-1">{{ activeTab==='incoming'?'没有其他函数调用此符号':'此符号没有调用其他函数' }}</p>
      </div>

      <div v-else v-for="item in items" :key="item.name + item.line" class="ch-item px-3 py-1.5 cursor-pointer transition-colors"
        :class="{ 'hover:bg-[var(--color-ide-surface-hover)]': true }"
        @click="goToSymbol(item)">
        <div class="flex items-center gap-1.5">
          <button v-if="item.children && item.children.length > 0" class="shrink-0" @click.stop="toggleExpand(item.name+item.line)">
            <ChevronRight :size="10" class="transition-transform" :class="{ 'rotate-90': expandedIds.has(item.name+item.line) }" style="color:var(--color-ide-text-dim)" />
          </button>
          <span v-else class="w-3 shrink-0" />
          <FunctionSquare :size="11" class="shrink-0" style="color:var(--color-ide-accent)" />
          <span class="flex-1 truncate font-medium">{{ item.name }}</span>
          <span class="text-[10px] opacity-50 shrink-0" style="color:var(--color-ide-text-dim)">{{ item.detail }}</span>
        </div>
        <div v-if="item.file" class="flex items-center gap-1 ml-5 mt-0.5 text-[10px]" style="color:var(--color-ide-text-dim)">
          <FileCode :size="9" />
          <span>{{ item.file.split(/[\\/]/).pop() }}:{{ item.line }}</span>
          <ArrowRight :size="9" v-if="activeTab==='outgoing'" />
          <span v-if="activeTab==='incoming'" class="opacity-60">→ {{ store.currentSymbol }}()</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ch-tab {
  display: flex; align-items: center; justify-content: center; gap: 4px;
  font-size: 11px; padding: 4px 8px;
  color: var(--color-ide-text-dim);
  border-bottom: 2px solid transparent;
  transition: all 0.1s;
}
.ch-tab:hover { color: var(--color-ide-text); background: var(--color-ide-surface-hover); }
.ch-tab.active { color: var(--color-ide-accent); border-bottom-color: var(--color-ide-accent); }
.ch-item { border-bottom: 1px solid color-mix(in srgb, var(--color-ide-border) 30%, transparent); }
</style>
