<script setup lang="ts">
/**
 * CodeBuddy IDE — Editor Area (Center)
 * Figma Design: studio-ai (node-id=9-195) — Main editing area
 *
 * Layout (when editing files):
 *   ┌──────────────────────────────────────┐
 *   │ TabBar (40px): App.vue | main.ts     │
 *   ├──────────────┬───────────────────────┤
 *   │ Monaco       │ Live Preview Panel    │
 *   │ CodeEditor   │ ("欢迎使用 AI Dev")    │
 *   │ (~420px)     │ (~280px)              │
 *   ├──────────────┴───────────────────────┤
 *   │ Terminal Panel (180px)               │
 *   │ [终端|问题|调试控制台] + npm run dev │
 *   └──────────────────────────────────────┘
 *
 * Layout (when viewing Studio pages):
 *   RouterView fills entire area (AgentChat, ProjectList, etc.)
 */
import { computed, nextTick, ref, watch } from "vue"
import { useRoute } from "vue-router"
import { useIDEStore } from "@/stores/useIDEStore"
import TabBar from "./TabBar.vue"
import CodeEditor from "./CodeEditor.vue"
import Terminal from "./Terminal.vue"

const store = useIDEStore()
const route = useRoute()
const editorKey = ref(0)

watch(
  () => store.activeTabId,
  async () => {
    await nextTick()
    editorKey.value++
  },
)

/** True when user is editing a file (code tab is active) */
const isEditingFile = computed(() => !!store.activeTab)

/** True when a Studio/route page is active */
const isStudioView = computed(
  () => !isEditingFile.value && route.name !== undefined,
)

/** Whether to show bottom terminal panel (Figma: always visible in IDE mode) */
const showBottomPanel = computed(
  () => store.layout.bottomPanelVisible && isEditingFile.value,
)

/** Terminal panel tabs matching Figma design */
const terminalTabs = [
  { id: "terminal", label: "终端" },
  { id: "problems", label: "问题" },
  { id: "debug", label: "调试控制台" },
]
const activeTerminalTab = ref("terminal")
</script>

<template>
  <div class="flex-1 flex flex-col overflow-hidden bg-[var(--color-editor-bg)] min-w-0">
    <!-- Tab Bar — only visible when editing files -->
    <TabBar v-if="isEditingFile" />

    <!-- Content Area -->
    <div class="flex-1 relative overflow-hidden flex flex-col">
      <!--
        Mode A: Studio Pages (RouterView) — default mode.
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
        Mode B: Code Editor + Preview + Terminal (Figma layout)
      -->
      <template v-else>
        <!-- Editor + Preview Row -->
        <div class="flex-1 flex overflow-hidden">
          <!-- Monaco Code Editor (left ~60%) -->
          <CodeEditor
            :key="editorKey"
            :active-tab="store.activeTab!"
            @update-content="store.updateActiveTabContent($event)"
            @update-cursor="store.updateCursorPosition($event)"
            class="flex-1 min-w-0"
          />

          <!-- Live Preview Panel (right ~40%, Figma design) -->
          <aside class="shrink-0 flex flex-col border-l border-[var(--color-ide-border)] overflow-hidden" style="width:280px; background:#0F131D;">
            <!-- Preview Header -->
            <div class="flex items-center justify-between px-2 py-2 shrink-0" style="border-bottom:1px solid var(--color-ide-border); background:#171B26;">
              <span class="text-[11px] font-bold uppercase tracking-wider" style="color:#908FA0;">实时预览</span>
              <div class="flex items-center gap-1">
                <button class="p-1 rounded hover:bg-white/5 transition-colors" style="color:#908FA0;" title="刷新预览">
                  <svg width="13.33" height="10.67" viewBox="0 0 16 12" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M10 1H3a1 1 0 00-1 1v8a1 1 0 001 1h10a1 1 0 001-1V5l-4-4z"/></svg>
                </button>
                <button class="p-1 rounded hover:bg-white/5 transition-colors" style="color:#908FA0;" title="更多操作">
                  <svg width="10.67" height="10.67" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><circle cx="3" cy="6" r="1" fill="currentColor"/><circle cx="8" cy="6" r="1" fill="currentColor"/><circle cx="13" cy="6" r="1" fill="currentColor"/></svg>
                </button>
              </div>
            </div>

            <!-- Preview Body: Card-style welcome content -->
            <div class="flex-1 flex items-center justify-center p-5" style="background:#12141C;">
              <div class="relative w-full max-w-[200px] rounded-lg p-5 flex flex-col items-center gap-4 text-center shadow-xl"
                style="background: rgba(28,31,42,0.85); border:1px solid rgba(70,69,84,0.3);">
                <!-- Shadow overlay (Figma detail) -->
                <div class="absolute inset-0 -z-10 rounded-lg"
                  style="box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25);" />

                <!-- Heading -->
                <div class="w-full text-left pr-8">
                  <h3 class="text-xl font-bold leading-tight" style="color:#C0C1FF;">
                    欢迎使用 AI Dev<br/>Studio
                  </h3>
                </div>

                <!-- Subtitle -->
                <p class="text-sm w-full text-left" style="color:#C7C4D7;">
                  这是一个实时预览区域
                </p>

                <!-- CTA Button -->
                <button class="self-start mt-1 px-6 py-2 rounded-full text-sm font-bold transition-all hover:brightness-110"
                  style="background:#C0C1FF; color:#1000A9; box-shadow: 0 4px 6px -4px rgba(0,0,0,0.1), 0 10px 15px -3px rgba(0,0,0,0.1);">
                  交互测试
                </button>
              </div>
            </div>
          </aside>
        </div>

        <!-- Bottom Terminal Panel (180px, Figma design) -->
        <div v-if="showBottomPanel" class="shrink-0 flex flex-col border-t border-[var(--color-ide-border)]" style="height:180px; background:#171B26;">
          <!-- Terminal Tabs Header -->
          <div class="flex items-center justify-between px-4 h-9 shrink-0" style="background:#262A35; border-bottom:1px solid var(--color-ide-border);">
            <!-- Tabs -->
            <div class="flex gap-4">
              <button
                v-for="tab in terminalTabs" :key="tab.id"
                class="text-xs font-semibold pb-2 -mb-px transition-colors relative"
                :style="{ color: activeTerminalTab === tab.id ? '#C0C1FF' : '#908FA0', borderBottom: activeTerminalTab === tab.id ? '2px solid #C0C1FF' : '2px solid transparent' }"
                @click="activeTerminalTab = tab.id"
              >
                {{ tab.label }}
              </button>
            </div>
            <!-- Actions -->
            <div class="flex items-center gap-2">
              <button class="p-1 rounded hover:bg-white/5 transition-colors" style="color:#908FA0;" title="清除">
                <svg width="9.33" height="9.33" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M11 3L3 11M3 3l8 8"/></svg>
              </button>
              <button class="p-1 rounded hover:bg-white/5 transition-colors" style="color:#908FA0;" title="分割">
                <svg width="10.67" height="12" viewBox="0 0 16 18" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="10" height="12" rx="1"/><path d="M8 3v12"/></svg>
              </button>
              <button class="p-1 rounded hover:bg-white/5 transition-colors" style="color:#908FA0;" title="关闭面板" @click="store.layout.bottomPanelVisible = false">
                <svg width="9.33" height="9.33" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M11 3L3 11M3 3l8 8"/></svg>
              </button>
            </div>
          </div>

          <!-- Terminal Content -->
          <div class="flex-1 overflow-auto">
            <Terminal />
          </div>
        </div>
      </template>
    </div>
  </div>
</template>
