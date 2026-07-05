// ============================================
// Search Store — Tauri + Backend API fallback
// Session 51: Backend API fallback for web mode
// ============================================
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { SearchState } from '@/types/ide'
import { isTauriEnv } from './shared'
import { useFileTreeStore } from './useFileTreeStore'

function getApiBase(): string { return (window as any).__apiBaseUrl || '/api/v1' }

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
  /** Session 51: 后端 API 也支持搜索 → 始终可用 */
  const searchAvailable = ref(true)

  function toggleGlobalSearch(): void {
    showGlobalSearch.value = !showGlobalSearch.value
    if (showGlobalSearch.value) searchState.value.results = []
  }

  /** Session 51: Tauri → Backend API fallback */
  async function executeSearch(): Promise<void> {
    const q = searchState.value.query.trim()
    if (!q) return
    searchState.value.searching = true
    searchState.value.results = []

    if (isTauriEnv()) {
      await _searchViaTauri(q)
    } else {
      await _searchViaApi(q)
    }
    searchState.value.searching = false
  }

  async function _searchViaTauri(q: string): Promise<void> {
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const workspaceRoot = useFileTreeStore().workspaceRoot
      const res: any = await invoke('global_search', {
        request: {
          path: workspaceRoot || '.', query: q,
          includePatterns: _parsePatterns(searchState.value.includePattern),
          excludePatterns: _parsePatterns(searchState.value.excludePattern),
          useRegex: searchState.value.useRegex,
          caseSensitive: searchState.value.caseSensitive,
          wholeWord: searchState.value.wholeWord,
        },
      })
      searchState.value.results = (res?.matches || []).map((m: any) => ({
        filePath: m.file, line: m.line, column: m.column,
        matchText: m.matchText, matchLength: m.matchLength,
        previewBefore: m.previewBefore, previewAfter: m.previewAfter,
      }))
    } catch (e) { console.warn('[Search] Tauri search failed:', e) }
  }

  /** Session 51: Backend API 文本搜索 */
  async function _searchViaApi(q: string): Promise<void> {
    try {
      const root = useFileTreeStore().workspaceRoot || '.'
      const resp = await fetch(`${getApiBase()}/system/search/text`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: q, path: root,
          include_patterns: _parsePatterns(searchState.value.includePattern),
          exclude_patterns: _parsePatterns(searchState.value.excludePattern),
          use_regex: searchState.value.useRegex,
          case_sensitive: searchState.value.caseSensitive,
          whole_word: searchState.value.wholeWord,
          max_results: 200,
        }),
      })
      if (resp.ok) {
        const data = await resp.json()
        searchState.value.results = (data.results || []).map((m: any) => ({
          filePath: m.file, line: m.line, column: m.column,
          matchText: m.match_text, matchLength: m.match_length,
          previewBefore: m.line_text?.slice(0, Math.max(0, m.column - 1)) || '',
          previewAfter: '',
        }))
      }
    } catch (e) { console.warn('[Search] API search failed:', e) }
  }

  /** Session 51: Tauri → Backend API fallback */
  async function executeReplace(): Promise<void> {
    const q = searchState.value.query.trim()
    const r = searchState.value.replaceQuery
    if (!q) return
    searchState.value.searching = true

    if (isTauriEnv()) {
      try {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('global_replace', {
          request: {
            path: useFileTreeStore().workspaceRoot || '.', query: q, replaceWith: r,
            includePatterns: _parsePatterns(searchState.value.includePattern),
            excludePatterns: _parsePatterns(searchState.value.excludePattern),
            useRegex: searchState.value.useRegex,
            caseSensitive: searchState.value.caseSensitive,
            wholeWord: searchState.value.wholeWord,
          },
        })
      } catch (e) { console.warn('[Search] Tauri replace failed:', e) }
    } else {
      try {
        await fetch(`${getApiBase()}/system/search/replace`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            query: q, replace_with: r,
            path: useFileTreeStore().workspaceRoot || '.',
            include_patterns: _parsePatterns(searchState.value.includePattern),
            exclude_patterns: _parsePatterns(searchState.value.excludePattern),
            use_regex: searchState.value.useRegex,
            case_sensitive: searchState.value.caseSensitive,
            whole_word: searchState.value.wholeWord,
          }),
        })
      } catch (e) { console.warn('[Search] API replace failed:', e) }
    }
    searchState.value.searching = false
  }

  async function replaceInFile(filePath: string, search: string, replace: string, line?: number): Promise<boolean> {
    if (isTauriEnv()) {
      try {
        const { invoke } = await import('@tauri-apps/api/core')
        const res: any = await invoke('replace_in_file', { path: filePath, search, replace, line })
        return res?.replaced ?? false
      } catch { return false }
    }
    try {
      const resp = await fetch(`${getApiBase()}/system/search/replace`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: search, replace_with: replace, file_path: filePath, line }),
      })
      const data = await resp.json()
      return data.replaced > 0
    } catch { return false }
  }

  function _parsePatterns(pattern: string): string[] | null {
    return pattern ? pattern.split(',').map(s => s.trim()).filter(Boolean) : null
  }

  return { searchState, showGlobalSearch, searchAvailable, toggleGlobalSearch, executeSearch, executeReplace, replaceInFile }
})
