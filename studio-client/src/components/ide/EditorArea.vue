<script setup lang="ts">
/** CodeBuddy IDE — Editor Area (Center) with Monaco + RouterView tabs */
import { shallowRef, watch, nextTick, ref, computed } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import TabBar from './TabBar.vue'
import CodeEditor from './CodeEditor.vue'
import { RouterView } from 'vue-router'

const store = useIDEStore()
const editorKey = ref(0)
watch(() => store.activeTabId, async () => { await nextTick(); editorKey.value++ })

/** Whether we are showing a Studio page (router view) vs code editor */
const isStudioPage = computed(() => !!currentRouteName())
function currentRouteName(): string | null {
  // We'll check the actual route via the router instance if needed
  return null // Simplified — the App.vue will handle routing visibility
}
</script>

<template>
  <div class="flex-1 flex flex-col overflow-hidden bg-[var(--color-editor-bg)] min-w-0">
    <!-- Tab Bar -->
    <TabBar />

    <!-- Content Area -->
    <div class="flex-1 relative overflow-hidden">
      <!-- Empty state when no tabs and no route -->
      <div v-if="!store.activeTab" class="absolute inset-0 flex flex-col items-center justify-center text-[var(--color-ide-text-dim)] select-none">
        <div class="mb-6">
          <svg width="96" height="96" viewBox="0 0 128 128" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect x="28" y="32" width="72" height="56" rx="16" fill="#35354a" stroke="#55557a" stroke-width="2"/>
            <rect x="38" y="42" width="52" height="30" rx="6" fill="#1e1e2e"/>
            <circle cx="52" cy="56" r="5" fill="#89b4fa"/><circle cx="76" cy="56" r="5" fill="#89b4fa"/>
            <line x1="64" y1="32" x2="64" y2="18" stroke="#55557a" stroke-width="2.5" stroke-linecap="round"/><circle cx="64" cy="14" r="4" fill="#a6e3a1"/>
            <rect x="40" y="88" width="48" height="24" rx="8" fill="#35354a" stroke="#55557a" stroke-width="2"/>
            <rect x="46" y="94" width="36" height="16" rx="3" fill="#1e1e2e" stroke="#45475a" stroke-width="1"/>
            <line x1="54" y1="101" x2="74" y2="101" stroke="#89b4fa" stroke-width="1" stroke-linecap="round"/>
            <rect x="20" y="84" width="20" height="8" rx="4" fill="#35354a" stroke="#55557a" stroke-width="1.5"/>
            <rect x="88" y="84" width="20" height="8" rx="4" fill="#35354a" stroke="#55557a" stroke-width="1.5"/>
          </svg>
        </div>
        <h2 class="text-lg font-medium text-[var(--color-ide-text)] mb-2">Hi Buddy</h2>
        <p class="text-sm mb-6">Waiting for work...</p>
        <div class="grid grid-cols-2 gap-2 text-xs max-w-sm">
          <div class="flex items-center gap-2 px-3 py-2 rounded bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)]"><span>显示所有命令</span><kbd class="ml-auto px-1.5 py-0.5 bg-[var(--color-ide-bg)] rounded text-[10px] border border-[var(--color-ide-border)]">Ctrl+Shift+P</kbd></div>
          <div class="flex items-center gap-2 px-3 py-2 rounded bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)]"><span>快速打开文件</span><kbd class="ml-auto px-1.5 py-0.5 bg-[var(--color-ide-bg)] rounded text-[10px] border border-[var(--color-ide-border)]">Ctrl+P</kbd></div>
          <div class="flex items-center gap-2 px-3 py-2 rounded bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)]"><span>打开设置</span><kbd class="ml-auto px-1.5 py-0.5 bg-[var(--color-ide-bg)] rounded text-[10px] border border-[var(--color-ide-border)]">Ctrl+,</kbd></div>
          <div class="flex items-center gap-2 px-3 py-2 rounded bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)]"><span>在文件中查找</span><kbd class="ml-auto px-1.5 py-0.5 bg-[var(--color-ide-bg)] rounded text-[10px] border border-[var(--color-ide-border)]">Ctrl+Shift+F</kbd></div>
          <div class="flex items-center gap-2 px-3 py-2 rounded bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] col-span-2"><span>开始调试</span><kbd class="ml-auto px-1.5 py-0.5 bg-[var(--color-ide-bg)] rounded text-[10px] border border-[var(--color-ide-border)]">F5</kbd></div>
        </div>
      </div>

      <!-- Active code editor (when a file tab is active) -->
      <CodeEditor v-else-if="store.activeTab" :key="editorKey" :active-tab="store.activeTab!"
        @update-content="store.updateActiveTabContent($event)" @update-cursor="store.updateCursorPosition($event)" />
    </div>
  </div>
</template>
