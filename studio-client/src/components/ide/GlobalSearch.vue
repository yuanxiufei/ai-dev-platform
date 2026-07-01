<script setup lang="ts">/** IDE — Global Search & Replace (VSCode-style full implementation) */
import { ref, computed, watch, nextTick } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { Search, ArrowUpDown, X, RefreshCw, Replace, CaseSensitive, WholeWord, Regex, Filter, ChevronDown, ChevronRight, FileText, Hash } from 'lucide-vue-next'

defineProps<{ visible: boolean }>()
const emit = defineEmits<(e:'close')=>void>()
const store = useIDEStore(), si = ref<HTMLInputElement|null>(null), rl = ref<HTMLDivElement|null>(null)
const query = computed({ get:()=>store.searchState.query, set:(v:string)=>store.searchState.query=v })
const rq = computed({ get:()=>store.searchState.replaceQuery, set:(v:string)=>store.searchState.replaceQuery=v })
const includePattern = ref('')
const excludePattern = ref('node_modules,.git,dist,__pycache__,target')
const showFilterBar = ref(false)

// Filter toggles from searchState
const caseSensitive = computed({ get:()=>store.searchState.caseSensitive, set:(v)=>store.searchState.caseSensitive=v })
const wholeWord = computed({ get:()=>store.searchState.wholeWord, set:(v)=>store.searchState.wholeWord=v })
const useRegex = computed({ get:()=>store.searchState.useRegex, set:(v)=>store.searchState.useRegex=v })

let _isTauri: boolean | null = null
function isTauri(): boolean {
  if (_isTauri !== null) return _isTauri
  try { _isTauri = !!(window as any).__TAURI_INTERNALS__; return !!_isTauri } catch { _isTauri = false; return false }
}

async function doSearch(): Promise<void> {
  if (!query.value.trim()) return
  store.searchState.searching = true
  store.searchState.results = []

  if (isTauri() && store.workspaceRoot) {
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const matchedFiles: string[] = await invoke('search_files', {
        request: {
          path: store.workspaceRoot,
          pattern: query.value,
          excludePatterns: excludePattern.value.split(',').map(s=>s.trim()).filter(Boolean),
          caseSensitive: caseSensitive.value,
          maxResults: 100,
        },
      })
      const contentResults: any[] = await invoke('search_in_file', {
        request: {
          path: store.workspaceRoot,
          pattern: query.value,
          excludePatterns: excludePattern.value.split(',').map(s=>s.trim()).filter(Boolean),
          caseSensitive: caseSensitive.value,
          maxResults: 50,
        },
      })
      const fileSet = new Set<string>()
      const results: any[] = []
      for (const f of matchedFiles.slice(0, 20)) {
        if (!fileSet.has(f)) {
          fileSet.add(f)
          results.push({ file: f, line: 1, column: 1, lineText: f.replace(store.workspaceRoot, ''), matchLength: query.value.length, matches: [{ start: 0, end: query.value.length }] })
        }
      }
      for (const r of contentResults) {
        const key = `${r.file}:${r.line}`
        if (!fileSet.has(key)) {
          fileSet.add(key)
          results.push({ file: r.file, line: r.line, column: r.column, lineText: r.text, matchLength: r.matchLength ?? query.value.length, matches: [{ start: r.column - 1, end: r.column - 1 + (r.matchLength ?? query.value.length) }] })
        }
        if (results.length >= 30) break
      }
      store.searchState.results = results.slice(0, 30)
    } catch (e) { console.warn('[Search] Tauri search failed:', e) }
  } else {
    try {
      const token = localStorage.getItem("token")
      const headers: Record<string, string> = { "Content-Type": "application/json" }
      if (token) headers.Authorization = `Bearer ${token}`
      const params = new URLSearchParams()
      params.set("q", query.value)
      params.set("limit", "30")
      const res = await fetch(`/api/v1/system/codebase/files?${params}`, { headers })
      if (res.ok) {
        const data = await res.json()
        const files: any[] = data.files || []
        const results: any[] = []
        for (const f of files.slice(0, 30)) {
          results.push({ file: f.path, line: 1, column: 1, lineText: f.path, matchLength: query.value.length, matches: [{ start: 0, end: query.value.length }] })
        }
        store.searchState.results = results
      } else { store.searchState.results = [] }
    } catch { store.searchState.results = [] }
  }

  store.searchState.searching = false
  store.searchState.currentResultIndex = store.searchState.results.length ? 0 : -1
  nextTick(() => { if (rl.value) rl.value.scrollTop = 0 })
}

watch(query, () => {})

function onKD(e: KeyboardEvent): void {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); doSearch() }
  else if (e.key === 'Escape') emit('close')
}

function goToPrev(): void {
  if (store.searchState.results.length)
    store.searchState.currentResultIndex = (store.searchState.currentResultIndex - 1 + store.searchState.results.length) % store.searchState.results.length
}
function goToNext(): void {
  if (store.searchState.results.length)
    store.searchState.currentResultIndex = (store.searchState.currentResultIndex + 1) % store.searchState.results.length
}

/** Execute replace on all search results */
async function replaceAll(): Promise<void> {
  if (!rq.value || !query.value || store.searchState.results.length === 0) return
  const files = new Set(store.searchState.results.map(r => r.file))

  for (const filePath of files) {
    try {
      if (isTauri()) {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('replace_in_file', {
          path: filePath,
          search: query.value,
          replace: rq.value,
        })
      }
    } catch (e) {
      console.warn(`[Search] Replace failed for ${filePath}:`, e)
    }
  }

  // Re-search to show updated results
  store.searchState.replaceQuery = rq.value
  await doSearch()
  // Show toast notification
  const count = store.searchState.results.length
  emit('close')
}

/** Replace current result only */
async function replaceCurrent(): Promise<void> {
  if (!rq.value) return
  const result = store.searchState.results[store.searchState.currentResultIndex]
  if (!result) return

  try {
    if (isTauri()) {
      const { invoke } = await import('@tauri-apps/api/core')
      await invoke('replace_in_file', {
        path: result.file,
        search: query.value,
        replace: rq.value,
        line: result.line,
      })
    }
  } catch (e) {
    console.warn('[Search] Single replace failed:', e)
  }
  await doSearch()
}

function hl(lineText: string, matches: any[]): string {
  if (!matches.length) return lineText
  let r = '', le = 0
  for (const m of matches) {
    r += lineText.slice(le, m.start)
    r += `<mark class="bg-yellow-500/40 text-yellow-200 rounded px-0.5">${lineText.slice(m.start, m.end)}</mark>`
    le = m.end
  }
  return r + lineText.slice(le)
}

/** Session 26: VSCode-style 文件分组结果 */
interface FileGroup {
  file: string
  results: typeof store.searchState.results
  collapsed: boolean
}
const collapsedFiles = ref<Set<string>>(new Set())

const groupedResults = computed<FileGroup[]>(() => {
  const map = new Map<string, typeof store.searchState.results>()
  for (const r of store.searchState.results) {
    if (!map.has(r.file)) map.set(r.file, [])
    map.get(r.file)!.push(r)
  }
  return Array.from(map.entries()).map(([file, results]) => ({
    file,
    results,
    collapsed: collapsedFiles.value.has(file),
  }))
})

function toggleFileCollapse(file: string): void {
  const s = new Set(collapsedFiles.value)
  if (s.has(file)) s.delete(file)
  else s.add(file)
  collapsedFiles.value = s
}

/** Compute flat result index for a grouped item (for currentResultIndex highlight) */
function flatIndexOf(file: string, result: typeof store.searchState.results[0]): number {
  let idx = 0
  for (const r of store.searchState.results) {
    if (r.file === file && r.line === result.line) return idx
    idx++
  }
  return -1
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="visible" class="fixed inset-0 z-[200] flex flex-col" @keydown="onKD">
        <div class="absolute inset-0 bg-black/30" @click.self="emit('close')" />
        <div class="mx-auto mt-16 w-[780px] max-w-[92vw] bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded-lg shadow-2xl flex flex-col overflow-hidden relative z-10">
          <!-- Search row -->
          <div class="flex items-center gap-2 px-3 py-2.5 border-b border-[var(--color-ide-border)]">
            <Search :size="16" class="text-[var(--color-ide-text-dim)] shrink-0"/>
            <input ref="si" v-model="query" type="text" placeholder="搜索" class="flex-1 bg-transparent outline-none text-[13px] text-[var(--color-ide-text)] placeholder:[var(--color-ide-text-dim)]" @keydown="onKD"/>
            <div class="flex items-center gap-0.5">
              <!-- Filter toggles -->
              <button class="p-1 rounded transition-colors" :class="caseSensitive?'bg-[var(--color-ide-accent)]/20 text-[var(--color-ide-accent)]':'text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]'" title="区分大小写" @click="caseSensitive=!caseSensitive">
                <CaseSensitive :size="14"/>
              </button>
              <button class="p-1 rounded transition-colors" :class="wholeWord?'bg-[var(--color-ide-accent)]/20 text-[var(--color-ide-accent)]':'text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]'" title="全词匹配" @click="wholeWord=!wholeWord">
                <WholeWord :size="14"/>
              </button>
              <button class="p-1 rounded transition-colors" :class="useRegex?'bg-[var(--color-ide-accent)]/20 text-[var(--color-ide-accent)]':'text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]'" title="正则表达式" @click="useRegex=!useRegex">
                <Regex :size="14"/>
              </button>
              <button class="p-1 rounded transition-colors" :class="showFilterBar?'bg-[var(--color-ide-accent)]/20 text-[var(--color-ide-accent)]':'text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]'" title="过滤选项" @click="showFilterBar=!showFilterBar">
                <Filter :size="14"/>
              </button>
            </div>
            <button class="p-1 rounded hover:bg-[var(--color-ide-surface-hover)] transition-colors text-[var(--color-ide-text-dim)]" @click="emit('close')"><X :size="16"/></button>
          </div>

          <!-- Replace row -->
          <div class="flex items-center gap-2 px-3 py-2 border-b border-[var(--color-ide-border)]">
            <ArrowUpDown :size="14" class="text-[var(--color-ide-text-dim)]"/>
            <input v-model="rq" type="text" placeholder="替换为" class="flex-1 bg-[var(--color-ide-bg)] border border-[var(--color-ide-border)] rounded px-2 py-1 outline-none text-[12px] text-[var(--color-ide-text)] placeholder:[var(--color-ide-text-dim)]"/>
            <div class="flex items-center gap-1">
              <button class="px-2 py-1 text-[11px] rounded bg-[var(--color-ide-accent)]/10 text-[var(--color-ide-accent)] hover:bg-[var(--color-ide-accent)]/20 transition-colors disabled:opacity-30" :disabled="!rq||store.searchState.results.length===0" @click="replaceCurrent" title="替换当前">
                <Replace :size="12" class="inline mr-1"/>替换
              </button>
              <button class="px-2 py-1 text-[11px] rounded bg-[var(--color-ide-accent)] text-white hover:bg-[var(--color-ide-accent)]/80 transition-colors disabled:opacity-30" :disabled="!rq||store.searchState.results.length===0" @click="replaceAll" title="全部替换">
                全部替换
              </button>
            </div>
          </div>

          <!-- Filter bar (expandable) -->
          <div v-if="showFilterBar" class="flex items-center gap-3 px-3 py-2 border-b border-[var(--color-ide-border)] bg-[var(--color-ide-bg)]/50 text-[11px]">
            <label class="flex items-center gap-1.5 text-[var(--color-ide-text-dim)]">
              包含 <input v-model="includePattern" type="text" placeholder="*.ts,*.vue" class="w-40 bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded px-1.5 py-0.5 outline-none text-[var(--color-ide-text)] text-[11px]">
            </label>
            <label class="flex items-center gap-1.5 text-[var(--color-ide-text-dim)]">
              排除 <input v-model="excludePattern" type="text" placeholder="node_modules,.git" class="w-40 bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded px-1.5 py-0.5 outline-none text-[var(--color-ide-text)] text-[11px]">
            </label>
          </div>

          <!-- Results -->
          <div ref="rl" class="flex-1 overflow-y-auto min-h-[200px] max-h-[400px]">
            <div v-if="store.searchState.searching" class="flex items-center justify-center py-8 text-[var(--color-ide-text-dim)] text-[12px]"><RefreshCw :size="14" class="animate-spin mr-2"/> 搜索中...</div>
            <div v-else-if="query&&store.searchState.results.length===0" class="flex flex-col items-center justify-center py-8 text-[var(--color-ide-text-dim)] text-[12px]"><p>没有找到结果</p></div>
            <div v-else-if="store.searchState.results.length>0">
              <!-- Session 26: VSCode-style 文件分组树形搜索 -->
              <div v-for="group in groupedResults" :key="group.file" class="border-b border-[var(--color-ide-border)]/50">
                <!-- File header -->
                <div class="flex items-center gap-1.5 px-3 py-1.5 cursor-pointer transition-colors hover:bg-[var(--color-ide-surface-hover)] select-none"
                  @click="toggleFileCollapse(group.file)">
                  <ChevronRight v-if="group.collapsed" :size="12" class="text-[var(--color-ide-text-dim)] shrink-0" />
                  <ChevronDown v-else :size="12" class="text-[var(--color-ide-text-dim)] shrink-0" />
                  <FileText :size="13" class="text-[var(--color-ide-accent)]/70 shrink-0" />
                  <span class="text-[12px] text-[var(--color-ide-text)] font-medium truncate">{{ group.file.split(/[\\/]/).pop() }}</span>
                  <span class="text-[10px] text-[var(--color-ide-text-dim)]/60 truncate flex-1">{{ group.file }}</span>
                  <span class="text-[10px] text-[var(--color-ide-text-dim)] bg-[var(--color-ide-bg)]/80 px-1.5 py-0.5 rounded-full shrink-0 tabular-nums">{{ group.results.length }}</span>
                </div>
                <!-- Results (collapsible) -->
                <div v-if="!group.collapsed">
                  <div v-for="result in group.results" :key="result.file + ':' + result.line"
                    class="flex items-start gap-2 pl-9 pr-3 py-1.5 cursor-pointer transition-colors hover:bg-[var(--color-ide-surface-hover)]"
                    :class="{ 'bg-[var(--color-ide-surface-active)]': flatIndexOf(group.file, result) === store.searchState.currentResultIndex }"
                    @click="store.openFile(result.file); emit('close')">
                    <Hash :size="10" class="mt-0.5 text-[var(--color-ide-text-dim)]/50 shrink-0" />
                    <div class="flex-1 min-w-0">
                      <div class="flex items-center gap-1">
                        <span class="text-[10px] text-[var(--color-ide-text-dim)] tabular-nums shrink-0 w-12 text-right">L{{ result.line }}</span>
                        <span class="text-[11px] text-[var(--color-ide-text)] truncate font-mono" v-html="hl(result.lineText,result.matches)" />
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div v-else class="flex flex-col items-center justify-center py-12 text-[var(--color-ide-text-dim)] text-[12px]"><Search :size="24" class="mb-2 opacity-30"/><p>输入以开始搜索</p></div>
          </div>

          <!-- Footer -->
          <div v-if="store.searchState.results.length>0" class="px-3 py-1.5 border-t border-[var(--color-ide-border)] flex justify-between text-[10px] text-[var(--color-ide-text-dim)] bg-[var(--color-ide-bg)]/50">
            <span>{{ store.searchState.results.length }} 个结果</span>
            <div class="flex gap-1"><button class="px-2 py-0.5 rounded hover:bg-[var(--color-ide-surface-hover)]" @click="goToPrev">↑</button><button class="px-2 py-0.5 rounded hover:bg-[var(--color-ide-surface-hover)]" @click="goToNext">↓</button></div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
