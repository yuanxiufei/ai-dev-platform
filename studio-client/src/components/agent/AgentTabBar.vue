<script setup lang="ts">
/**
 * AgentTabBar.vue — RooCode-inspired conversation tab bar (Session 10)
 *
 * Features:
 *   - Multi-tab switching with active indicator
 *   - Pin/unpin tabs
 *   - Close individual tabs
 *   - New tab button
 *   - Truncated titles with ellipsis
 */

import { computed } from "vue"
import { Plus, Pin, PinOff, X, MessageSquare } from "lucide-vue-next"
import { useAgentTabsStore } from "@/stores/useAgentTabsStore"

const store = useAgentTabsStore()

const emit = defineEmits<{
  (e: "tab-switch", tabId: string): void
  (e: "new-tab"): void
}>()

const displayedTabs = computed(() => {
  // Pinned tabs first, then unpinned, maintaining relative order
  const pinned = store.tabs.filter((t) => t.pinned)
  const unpinned = store.tabs.filter((t) => !t.pinned)
  return [...pinned, ...unpinned]
})

function onTabClick(tabId: string): void {
  store.switchToTab(tabId)
  emit("tab-switch", tabId)
}

function onCloseTab(tabId: string, e: Event): void {
  e.stopPropagation()
  const wasActive = tabId === store.activeTabId
  store.removeTab(tabId)
  // If the closed tab was active, notify parent to switch
  if (wasActive && store.activeTabId) {
    emit("tab-switch", store.activeTabId)
  }
}

function onPinTab(tabId: string, e: Event): void {
  e.stopPropagation()
  store.togglePin(tabId)
}

function onNewTab(): void {
  // Parent is responsible for actual tab creation (via newChat / createTab),
  // to avoid double-creation when both TabBar and parent call createTab.
  emit("new-tab")
}

function truncateTitle(title: string): string {
  return title.length > 18 ? title.slice(0, 17) + "…" : title
}
</script>

<template>
  <div
    class="flex items-center gap-0 h-9 px-1 bg-[var(--color-ide-bg-secondary)] border-b border-[var(--color-ide-border)] overflow-hidden shrink-0 select-none"
  >
    <!-- Tab scroll area -->
    <div class="flex-1 flex items-center gap-0 overflow-x-auto overflow-y-hidden thin-scroll">
      <button
        v-for="tab in displayedTabs"
        :key="tab.id"
        class="group relative flex items-center gap-1.5 h-7 px-2.5 rounded-t-md text-xs transition-all duration-150 shrink-0 max-w-[200px]"
        :class="[
          tab.active
            ? 'bg-[var(--color-editor-bg)] text-[var(--color-ide-text)] border-t border-x border-[var(--color-ide-border)]'
            : 'text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-hover)] hover:text-[var(--color-ide-text)]',
        ]"
        @click="onTabClick(tab.id)"
      >
        <!-- Pin indicator -->
        <Pin
          v-if="tab.pinned"
          class="w-2.5 h-2.5 text-[var(--color-ide-accent)] shrink-0"
          @click="onPinTab(tab.id, $event)"
        />

        <!-- Icon -->
        <MessageSquare class="w-3 h-3 shrink-0 opacity-50" />

        <!-- Title -->
        <span class="truncate" :title="tab.title">{{ truncateTitle(tab.title) }}</span>

        <!-- Close / Pin button -->
        <span class="flex items-center gap-0.5 ml-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
          <!-- Pin toggle (only show when not pinned) -->
          <button
            v-if="!tab.pinned"
            class="p-0.5 rounded hover:bg-white/10 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-accent)] transition-colors"
            @click="onPinTab(tab.id, $event)"
            title="固定"
          >
            <PinOff class="w-2.5 h-2.5" />
          </button>

          <!-- Close -->
          <button
            class="p-0.5 rounded hover:bg-red-500/20 text-[var(--color-ide-text-dim)] hover:text-red-400 transition-colors"
            @click="onCloseTab(tab.id, $event)"
            title="关闭"
            :class="{ 'opacity-100': tab.active }"
          >
            <X class="w-3 h-3" />
          </button>
        </span>
      </button>
    </div>

    <!-- New tab button -->
    <button
      class="flex items-center justify-center w-7 h-7 rounded-md hover:bg-[var(--color-ide-hover)] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-accent)] transition-all duration-150 shrink-0 ml-1"
      title="新建对话 (Ctrl+T)"
      @click="onNewTab"
    >
      <Plus class="w-3.5 h-3.5" />
    </button>
  </div>
</template>

<style scoped>
.thin-scroll::-webkit-scrollbar {
  height: 3px;
}
.thin-scroll::-webkit-scrollbar-thumb {
  background: #46455466;
  border-radius: 3px;
}
</style>
