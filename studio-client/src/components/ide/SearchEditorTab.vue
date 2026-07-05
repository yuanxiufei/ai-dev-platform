<script setup lang="ts">
/**
 * SearchEditorTab — VSCode Search Editor 对标
 * Session 42: 搜索结果持久化到编辑器标签页
 */
import { ref, computed } from "vue"
import { useIDEStore } from "@/stores/useIDEStore"
import { Search, X, FileText, ChevronRight, Trash2, RefreshCw } from "lucide-vue-next"

const props = defineProps<{ tabId: string; searchQuery?: string; replaceQuery?: string }>()
const emit = defineEmits<{ (e: "close"): void }>()

const store = useIDEStore()

const query = ref(props.searchQuery ?? "")
const replaceText = ref(props.replaceQuery ?? "")
const caseSensitive = ref(false)
const wholeWord = ref(false)
const regexMode = ref(false)
const contextLines = ref(2)
const searching = ref(false)
const results = ref<{ file: string; line: number; content: string; matches: number[] }[]>([])
const excludedResults = ref<Set<string>>(new Set())

const fileGroups = computed(() => {
  const map = new Map<string, typeof results.value>()
  for (const r of results.value) {
    if (excludedResults.value.has(`${r.file}:${r.line}`)) continue
    if (!map.has(r.file)) map.set(r.file, [])
    map.get(r.file)!.push(r)
  }
  return Array.from(map.entries())
})

function search(): void {
  if (!query.value.trim()) return
  searching.value = true
  results.value = []
  // 搜索所有打开的标签页
  for (const tab of store.tabs) {
    const content = tab.content ?? ""
    const lines = content.split("\n")
    let q = query.value
    if (!regexMode.value) q = q.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
    try {
      const re = new RegExp(wholeWord.value ? `\\b${q}\\b` : q, caseSensitive.value ? "g" : "gi")
      for (let i = 0; i < lines.length; i++) {
        const matches = [...lines[i].matchAll(re)]
        if (matches.length > 0) {
          results.value.push({
            file: tab.filePath ?? tab.label,
            line: i + 1,
            content: lines[i].trim(),
            matches: matches.map(m => m.index ?? 0),
          })
        }
      }
    } catch { /* ignore */ }
  }
  searching.value = false
}

function excludeResult(file: string, line: number): void {
  excludedResults.value.add(`${file}:${line}`)
  excludedResults.value = new Set(excludedResults.value)
}

function openResult(file: string, line: number): void {
  store.openFile(file)
  // 跳转到行
  setTimeout(() => {
    const ed = (window as any).__monacoInstances?.[file]
    if (ed) { ed.revealLineInCenter(line); ed.setPosition({ lineNumber: line, column: 1 }) }
  }, 300)
}

const totalMatches = computed(() => results.value.length)
const totalFiles = computed(() => new Set(results.value.map(r => r.file)).size)
</script>

<template>
  <div class="flex flex-col h-full" style="background: var(--color-ide-bg);">
    <!-- 搜索栏 -->
    <div class="flex items-center gap-2 px-3 py-2 border-b" style="border-color: var(--color-ide-border);">
      <Search :size="14" style="color: var(--color-ide-accent);" />
      <input v-model="query" class="flex-1 bg-transparent text-[12px] outline-none font-mono" style="color: var(--color-ide-text);" placeholder="搜索..." @keydown.enter="search" />
      <button v-if="replaceText" class="flex items-center gap-1 text-[11px] px-2 py-0.5 rounded" style="color: var(--color-ide-text-dim);">
        替换: <input v-model="replaceText" class="w-24 bg-transparent outline-none text-[11px]" style="color: var(--color-ide-text);" />
      </button>
      <div class="flex items-center gap-1 text-[10px]">
        <button @click="caseSensitive = !caseSensitive" :class="['px-1.5 py-0.5 rounded font-mono', caseSensitive ? 'bg-white/10' : '']" style="color: var(--color-ide-text-dim);" title="区分大小写">Aa</button>
        <button @click="wholeWord = !wholeWord" :class="['px-1.5 py-0.5 rounded font-mono', wholeWord ? 'bg-white/10' : '']" style="color: var(--color-ide-text-dim);" title="全字匹配">W</button>
        <button @click="regexMode = !regexMode" :class="['px-1.5 py-0.5 rounded font-mono', regexMode ? 'bg-white/10' : '']" style="color: var(--color-ide-text-dim);" title="正则">.*</button>
        <button @click="contextLines = Math.max(0, contextLines - 1)" class="px-1 py-0.5 rounded hover:bg-white/5 text-[9px]" style="color: var(--color-ide-text-dim);">-</button>
        <span class="px-1" style="color: var(--color-ide-text-dim);">{{ contextLines }}</span>
        <button @click="contextLines = Math.min(10, contextLines + 1)" class="px-1 py-0.5 rounded hover:bg-white/5 text-[9px]" style="color: var(--color-ide-text-dim);">+</button>
      </div>
      <button @click="search" class="p-1 rounded hover:bg-white/5"><RefreshCw :size="14" :class="{ 'animate-spin': searching }" style="color: var(--color-ide-text-dim);" /></button>
    </div>

    <!-- 结果列表 -->
    <div class="flex-1 overflow-y-auto scrollbar-thin">
      <div v-if="results.length === 0 && query && !searching" class="flex flex-col items-center justify-center py-16 gap-2">
        <Search :size="32" style="color: var(--color-ide-text-dim); opacity: 0.15;" />
        <span class="text-[12px]" style="color: var(--color-ide-text-dim);">没有匹配结果</span>
      </div>

      <div v-for="[file, fileResults] in fileGroups" :key="file" class="border-b" style="border-color: var(--color-ide-border); border-opacity: 0.3;">
        <div class="flex items-center gap-2 px-3 py-1.5 text-[11px] font-semibold" style="background: var(--color-ide-bg-secondary); color: var(--color-ide-text);">
          <FileText :size="12" style="color: var(--color-ide-accent);" />
          <span class="truncate">{{ file.split("/").pop() ?? file }}</span>
          <span class="opacity-40" style="color: var(--color-ide-text-dim);">{{ fileResults.length }} 个匹配</span>
        </div>
        <div v-for="r in fileResults" :key="`${r.file}:${r.line}`" class="flex items-center gap-2 px-3 py-1 hover:bg-white/5 cursor-pointer" @click="openResult(r.file, r.line)">
          <span class="text-[10px] font-mono w-10 text-right shrink-0" style="color: var(--color-ide-accent);">{{ r.line }}</span>
          <span class="text-[11px] font-mono flex-1 truncate whitespace-pre" style="color: var(--color-ide-text);">{{ r.content }}</span>
          <button @click.stop="excludeResult(r.file, r.line)" class="p-0.5 rounded hover:bg-white/10 opacity-0 group-hover:opacity-100">
            <X :size="12" style="color: var(--color-ide-text-dim);" />
          </button>
        </div>
      </div>
    </div>

    <!-- 底部统计 -->
    <div class="flex items-center gap-4 px-3 py-1.5 border-t text-[10px]" style="border-color: var(--color-ide-border); color: var(--color-ide-text-dim);">
      <span>{{ totalMatches }} 个结果 · {{ totalFiles }} 个文件</span>
      <span v-if="excludedResults.size > 0">{{ excludedResults.size }} 个已排除</span>
    </div>
  </div>
</template>
