// ============================================
// Search Store — real Tauri global search
// ============================================
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { SearchState } from '@/types/ide'
import { isTauriEnv } from './shared'
import { useFileTreeStore } from './useFileTreeStore'

export const useSearchStore = defineStore('search', () => {
  const searchState = ref<SearchState>({
    query: '',
    replaceQuery: '',
    includePattern: '*.ts,*.vue,*.py,*.json',
    excludePattern: 'node_modules,dist,.git',
    results: [],
    searching: false,
    caseSensitive: false,
    wholeWord: false,
    useRegex: false,
    currentResultIndex: -1,
  })
  const showGlobalSearch = ref(false)

  function toggleGlobalSearch(): void {
    showGlobalSearch.value = !showGlobalSearch.value
    if (showGlobalSearch.value) searchState.value.results = []
  }

  /** Execute global search via Tauri */
  async function executeSearch(): Promise<void> {
    const q = searchState.value.query.trim()
    if (!q) return

    searchState.value.searching = true
    searchState.value.results = []

    try {
      if (isTauriEnv()) {
        const { invoke } = await import('@tauri-apps/api/core')
        const workspaceRoot = useFileTreeStore().workspaceRoot
        const res: any = await invoke('global_search', {
          request: {
            path: workspaceRoot || '.',
            query: q,
            includePatterns: searchState.value.includePattern
              ? searchState.value.includePattern.split(',').map(s => s.trim()).filter(Boolean)
              : null,
            excludePatterns: searchState.value.excludePattern
              ? searchState.value.excludePattern.split(',').map(s => s.trim()).filter(Boolean)
              : null,
            useRegex: searchState.value.useRegex,
            caseSensitive: searchState.value.caseSensitive,
            wholeWord: searchState.value.wholeWord,
          },
        })
        searchState.value.results = (res?.matches || []).map((m: any) => ({
          filePath: m.file,
          line: m.line,
          column: m.column,
          matchText: m.matchText,
          matchLength: m.matchLength,
          previewBefore: m.previewBefore,
          previewAfter: m.previewAfter,
        }))
      }
    } catch (e) {
      console.warn('[Search] global_search failed:', e)
    } finally {
      searchState.value.searching = false
    }
  }

  /** Replace all matches */
  async function executeReplace(): Promise<void> {
    const q = searchState.value.query.trim()
    const replace = searchState.value.replaceQuery
    if (!q) return

    try {
      if (isTauriEnv()) {
        const { invoke } = await import('@tauri-apps/api/core')
        const workspaceRoot = useFileTreeStore().workspaceRoot
        await invoke('global_replace', {
          request: {
            path: workspaceRoot || '.',
            query: q,
            replaceWith: replace,
            includePatterns: searchState.value.includePattern
              ? searchState.value.includePattern.split(',').map(s => s.trim()).filter(Boolean)
              : null,
            excludePatterns: searchState.value.excludePattern
              ? searchState.value.excludePattern.split(',').map(s => s.trim()).filter(Boolean)
              : null,
            useRegex: searchState.value.useRegex,
            caseSensitive: searchState.value.caseSensitive,
            wholeWord: searchState.value.wholeWord,
          },
        })
      }
    } catch (e) {
      console.warn('[Search] replace failed:', e)
    }
  }

  return { searchState, showGlobalSearch, toggleGlobalSearch, executeSearch, executeReplace }
})
