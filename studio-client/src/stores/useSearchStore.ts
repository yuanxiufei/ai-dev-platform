// ============================================
// Search Store — global search state
// ============================================
import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { SearchState } from '@/types/ide'

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
  }

  return { searchState, showGlobalSearch, toggleGlobalSearch }
})
