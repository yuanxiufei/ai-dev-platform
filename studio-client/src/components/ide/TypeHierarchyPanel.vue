<script setup lang="ts">
/**
 * TypeHierarchyPanel.vue — 类型层次结构面板
 *
 * 借鉴: VSCode workbench/contrib/typeHierarchy/
 */
import { Layers, ArrowUp, ArrowDown, RefreshCw, ChevronRight, Box, FileCode } from 'lucide-vue-next'
import { computed, ref } from 'vue'
import { useTypeHierarchyStore, type TypeHierarchyItem } from '@/stores/useTypeHierarchyStore'
import { useIDEStore } from '@/stores/useIDEStore'

const store = useTypeHierarchyStore()
const ideStore = useIDEStore()
const activeTab = ref<'supertypes' | 'subtypes'>('supertypes')

const items = computed(() => activeTab.value === 'supertypes' ? store.superTypes : store.subTypes)

function refresh(): void {
  const tab = ideStore.activeTab
  if (tab && tab.content) {
    const name = store.currentType || tab.filePath?.split(/[\\/]/).pop()?.replace(/\.\w+$/, '')
    if (name) {
      store.setCurrentType(name)
      store.parseTypeHierarchy(tab.content, name, tab.language || 'plaintext')
    }
  }
}

function goToItem(item: TypeHierarchyItem): void {
  if (item.file) ideStore.openFile(item.file)
}
</script>

<template>
  <div class="type-hierarchy flex flex-col h-full text-[13px]" style="color:var(--color-ide-text); background:var(--color-ide-surface)">
    <div class="shrink-0 flex items-center px-3 h-9 gap-2" style="border-bottom:1px solid var(--color-ide-border)">
      <Layers :size="14" style="color:var(--color-ide-accent)" />
      <span class="text-[12px] font-semibold uppercase tracking-wider">类型层次结构</span>
      <div class="flex-1" />
      <button class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]" title="刷新" @click="refresh">
        <RefreshCw :size="12" />
      </button>
    </div>

    <div v-if="store.currentType" class="shrink-0 px-3 py-1.5 text-[11px]" style="border-bottom:1px solid var(--color-ide-border); color:var(--color-ide-text-dim)">
      类型: <span class="font-semibold" style="color:var(--color-ide-accent)">{{ store.currentType }}</span>
    </div>

    <div class="shrink-0 flex border-b" style="border-color:var(--color-ide-border)">
      <button class="th-tab flex-1" :class="{ active: activeTab==='supertypes' }" @click="activeTab='supertypes'">
        <ArrowUp :size="11" /> 父类型 ({{ store.superTypes.length }})
      </button>
      <button class="th-tab flex-1" :class="{ active: activeTab==='subtypes' }" @click="activeTab='subtypes'">
        <ArrowDown :size="11" /> 子类型 ({{ store.subTypes.length }})
      </button>
    </div>

    <div class="flex-1 overflow-y-auto py-1">
      <div v-if="items.length===0" class="flex flex-col items-center justify-center py-12" style="color:var(--color-ide-text-dim)">
        <Layers :size="24" class="mb-2 opacity-20" />
        <p class="text-[12px]">无层次信息</p>
      </div>
      <div v-for="item in items" :key="item.name" class="th-item px-3 py-1.5 cursor-pointer transition-colors" @click="goToItem(item)">
        <div class="flex items-center gap-1.5">
          <Box :size="11" class="shrink-0" style="color:var(--color-ide-accent)" />
          <span class="flex-1 truncate font-medium">{{ item.name }}</span>
          <span class="text-[10px] opacity-50 shrink-0" style="color:var(--color-ide-text-dim)">{{ item.kind }}</span>
        </div>
        <div v-if="item.detail" class="flex items-center gap-1 ml-4 mt-0.5 text-[10px]" style="color:var(--color-ide-text-dim)">
          <span>{{ item.detail }}</span>
        </div>
        <div v-if="item.file" class="text-[10px] ml-4 opacity-40" style="color:var(--color-ide-text-dim)">
          <FileCode :size="9" class="inline" /> {{ item.file.split(/[\\/]/).pop() }}:{{ item.line }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.th-tab {
  display: flex; align-items: center; justify-content: center; gap: 4px;
  font-size: 11px; padding: 4px 8px;
  color: var(--color-ide-text-dim);
  border-bottom: 2px solid transparent;
  transition: all 0.1s;
}
.th-tab:hover { color: var(--color-ide-text); background: var(--color-ide-surface-hover); }
.th-tab.active { color: var(--color-ide-accent); border-bottom-color: var(--color-ide-accent); }
.th-item { border-bottom: 1px solid color-mix(in srgb, var(--color-ide-border) 30%, transparent); }
.th-item:hover { background: var(--color-ide-surface-hover); }
</style>
