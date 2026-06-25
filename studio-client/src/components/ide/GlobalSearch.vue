<script setup lang="ts">/** IDE — Global Search & Replace */
import { ref, computed, watch, nextTick } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { Search, ArrowUpDown, X, ChevronRight, RefreshCw } from 'lucide-vue-next'

defineProps<{ visible: boolean }>()
const emit = defineEmits<(e:'close')=>void>()
const store = useIDEStore(), si = ref<HTMLInputElement|null>(null), rl = ref<HTMLDivElement|null>(null)
const query = computed({ get:()=>store.searchState.query, set:(v:string)=>store.searchState.query=v })
const rq = computed({ get:()=>store.searchState.replaceQuery, set:(v:string)=>store.searchState.replaceQuery=v })

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
      // Search files by name
      const matchedFiles: string[] = await invoke('search_files', {
        request: {
          path: store.workspaceRoot,
          pattern: query.value,
          excludePatterns: ['node_modules', '.git', 'dist', '__pycache__', 'target'],
          caseSensitive: store.searchState.caseSensitive,
          maxResults: 100,
        },
      })
      // Also search content within files
      const contentResults: any[] = await invoke('search_in_file', {
        request: {
          path: store.workspaceRoot,
          pattern: query.value,
          excludePatterns: ['node_modules', '.git', 'dist', '__pycache__', 'target'],
          caseSensitive: store.searchState.caseSensitive,
          maxResults: 50,
        },
      })

      // Merge results
      const fileSet = new Set<string>()
      const results: any[] = []

      for (const f of matchedFiles.slice(0, 20)) {
        if (!fileSet.has(f)) {
          fileSet.add(f)
          results.push({
            file: f, line: 1, column: 1,
            lineText: f.replace(store.workspaceRoot, ''),
            matchLength: query.value.length,
            matches: [{ start: 0, end: query.value.length }],
          })
        }
      }

      for (const r of contentResults) {
        const key = `${r.file}:${r.line}`
        if (!fileSet.has(key)) {
          fileSet.add(key)
          results.push({
            file: r.file, line: r.line, column: r.column,
            lineText: r.text,
            matchLength: r.matchLength ?? query.value.length,
            matches: [{ start: r.column - 1, end: r.column - 1 + (r.matchLength ?? query.value.length) }],
          })
        }
        if (results.length >= 30) break
      }

      store.searchState.results = results.slice(0, 30)
    } catch (e) {
      console.warn('[Search] Tauri search failed:', e)
    }
  } else {
    // Web fallback: basic mock
    await new Promise(r => setTimeout(r, 300))
    store.searchState.results = []
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
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="visible" class="fixed inset-0 z-[200] flex flex-col" @keydown="onKD">
        <div class="absolute inset-0 bg-black/30" @click.self="emit('close')" />
        <div class="mx-auto mt-16 w-[720px] max-w-[90vw] bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded-lg shadow-2xl flex flex-col overflow-hidden relative z-10">
          <div class="flex items-center gap-2 px-3 py-2.5 border-b border-[var(--color-ide-border)]">
            <Search :size="16" class="text-[var(--color-ide-text-dim)] shrink-0"/>
            <input ref="si" v-model="query" type="text" placeholder="搜索文件内容..." class="flex-1 bg-transparent outline-none text-[13px] text-[var(--color-ide-text)] placeholder:[var(--color-ide-text-dim)]" @keydown="onKD"/>
            <button class="p-1 rounded hover:bg-white/5 transition-colors text-[var(--color-ide-text-dim)]" @click="emit('close')"><X :size="16"/></button>
          </div>
          <div class="flex items-center gap-2 px-3 py-2 border-b border-[var(--color-ide-border)]">
            <ArrowUpDown :size="14" class="text-[var(--color-ide-text-dim)]"/>
            <input v-model="rq" type="text" placeholder="替换为" class="flex-1 bg-[var(--color-ide-bg)] border border-[var(--color-ide-border)] rounded px-2 py-1 outline-none text-[12px] text-[var(--color-ide-text)] placeholder:[var(--color-ide-text-dim)]"/>
          </div>
          <div ref="rl" class="flex-1 overflow-y-auto min-h-[200px] max-h-[400px]">
            <div v-if="store.searchState.searching" class="flex items-center justify-center py-8 text-[var(--color-ide-text-dim)] text-[12px]"><RefreshCw :size="14" class="animate-spin mr-2"/> 搜索中...</div>
            <div v-else-if="query&&store.searchState.results.length===0" class="flex flex-col items-center justify-center py-8 text-[var(--color-ide-text-dim)] text-[12px]"><p>没有找到结果</p></div>
            <div v-else-if="store.searchState.results.length>0">
              <div v-for="(result,idx) in store.searchState.results" :key="idx"
                class="flex items-start gap-2 px-3 py-2 border-b border-[var(--color-ide-border)]/50 cursor-pointer transition-colors hover:bg-[var(--color-ide-surface-hover)]"
                :class="{ 'bg-[var(--color-ide-surface-active)]': idx === store.searchState.currentResultIndex }"
                @click="store.openFile(result.file); emit('close')">
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-1 text-[11px]">
                    <span class="text-[var(--color-ide-text)] truncate">{{ result.file.split('/').pop() }}</span>
                    <ChevronRight :size="10" class="opacity-40"/>
                    <span class="text-[var(--color-ide-text-dim)] opacity-50 truncate">{{ result.file }}</span>
                    <span class="text-[var(--color-ide-text-dim)] ml-auto shrink-0">{{ result.line }} 行</span>
                  </div>
                  <div class="text-[11px] text-[var(--color-ide-text-dim)] truncate mt-0.5 font-mono" v-html="hl(result.lineText,result.matches)" />
                </div>
              </div>
            </div>
            <div v-else class="flex flex-col items-center justify-center py-12 text-[var(--color-ide-text-dim)] text-[12px]"><Search :size="24" class="mb-2 opacity-30"/><p>输入以开始搜索</p></div>
          </div>
          <div v-if="store.searchState.results.length>0" class="px-3 py-1.5 border-t border-[var(--color-ide-border)] flex justify-between text-[10px] text-[var(--color-ide-text-dim)] bg-[var(--color-ide-bg)]/50">
            <span>{{ store.searchState.results.length }} 个结果</span>
            <div class="flex gap-1"><button class="px-2 py-0.5 rounded hover:bg-white/5" @click="goToPrev">↑</button><button class="px-2 py-0.5 rounded hover:bg-white/5" @click="goToNext">↓</button></div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
