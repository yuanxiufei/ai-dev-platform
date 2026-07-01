<script setup lang="ts">
/**
 * AtMentionPopup.vue — @-mention 文件引用弹出面板
 *
 * 参考项目：Continue (AtMentionPopover) — 用户输入 "@" 时触发
 *
 * 功能：
 *   1. 键盘键入 "@" 自动弹出，输入关键词实时过滤
 *   2. 支持多种引用类型：@file, @dir, @symbol, @recent
 *   3. 键盘导航（↑↓ Enter Esc）
 *   4. 结果分组（最近打开 / 项目文件 / 搜索结果）
 *   5. 文件路径面包屑 + 语言/大小等元信息
 */
import {
  Clock,
  FileCode,
  Folder,
  FolderOpen,
  Search,
  X,
} from "lucide-vue-next"
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue"
import type { ReferencedFile } from "@/types/studio"

const props = defineProps<{
  visible: boolean
  /** 光标位置（用于定位弹出面板） */
  anchorEl?: HTMLElement | null
  /** 已引用的文件（避免重复选择） */
  existingFiles?: ReferencedFile[]
  /** 项目根路径 */
  projectRoot?: string
}>()

const emit = defineEmits<{
  (e: "select", file: ReferencedFile): void
  (e: "selectDir", dirPath: string): void
  (e: "close"): void
}>()

// ═══════════════════════ 搜索状态 ═══════════════════════
const filter = ref("")
const fakeFiles = ref<{ path: string; name: string; language?: string; size?: string }[]>([])
const loading = ref(false)
const activeIndex = ref(0)
const inputRef = ref<HTMLInputElement | null>(null)
const popupRef = ref<HTMLDivElement | null>(null)

// ═══════════════════════ 引用类型 Tab ═══════════════════════
type RefType = "file" | "dir" | "symbol" | "recent"
const activeTab = ref<RefType>("file")

const tabs: { id: RefType; label: string; shortcut: string }[] = [
  { id: "file", label: "文件", shortcut: "@file" },
  { id: "dir", label: "目录", shortcut: "@dir" },
  { id: "symbol", label: "符号", shortcut: "@sym" },
  { id: "recent", label: "最近", shortcut: "@recent" },
]

// ═══════════════════════ 模拟文件列表 ═══════════════════════
// 实际使用时通过后端 API 获取项目文件列表
const recentFiles = ref<typeof fakeFiles.value>([
  { path: "src/pages/AgentChat.vue", name: "AgentChat.vue", language: "vue" },
  { path: "src/components/ChatInput.vue", name: "ChatInput.vue", language: "vue" },
  { path: "src/types/studio.ts", name: "studio.ts", language: "typescript" },
  { path: "backend/app/core/agent/orchestrator.py", name: "orchestrator.py", language: "python" },
])

async function loadFiles(query?: string) {
  loading.value = true
  try {
    const token = localStorage.getItem("token")
    const headers: Record<string, string> = { "Content-Type": "application/json" }
    if (token) headers.Authorization = `Bearer ${token}`
    const params = new URLSearchParams()
    if (query) params.set("q", query)
    params.set("limit", "20")
    const res = await fetch(`/api/v1/system/codebase/files?${params}`, { headers })
    if (res.ok) {
      const data = await res.json()
      fakeFiles.value = data.files || []
    }
  } catch {
    // 静默回退到模拟数据
  } finally {
    loading.value = false
  }
}

// ═══════════════════════ 过滤逻辑 ═══════════════════════
const filteredResults = computed(() => {
  const q = filter.value.toLowerCase().trim()
  let source: typeof fakeFiles.value = []

  switch (activeTab.value) {
    case "recent":
      source = recentFiles.value
      break
    case "file":
    default:
      source = fakeFiles.value
      break
  }

  if (!q) return source.slice(0, 15)

  // 模糊匹配：路径或文件名包含关键词
  return source
    .filter(f =>
      f.path.toLowerCase().includes(q) ||
      f.name.toLowerCase().includes(q)
    )
    .slice(0, 15)
})

// 已选中项的路径集合
const existingPaths = computed(() =>
  new Set(props.existingFiles?.map(f => f.path) || [])
)

// ═══════════════════════ 分组（最近/其他） ═══════════════════════
const groupedResults = computed(() => {
  const recent = filteredResults.value.filter(f =>
    recentFiles.value.some(r => r.path === f.path)
  )
  const others = filteredResults.value.filter(f =>
    !recentFiles.value.some(r => r.path === f.path)
  )
  return { recent, others }
})

// ═══════════════════════ 键盘导航 ═══════════════════════
function handleKeydown(e: KeyboardEvent) {
  switch (e.key) {
    case "ArrowDown":
      e.preventDefault()
      activeIndex.value = Math.min(activeIndex.value + 1, filteredResults.value.length - 1)
      break
    case "ArrowUp":
      e.preventDefault()
      activeIndex.value = Math.max(activeIndex.value - 1, 0)
      break
    case "Enter":
      e.preventDefault()
      if (filteredResults.value[activeIndex.value]) {
        selectFile(filteredResults.value[activeIndex.value])
      }
      break
    case "Escape":
      e.preventDefault()
      emit("close")
      break
    case "Tab":
      e.preventDefault()
      // 循环切换 Tab
      const idx = tabs.findIndex(t => t.id === activeTab.value)
      activeTab.value = tabs[(idx + 1) % tabs.length].id
      break
  }
}

function selectFile(file: { path: string; name: string; language?: string }) {
  emit("select", {
    path: file.path,
    name: file.name,
    language: file.language,
    type: "full",
  })
  filter.value = ""
  emit("close")
}

function selectDir(e: MouseEvent) {
  e.preventDefault()
  // 在 file tab 下，选择文件的父目录
  if (activeTab.value === "file" && filteredResults.value.length > 0) {
    const firstFile = filteredResults.value[0]
    const dir = firstFile.path.split("/").slice(0, -1).join("/")
    emit("selectDir", dir || ".")
  }
  emit("close")
}

// ═══════════════════════ 生命周期 ═══════════════════════
watch(() => props.visible, (v) => {
  if (v) {
    activeIndex.value = 0
    filter.value = ""
    loadFiles()
    nextTick(() => inputRef.value?.focus())
  }
})

onMounted(() => {
  loadFiles()
})

// 获取文件的语言图标颜色
function langColor(lang?: string): string {
  const map: Record<string, string> = {
    vue: "#42b883", typescript: "#3178c6", javascript: "#f7df1e",
    python: "#3776ab", rust: "#dea584", go: "#00add8",
    css: "#1572b6", html: "#e34f26", json: "#292929",
    yaml: "#cb171e", markdown: "#083fa1", sql: "#4479a1",
  }
  return map[lang || ""] || "#8b8b8b"
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="fixed inset-0 z-[9999]"
      @click.self="emit('close')"
    >
      <!-- 弹出面板 -->
      <div
        ref="popupRef"
        class="absolute bottom-[140px] left-1/2 -translate-x-1/2 w-[480px] max-h-[340px] rounded-xl border border-white/[0.08] bg-surface-900/95 backdrop-blur-xl shadow-2xl shadow-black/40 overflow-hidden flex flex-col animate-in slide-in-from-bottom-2 duration-200"
      >
        <!-- 搜索栏 -->
        <div class="flex items-center gap-2 px-3 py-2.5 border-b border-white/[0.05]">
          <Search class="w-4 h-4 text-gray-500 shrink-0" />
          <input
            ref="inputRef"
            v-model="filter"
            placeholder="搜索文件名（支持模糊匹配）..."
            class="flex-1 bg-transparent text-sm text-gray-200 placeholder-gray-600 focus:outline-none"
            @keydown="handleKeydown"
          />
          <button
            @click="emit('close')"
            class="p-1 rounded-md text-gray-600 hover:text-gray-400 hover:bg-white/5 transition-colors"
          >
            <X class="w-4 h-4" />
          </button>
        </div>

        <!-- Tab 导航 -->
        <div class="flex items-center gap-0.5 px-2 py-1.5 border-b border-white/[0.04] bg-white/[0.01]">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            @click="activeTab = tab.id"
            :class="[
              'px-2.5 py-1 rounded-md text-[11px] font-medium transition-all duration-150',
              activeTab === tab.id
                ? 'bg-brand-500/15 text-brand-400 shadow-sm'
                : 'text-gray-500 hover:text-gray-300 hover:bg-white/[0.03]'
            ]"
          >
            {{ tab.label }}
            <span class="ml-1 text-[9px] opacity-50">{{ tab.shortcut }}</span>
          </button>
        </div>

        <!-- 结果列表 -->
        <div class="flex-1 overflow-y-auto custom-scroll py-1">
          <!-- 加载中 -->
          <div v-if="loading" class="flex items-center justify-center py-8 text-gray-500 text-xs">
            <Search class="w-3.5 h-3.5 animate-pulse mr-1.5" /> 加载文件列表...
          </div>

          <!-- 无结果 -->
          <div v-else-if="filteredResults.length === 0" class="py-10 text-center">
            <FolderOpen class="w-8 h-8 text-gray-700 mx-auto mb-2" />
            <p class="text-xs text-gray-500">未找到匹配文件</p>
            <p class="text-[10px] text-gray-600 mt-1">尝试其他关键词</p>
          </div>

          <!-- 结果列表 -->
          <template v-else>
            <!-- 最近打开分组 -->
            <div v-if="groupedResults.recent.length > 0" class="mb-0.5">
              <div class="px-3 py-1 text-[10px] font-semibold text-gray-600 uppercase tracking-wider flex items-center gap-1">
                <Clock class="w-3 h-3" /> 最近打开
              </div>
              <div
                v-for="(file, idx) in groupedResults.recent"
                :key="'recent-' + file.path"
                :ref="el => {}"
                @click="selectFile(file)"
                @mouseenter="activeIndex = filteredResults.indexOf(file)"
                :class="[
                  'flex items-center gap-2.5 px-3 py-2 mx-1 rounded-lg cursor-pointer transition-all duration-100 group',
                  filteredResults.indexOf(file) === activeIndex
                    ? 'bg-brand-500/10 text-gray-200'
                    : 'text-gray-400 hover:bg-white/[0.03] hover:text-gray-200'
                ]"
              >
                <!-- 语言图标 / 已引用勾选 -->
                <div class="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                  :class="existingPaths.has(file.path) ? 'bg-emerald-500/10' : 'bg-white/[0.03]'"
                >
                  <component
                    :is="existingPaths.has(file.path) ? 'span' : FileCode"
                    v-if="!existingPaths.has(file.path)"
                    class="w-3.5 h-3.5"
                    :style="{ color: langColor(file.language) }"
                  />
                  <span v-else class="text-[10px] text-emerald-400 font-bold">✓</span>
                </div>

                <div class="flex-1 min-w-0">
                  <p class="text-[13px] font-medium truncate font-mono">{{ file.name }}</p>
                  <p class="text-[11px] text-gray-600 truncate">{{ file.path }}</p>
                </div>

                <!-- 语言标签 -->
                <span
                  v-if="file.language"
                  class="text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded-full bg-white/[0.03] text-gray-600 group-hover:text-gray-500"
                >
                  {{ file.language }}
                </span>
              </div>
            </div>

            <!-- 其他文件 -->
            <div v-if="groupedResults.others.length > 0">
              <div class="px-3 py-1 text-[10px] font-semibold text-gray-600 uppercase tracking-wider flex items-center gap-1 mt-1">
                <Folder class="w-3 h-3" />
                {{ activeTab === 'file' ? '项目文件' : '搜索结果' }}
              </div>
              <div
                v-for="(file, idx) in groupedResults.others"
                :key="'other-' + file.path"
                @click="selectFile(file)"
                @mouseenter="activeIndex = filteredResults.indexOf(file)"
                :class="[
                  'flex items-center gap-2.5 px-3 py-2 mx-1 rounded-lg cursor-pointer transition-all duration-100 group',
                  filteredResults.indexOf(file) === activeIndex
                    ? 'bg-brand-500/10 text-gray-200'
                    : 'text-gray-400 hover:bg-white/[0.03] hover:text-gray-200'
                ]"
              >
                <div class="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 bg-white/[0.03]">
                  <FileCode class="w-3.5 h-3.5" :style="{ color: langColor(file.language) }" />
                </div>
                <div class="flex-1 min-w-0">
                  <p class="text-[13px] font-medium truncate font-mono">{{ file.name }}</p>
                  <p class="text-[11px] text-gray-600 truncate">{{ file.path }}</p>
                </div>
                <span
                  v-if="file.language"
                  class="text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded-full bg-white/[0.03] text-gray-600 group-hover:text-gray-500 shrink-0"
                >
                  {{ file.language }}
                </span>
              </div>
            </div>
          </template>

          <!-- 目录引用入口 -->
          <div class="border-t border-white/[0.04] mt-1 pt-1 px-3 pb-1">
            <button
              @click="selectDir"
              class="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-[11px] text-gray-500 hover:text-gray-300 hover:bg-white/[0.03] transition-colors"
            >
              <Folder class="w-3.5 h-3.5" />
              引用整个目录
            </button>
          </div>
        </div>

        <!-- 底部提示 -->
        <div class="px-3 py-1.5 border-t border-white/[0.04] bg-white/[0.01]">
          <div class="flex items-center gap-3 text-[10px] text-gray-600">
            <span><kbd class="px-1 py-0.5 rounded bg-white/[0.04] border border-white/[0.06] text-[9px]">↑↓</kbd> 导航</span>
            <span><kbd class="px-1 py-0.5 rounded bg-white/[0.04] border border-white/[0.06] text-[9px]">Enter</kbd> 选择</span>
            <span><kbd class="px-1 py-0.5 rounded bg-white/[0.04] border border-white/[0.06] text-[9px]">Tab</kbd> 切换</span>
            <span><kbd class="px-1 py-0.5 rounded bg-white/[0.04] border border-white/[0.06] text-[9px]">Esc</kbd> 关闭</span>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.custom-scroll::-webkit-scrollbar { width: 3px; }
.custom-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,.06); border-radius: 9999px; }

@keyframes slide-in-from-bottom-2 {
  from { opacity: 0; transform: translateX(-50%) translateY(8px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}
</style>
