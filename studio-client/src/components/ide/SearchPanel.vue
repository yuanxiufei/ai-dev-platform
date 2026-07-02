<script setup lang="ts">
/**
 * SearchPanel — VS Code Search Viewlet (像素级对齐)
 *
 * 功能对标 VS Code 搜索视图:
 *   - 搜索输入框 (带历史记录)
 *   - 替换输入框 (可展开/折叠)
 *   - 文件包含/排除模式
 *   - 大小写敏感 / 全词匹配 / 正则表达式
 *   - 搜索结果按文件分组 (树形展开)
 *   - 搜索统计 (N results in M files)
 *   - 替换预览 / 全部替换
 *   - 搜索进度指示器
 */
import { ref, computed, watch } from "vue"
import { ChevronRight, ChevronDown, Regex, CaseSensitive, WholeWord, Replace, Search, X, RotateCw, ChevronUp, ChevronDown as ChevronDownIcon, FileText, ListFilter, History } from "lucide-vue-next"
import { useIDEStore } from "@/stores/useIDEStore"
import type { SearchResult } from "@/types/ide"

const store = useIDEStore()

// ── 本地搜索状态 ──
const query = ref("")
const replaceQuery = ref("")
const showReplace = ref(false)
const caseSensitive = ref(false)
const wholeWord = ref(false)
const useRegex = ref(false)
const includePattern = ref("")
const excludePattern = ref("**/node_modules/**, **/dist/**, **/.git/**")
const showExclude = ref(false)

// 🔥 搜索历史
const searchHistory = ref<string[]>([])
const showHistory = ref(false)

// 🔥 搜索结果文件折叠状态
const collapsedFiles = ref<Record<string, boolean>>({})

// 🔥 搜索结果 (模拟 — 实际项目会通过后端 API 或 vite-plugin 搜索)
const results = ref<SearchResult[]>([])
const searching = ref(false)
const resultStats = ref("")
const currentMatchIndex = ref(0)

// ── 分组结果 ──
const groupedResults = computed(() => {
  const groups: Record<string, SearchResult[]> = {}
  for (const r of results.value) {
    if (!groups[r.file]) groups[r.file] = []
    groups[r.file].push(r)
  }
  return groups
})

const fileList = computed(() => Object.keys(groupedResults.value))
const totalMatches = computed(() => results.value.length)
const totalFiles = computed(() => fileList.value.length)

// ── 切换文件折叠 ──
function toggleFile(file: string): void {
  collapsedFiles.value[file] = !collapsedFiles.value[file]
}

// ── 添加搜索历史 ──
function addToHistory(q: string): void {
  if (!q.trim()) return
  searchHistory.value = [q, ...searchHistory.value.filter(h => h !== q)].slice(0, 20)
}

// ── 模拟搜索 ──
async function doSearch(): Promise<void> {
  if (!query.value.trim()) return
  addToHistory(query.value)
  searching.value = true
  showHistory.value = false

  // 模拟搜索延迟
  await new Promise(r => setTimeout(r, 400))

  // 🔥 模拟搜索结果 (实际项目通过后端 API 搜索)
  const files = store.tabs.map(t => t.filePath || t.label)
  const mockResults: SearchResult[] = []
  for (const f of files) {
    const ext = f.split(".").pop()?.toLowerCase() || ""
    const matchCount = ext === "ts" || ext === "tsx" || ext === "py" || ext === "vue" ? 3 + Math.floor(Math.random() * 5) : 0
    for (let i = 0; i < matchCount; i++) {
      const line = Math.floor(Math.random() * 200) + 1
      mockResults.push({
        file: f,
        line,
        column: Math.floor(Math.random() * 40) + 1,
        lineText: `  // Line ${line}: ... ${query.value} ... example content here`,
        matchLength: query.value.length,
        matches: [{ start: 3 + Math.floor(Math.random() * 30), end: 3 + Math.floor(Math.random() * 30) + query.value.length }],
      })
    }
  }

  results.value = mockResults.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line)
  collapsedFiles.value = {}
  resultStats.value = `${mockResults.length} 个结果, ${fileList.value.length} 个文件`
  currentMatchIndex.value = 0
  searching.value = false
}

// ── 清除搜索 ──
function clearSearch(): void {
  query.value = ""
  replaceQuery.value = ""
  results.value = []
  resultStats.value = ""
  currentMatchIndex.value = 0
}

// ── 替换操作 ──
function replaceOne(result: SearchResult): void {
  // 🔥 单个替换 — 实际项目需通过编辑器 API 实现
  console.log("[Search] Replace one:", result.file, result.line)
}

function replaceAll(): void {
  // 🔥 全部替换 — 实际项目需通过编辑器 API 实现
  console.log("[Search] Replace all:", totalMatches.value, "matches")
}

// ── 点击结果跳转 ──
function goToResult(result: SearchResult): void {
  store.openFile(result.file)
}

// ── 导航到上一个/下一个匹配 ──
function nextMatch(): void {
  if (results.value.length === 0) return
  currentMatchIndex.value = (currentMatchIndex.value + 1) % results.value.length
}

function prevMatch(): void {
  if (results.value.length === 0) return
  currentMatchIndex.value = (currentMatchIndex.value - 1 + results.value.length) % results.value.length
}

// ── 清除历史 ──
function clearHistory(): void {
  searchHistory.value = []
}
</script>

<template>
  <div class="search-panel flex flex-col h-full text-[13px]"
    style="color: var(--color-ide-text); background: var(--color-ide-surface);">

    <!-- ═══ 搜索输入框区域 ═══ -->
    <div class="search-inputs shrink-0 px-3 pt-3 pb-2 space-y-2"
      style="border-bottom: 1px solid var(--color-ide-border);">
      <!-- 搜索框 -->
      <div class="relative">
        <div class="flex items-center gap-1 border rounded-[3px] overflow-hidden"
          :style="{
            background: 'var(--color-chat-input-bg)',
            borderColor: query.trim()
              ? 'var(--color-ide-border-focus)'
              : 'transparent',
          }">
          <!-- 🔥 搜索/替换切换按钮 -->
          <button
            class="shrink-0 w-7 h-7 flex items-center justify-center hover:bg-[var(--color-ide-surface-hover)] rounded-[3px]"
            :title="showReplace ? '隐藏替换' : '显示替换 (Ctrl+H)'"
            @click="showReplace = !showReplace"
          >
            <Search v-if="!showReplace" :size="14" style="color: var(--color-ide-text-dim);" />
            <Replace v-else :size="14" style="color: var(--color-ide-accent);" />
          </button>
          <!-- 输入框 -->
          <input
            v-model="query"
            type="text"
            class="flex-1 h-7 bg-transparent text-[13px] outline-none px-1"
            placeholder="搜索"
            @keydown.enter="doSearch"
            @focus="showHistory = searchHistory.length > 0"
            @blur="setTimeout(() => showHistory = false, 200)"
          />
          <!-- 清除按钮 -->
          <button
            v-if="query"
            class="shrink-0 w-7 h-7 flex items-center justify-center hover:bg-[var(--color-ide-surface-hover)] rounded-[3px]"
            @click="clearSearch"
          >
            <X :size="12" style="color: var(--color-ide-text-dim);" />
          </button>
          <!-- 搜索按钮 -->
          <button
            class="shrink-0 w-7 h-7 flex items-center justify-center hover:bg-[var(--color-ide-surface-hover)] rounded-[3px]"
            :disabled="!query.trim()"
            @click="doSearch"
          >
            <Search :size="14" :style="{ color: query.trim() ? 'var(--color-ide-text)' : 'var(--color-ide-text-dim)', opacity: query.trim() ? 1 : 0.3 }" />
          </button>
        </div>

        <!-- 🔥 搜索历史下拉 -->
        <div v-if="showHistory && searchHistory.length > 0"
          class="absolute left-0 right-0 top-full mt-0.5 z-50 max-h-48 overflow-y-auto rounded-[3px] shadow-xl border py-1"
          style="background: var(--color-ide-surface); border-color: var(--color-ide-border);">
          <div class="flex items-center justify-between px-3 py-0.5">
            <span class="text-[10px] uppercase tracking-wider" style="color: var(--color-ide-text-dim);">最近搜索</span>
            <button
              class="text-[10px] hover:underline"
              style="color: var(--color-ide-accent);"
              @click="clearHistory"
            >清除</button>
          </div>
          <button
            v-for="h in searchHistory"
            :key="h"
            class="flex items-center gap-2 w-full text-left px-3 py-1 text-[12px] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
            @mousedown.prevent="query = h; doSearch()"
          >
            <History :size="10" style="color: var(--color-ide-text-dim); opacity: 0.5;" />
            <span class="truncate">{{ h }}</span>
          </button>
        </div>
      </div>

      <!-- 🔥 替换输入框 (可折叠) -->
      <div v-if="showReplace" class="flex items-center gap-1 border rounded-[3px] overflow-hidden"
        :style="{
          background: 'var(--color-chat-input-bg)',
          borderColor: replaceQuery.trim()
            ? 'var(--color-ide-border-focus)'
            : 'transparent',
        }">
        <input
          v-model="replaceQuery"
          type="text"
          class="flex-1 h-7 bg-transparent text-[13px] outline-none px-2"
          placeholder="替换"
          @keydown.enter="replaceAll"
        />
        <button
          class="shrink-0 px-2 h-7 flex items-center justify-center text-[11px] font-medium hover:bg-[var(--color-ide-surface-hover)] transition-colors"
          :style="{ color: 'var(--color-ide-accent)' }"
          :disabled="!replaceQuery.trim() || results.length === 0"
          @click="replaceAll"
          title="全部替换 (Ctrl+Alt+Enter)"
        >
          全部替换
        </button>
      </div>

      <!-- 🔥 搜索选项行 -->
      <div class="flex items-center gap-1">
        <!-- 要包含的文件 -->
        <div class="relative flex-1 min-w-0">
          <div class="flex items-center gap-1 border rounded-[3px] overflow-hidden"
            :style="{
              background: includePattern ? 'var(--color-chat-input-bg)' : 'transparent',
              borderColor: includePattern ? 'var(--color-ide-border-focus)' : 'transparent',
            }">
            <input
              v-model="includePattern"
              type="text"
              class="flex-1 h-6 bg-transparent text-[11px] outline-none px-1.5"
              placeholder="要包含的文件"
            />
            <button
              v-if="includePattern"
              class="shrink-0 w-5 h-6 flex items-center justify-center"
              @click="includePattern = ''"
            >
              <X :size="10" style="color: var(--color-ide-text-dim);" />
            </button>
          </div>
        </div>

        <!-- 🔥 排除模式展开 -->
        <button
          class="shrink-0 w-6 h-6 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
          :class="{ 'opacity-100': excludePattern, 'opacity-40': !excludePattern }"
          title="要排除的文件"
          @click="showExclude = !showExclude"
        >
          <ListFilter :size="13" style="color: var(--color-ide-text-dim);" />
        </button>

        <!-- 🔥 搜索选项 toggle 按钮组 -->
        <button
          class="search-option-btn"
          :class="{ active: caseSensitive }"
          title="区分大小写 (Alt+C)"
          @click="caseSensitive = !caseSensitive"
        >
          <CaseSensitive :size="14" />
        </button>
        <button
          class="search-option-btn"
          :class="{ active: wholeWord }"
          title="全词匹配 (Alt+W)"
          @click="wholeWord = !wholeWord"
        >
          <WholeWord :size="14" />
        </button>
        <button
          class="search-option-btn"
          :class="{ active: useRegex }"
          title="使用正则表达式 (Alt+R)"
          @click="useRegex = !useRegex"
        >
          <Regex :size="14" />
        </button>

        <!-- 🔥 刷新按钮 -->
        <button
          class="shrink-0 w-6 h-6 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)] transition-colors opacity-70 hover:opacity-100"
          title="刷新搜索"
          @click="doSearch"
        >
          <RotateCw :size="12" style="color: var(--color-ide-text-dim);" />
        </button>
      </div>

      <!-- 🔥 排除文件模式 (可折叠) -->
      <div v-if="showExclude" class="flex items-center gap-1 border rounded-[3px] overflow-hidden"
        :style="{
          background: 'var(--color-chat-input-bg)',
          borderColor: excludePattern ? 'var(--color-ide-border-focus)' : 'transparent',
        }">
        <input
          v-model="excludePattern"
          type="text"
          class="flex-1 h-6 bg-transparent text-[11px] outline-none px-1.5"
          placeholder="要排除的文件 (如 **/node_modules/**)"
        />
        <button
          v-if="excludePattern"
          class="shrink-0 w-5 h-6 flex items-center justify-center"
          @click="excludePattern = ''"
        >
          <X :size="10" style="color: var(--color-ide-text-dim);" />
        </button>
      </div>
    </div>

    <!-- ═══ 搜索结果区域 ═══ -->
    <div class="search-results flex-1 overflow-y-auto min-h-0">
      <!-- 🔥 搜索统计 + 导航 -->
      <div v-if="resultStats" class="flex items-center justify-between px-3 h-8 shrink-0"
        style="border-bottom: 1px solid var(--color-ide-border);">
        <span class="text-[11px] font-semibold" style="color: var(--color-ide-text-dim);">
          {{ resultStats }}
        </span>
        <div class="flex items-center gap-0.5">
          <button
            class="w-6 h-6 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)]"
            title="上一个匹配 (F4)"
            @click="prevMatch"
          >
            <ChevronUp :size="14" style="color: var(--color-ide-text-dim);" />
          </button>
          <button
            class="w-6 h-6 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)]"
            title="下一个匹配 (Shift+F4)"
            @click="nextMatch"
          >
            <ChevronDownIcon :size="14" style="color: var(--color-ide-text-dim);" />
          </button>
        </div>
      </div>

      <!-- 🔥 搜索中指示器 -->
      <div v-if="searching" class="flex items-center justify-center py-8 gap-2">
        <RotateCw :size="14" class="animate-spin" style="color: var(--color-ide-text-dim);" />
        <span class="text-[12px]" style="color: var(--color-ide-text-dim);">正在搜索...</span>
      </div>

      <!-- 🔥 搜索结果 (按文件分组, VS Code 风格) -->
      <div v-if="!searching && results.length > 0" class="py-0.5">
        <div v-for="file in fileList" :key="file">
          <!-- 文件头 -->
          <button
            class="search-file-header flex items-center gap-1 w-full h-8 px-3 text-left hover:bg-[var(--color-ide-surface-hover)] transition-colors group"
            @click="toggleFile(file)"
          >
            <ChevronRight
              v-if="collapsedFiles[file]"
              :size="12"
              :style="{ color: 'var(--color-ide-text-dim)', transform: 'rotate(0deg)', transition: 'transform 0.1s' }"
            />
            <ChevronDown
              v-else
              :size="12"
              :style="{ color: 'var(--color-ide-text-dim)', transform: 'rotate(0deg)', transition: 'transform 0.1s' }"
            />
            <FileText :size="13" style="color: var(--color-ide-text-dim); opacity: 0.6;" />
            <span class="text-[12px] font-medium truncate flex-1" style="color: var(--color-ide-text);">
              {{ file }}
            </span>
            <span class="text-[10px] px-1.5 py-0.5 rounded-full font-semibold"
              style="background: var(--color-ide-accent); color: #fff; opacity: 0.85;">
              {{ groupedResults[file].length }}
            </span>
          </button>

          <!-- 文件下的匹配行 -->
          <div v-if="!collapsedFiles[file]" class="pb-0.5">
            <div
              v-for="(result, ri) in groupedResults[file]"
              :key="`${file}-${ri}`"
              class="search-match flex items-start gap-2 px-5 py-0.5 cursor-pointer hover:bg-[var(--color-ide-surface-hover)] transition-colors"
              @click="goToResult(result)"
              @dblclick="goToResult(result)"
            >
              <!-- 行号 -->
              <span class="shrink-0 w-9 text-right text-[11px] leading-5"
                style="color: var(--color-ide-text-dim); opacity: 0.6; font-family: 'Cascadia Code','JetBrains Mono',monospace;">
                {{ result.line }}
              </span>
              <!-- 匹配行文本 (含高亮) -->
              <span class="text-[12px] leading-5 whitespace-pre font-mono truncate flex-1"
                style="color: var(--color-ide-text);">
                <!-- 🔥 简单高亮 (实际应用需要更复杂的文本分割) -->
                {{ result.lineText }}
              </span>
              <!-- 🔥 单个替换按钮 (仅在显示替换时) -->
              <button
                v-if="showReplace"
                class="shrink-0 w-5 h-5 flex items-center justify-center rounded-[3px] opacity-0 group-hover:opacity-100 hover:bg-[var(--color-ide-surface-active)] transition-all"
                title="替换此匹配"
                @click.stop="replaceOne(result)"
              >
                <Replace :size="11" style="color: var(--color-ide-accent);" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 🔥 空状态 -->
      <div v-if="!searching && query && results.length === 0" class="flex flex-col items-center justify-center py-12 gap-2">
        <Search :size="24" style="color: var(--color-ide-text-dim); opacity: 0.2;" />
        <span class="text-[12px]" style="color: var(--color-ide-text-dim);">
          无结果。请尝试其他搜索词。
        </span>
      </div>

      <div v-if="!searching && !query" class="flex flex-col items-center justify-center py-12 gap-2">
        <Search :size="24" style="color: var(--color-ide-text-dim); opacity: 0.15;" />
        <span class="text-[12px]" style="color: var(--color-ide-text-dim);">
          输入搜索词以开始
        </span>
        <span class="text-[10px] opacity-50" style="color: var(--color-ide-text-dim);">
          Ctrl+Shift+F 跨文件搜索
        </span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══ 搜索选项按钮 ═══ */
.search-option-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-ide-text-dim);
  opacity: 0.4;
  transition: all 0.1s ease;
}
.search-option-btn:hover {
  opacity: 0.7;
  background: var(--color-ide-surface-hover);
}
.search-option-btn.active {
  opacity: 1;
  color: var(--color-ide-accent);
  background: rgba(0, 122, 204, 0.1);
}

/* ═══ 搜索文件头 ═══ */
.search-file-header {
  border-bottom: 1px solid transparent;
}
.search-file-header:hover {
  border-bottom-color: var(--color-ide-border);
}

/* ═══ 搜索匹配行高亮 ═══ */
.search-match {
  border-left: 2px solid transparent;
  transition: all 0.08s ease;
}
.search-match:hover {
  border-left-color: var(--color-ide-accent);
}

.search-match .group-hover\:opacity-100 {
  opacity: 0;
}
.search-match:hover .group-hover\:opacity-100 {
  opacity: 1;
}
</style>
