<script setup lang="ts">
/**
 * CodeBuddy IDE — Editor Area (Center)
 * 
 * Dual-mode rendering:
 *   - Studio pages (AgentChat, ProjectList, etc.) render via RouterView
 *   - File editing uses the Monaco CodeEditor + TabBar
 * 
 * The key insight: RouterView always renders. When a code tab is active,
 * we overlay the CodeEditor on top and visually hide the router content.
 */
import { watch, nextTick, ref, computed } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { useRoute } from 'vue-router'
import TabBar from './TabBar.vue'
import CodeEditor from './CodeEditor.vue'

const store = useIDEStore()
const route = useRoute()
const editorKey = ref(0)

watch(() => store.activeTabId, async () => {
  await nextTick()
  editorKey.value++
})

/** True when user is editing a file (code tab is active) */
const isEditingFile = computed(() => !!store.activeTab)

/** True when a Studio/route page is active (no file tab, and we're on a known route) */
const isStudioView = computed(() => !isEditingFile.value && route.name !== undefined)
</script>

<template>
  <div class="flex-1 flex flex-col overflow-hidden bg-[var(--color-editor-bg)] min-w-0">
    <!-- Tab Bar — only visible when editing files -->
    <TabBar v-if="isEditingFile" />

    <!-- Content Area -->
    <div class="flex-1 relative overflow-hidden">
      <!--
        Mode A: Studio Pages (RouterView) — default mode when no file tab is open.
        Shows AgentChat, ProjectList, ToolsBrowser, etc.
      -->
      <template v-if="!isEditingFile">
        <router-view v-slot="{ Component, route: currentRoute }">
          <transition
            enter-active-class="transition-all duration-200 ease-out"
            enter-from-class="opacity-0 translate-y-2"
            enter-to-class="opacity-100 translate-y-0"
            leave-active-class="transition-all duration-150 ease-in"
            leave-from-class="opacity-100 translate-y-0"
            leave-to-class="opacity-0 -translate-y-2"
            mode="out-in"
          >
            <component :is="Component" :key="currentRoute.path" />
          </transition>
        </router-view>
      </template>

      <!--
        Mode B: Code Editor — when a file tab is active.
        The RouterView is hidden, and we show the Monaco-based editor.
      -->
      <CodeEditor
        v-else
        :key="editorKey"
        :active-tab="store.activeTab!"
        @update-content="store.updateActiveTabContent($event)"
        @update-cursor="store.updateCursorPosition($event)"
      />
    </div>
  </div>
</template>
