<template>
  <div class="global-search-page">
    <div class="page-header">
      <h2>全局搜索</h2>
      <p class="subtitle">跨文件全文搜索、文件查找、批量替换</p>
    </div>

    <!-- 搜索栏 -->
    <div class="search-bar">
      <div class="search-row">
        <select v-model="searchType" class="input input-sm">
          <option value="text">文本搜索</option>
          <option value="file">文件查找</option>
        </select>
        <input v-model="query" placeholder="输入搜索内容..." class="input" style="flex:1" @keyup.enter="doSearch" />
        <input v-model="filePattern" placeholder="文件模式 (如 *.py)" class="input input-sm" />
        <input v-model="dirFilter" placeholder="目录限制 (可选)" class="input input-sm" />
        <input v-model.number="maxResults" type="number" placeholder="最多结果" class="input input-xs" />
        <button class="btn btn-primary" @click="doSearch" :disabled="searching">
          {{ searching ? '搜索中...' : '搜索' }}
        </button>
      </div>
      <div class="engine-row">
        <span class="engine-label">搜索引擎：</span>
        <label v-for="e in engines" :key="e" class="engine-option">
          <input type="radio" v-model="searchEngine" :value="e" />
          {{ e }}
        </label>
        <label class="opt-check"><input type="checkbox" v-model="caseSensitive" /> 区分大小写</label>
        <label class="opt-check"><input type="checkbox" v-model="regexMode" /> 正则</label>
        <label class="opt-check"><input type="checkbox" v-model="wholeWord" /> 全词</label>
      </div>
    </div>

    <!-- 替换面板 -->
    <div v-if="searchType === 'text'" class="replace-panel" :class="{ active: showReplace }">
      <button class="btn btn-sm" @click="showReplace = !showReplace">
        {{ showReplace ? '关闭替换' : '展开替换' }}
      </button>
      <template v-if="showReplace">
        <input v-model="replaceText" placeholder="替换为..." class="input" />
        <button class="btn btn-primary btn-sm" @click="doReplace" :disabled="replacing">
          {{ replacing ? '替换中...' : '全部替换' }}
        </button>
      </template>
    </div>

    <!-- 结果列表 -->
    <div class="results-area">
      <div v-if="searching" class="loading">搜索中...</div>
      <div v-else-if="results.length === 0 && searched" class="empty">未找到结果</div>
      <div v-else-if="results.length === 0 && !searched" class="empty hint">输入关键词开始搜索</div>

      <div v-if="searchType === 'text'">
        <div v-for="(file, fi) in groupedResults" :key="fi" class="file-group">
          <div class="file-path" @click="toggleFile(fi)">
            <span class="toggle-icon">{{ expandedFiles.has(fi) ? '▼' : '▶' }}</span>
            <span class="file-name">{{ file.path }}</span>
            <span class="match-count">{{ file.matches.length }} 处匹配</span>
          </div>
          <div v-if="expandedFiles.has(fi)" class="matches">
            <div v-for="(m, mi) in file.matches" :key="mi" class="match-row">
              <span class="match-line-num">{{ m.line ?? m.line_number ?? '—' }}</span>
              <span class="match-content" v-html="highlightMatch(m.line_text ?? m.content ?? m.line ?? '', query)"></span>
            </div>
          </div>
        </div>
      </div>

      <div v-if="searchType === 'file'">
        <div v-for="(f, i) in results as any[]" :key="i" class="file-result-row">
          <span :class="['file-icon', f.type === 'directory' ? 'dir' : 'file']">
            {{ f.type === 'directory' ? '📁' : '📄' }}
          </span>
          <span class="file-path-text">{{ f.path }}</span>
          <span class="file-size">{{ formatSize(f.size_bytes) }}</span>
          <span class="file-time">{{ formatTime(f.modified_at) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { searchApi } from '@/api/search'
import type { TextSearchParams, ReplaceParams } from '@/api/search'

const query = ref('')
const replaceText = ref('')
const searchType = ref('text')
const filePattern = ref('')
const dirFilter = ref('')
const maxResults = ref(50)
const caseSensitive = ref(false)
const regexMode = ref(false)
const wholeWord = ref(false)
const searchEngine = ref('default')
const showReplace = ref(false)

const engines = ref<string[]>([])
const results = ref<any[]>([])
const searched = ref(false)
const searching = ref(false)
const replacing = ref(false)
const expandedFiles = ref(new Set<number>())

function highlightMatch(text: string, keyword: string) {
  if (!keyword || !text) return text
  const escaped = keyword.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const re = new RegExp(`(${escaped})`, 'gi')
  return text.replace(re, '<mark>$1</mark>')
}

const groupedResults = computed(() => {
  if (searchType.value !== 'text') return []
  // 后端 SearchMatch.file 是文件路径，先尝试 .file，再回退 .file_path / .path
  const map = new Map<string, { path: string; matches: any[] }>()
  for (const r of results.value as any[]) {
    const fp = r.file ?? r.file_path ?? r.path ?? 'unknown'
    if (!map.has(fp)) map.set(fp, { path: fp, matches: [] })
    map.get(fp)!.matches.push(r)
  }
  return Array.from(map.values())
})

function formatSize(bytes?: number) {
  if (!bytes) return '—'
  return bytes >= 1024 * 1024 ? (bytes / (1024 * 1024)).toFixed(1) + ' MB' :
         bytes >= 1024 ? (bytes / 1024).toFixed(1) + ' KB' : bytes + ' B'
}

function formatTime(ts?: number) {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString()
}

function toggleFile(i: number) {
  if (expandedFiles.value.has(i)) {
    expandedFiles.value.delete(i)
  } else {
    expandedFiles.value.add(i)
  }
  // 触发响应式
  expandedFiles.value = new Set(expandedFiles.value)
}

async function fetchEngines() {
  try {
    const res = await searchApi.getEngines()
    const engDict = res.data?.engines ?? {}
    if (typeof engDict === 'object' && !Array.isArray(engDict)) {
      engines.value = Object.keys(engDict).filter(k => (engDict as Record<string, { available?: boolean }>)[k]?.available !== false)
    }
    if (engines.value.length === 0) engines.value = ['default']
  } catch { /* empty */ }
}

async function doSearch() {
  if (!query.value.trim()) return
  searching.value = true
  searched.value = true
  expandedFiles.value.clear()
  try {
    if (searchType.value === 'text') {
      const params: TextSearchParams = {
        query: query.value,
        max_results: maxResults.value,
        file_pattern: filePattern.value || undefined,
        directory: dirFilter.value || undefined,
        case_sensitive: caseSensitive.value,
        regex: regexMode.value,
        whole_word: wholeWord.value,
        engine: searchEngine.value !== 'default' ? searchEngine.value : undefined,
      }
      const res = await searchApi.textSearch(params)
      results.value = res.data?.matches ?? res.data?.results ?? res.data ?? []
    } else {
      const res = await searchApi.fileSearch({
        query: query.value,
        max_results: maxResults.value,
        directory: dirFilter.value || undefined,
        case_sensitive: caseSensitive.value,
      })
      results.value = res.data?.files ?? res.data?.results ?? res.data ?? []
    }
  } finally {
    searching.value = false
  }
}

async function doReplace() {
  if (!query.value.trim() || !replaceText.value) return
  replacing.value = true
  try {
    const params: ReplaceParams = {
      find: query.value,
      replace: replaceText.value,
      file_pattern: filePattern.value || undefined,
      directory: dirFilter.value || undefined,
      case_sensitive: caseSensitive.value,
      regex: regexMode.value,
      whole_word: wholeWord.value,
    }
    const res = await searchApi.replace(params)
    const count = res.data?.replaced ?? res.data?.count ?? 0
    alert(`替换完成：${count} 处`)
    doSearch()
  } finally {
    replacing.value = false
  }
}

onMounted(() => fetchEngines())
</script>

<style scoped>
.global-search-page { padding: 24px; }
.page-header { margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 20px; }
.subtitle { color: var(--color-ide-fg-secondary); margin: 4px 0 0; font-size: 13px; }

.search-bar { border: 1px solid var(--color-ide-border); border-radius: 10px; padding: 16px; margin-bottom: 16px; }
.search-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 10px; }
.engine-row { display: flex; align-items: center; gap: 12px; font-size: 12px; color: var(--color-ide-fg-secondary); flex-wrap: wrap; }
.engine-label { font-weight: 500; }
.engine-option { display: flex; align-items: center; gap: 4px; cursor: pointer; }
.opt-check { display: flex; align-items: center; gap: 3px; margin-left: 4px; }

.replace-panel { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; }
.replace-panel:not(.active) { margin-bottom: 8px; }
.replace-panel.active { padding: 10px; border: 1px solid var(--color-ide-accent); border-radius: 8px; }

.results-area { min-height: 200px; }

.file-group { border: 1px solid var(--color-ide-border); border-radius: 8px; margin-bottom: 8px; overflow: hidden; }
.file-path { display: flex; align-items: center; gap: 8px; padding: 10px 14px; background: var(--color-ide-bg-secondary); cursor: pointer; font-size: 13px; }
.file-path:hover { background: var(--color-ide-bg-hover, rgba(128,128,128,0.1)); }
.file-name { font-weight: 500; flex: 1; }
.match-count { font-size: 11px; color: var(--color-ide-fg-secondary); }
.toggle-icon { font-size: 10px; width: 14px; }

.matches { padding: 8px 14px; }
.match-row { display: flex; gap: 10px; padding: 4px 0; font-size: 13px; border-bottom: 1px solid var(--color-ide-border); }
.match-row:last-child { border: none; }
.match-line-num { color: var(--color-ide-fg-secondary); min-width: 36px; text-align: right; font-family: monospace; font-size: 12px; }
.match-content { flex: 1; white-space: pre-wrap; word-break: break-all; }
.match-content :deep(mark) { background: #d4a72c44; color: inherit; padding: 0 2px; border-radius: 2px; }

.file-result-row { display: flex; align-items: center; gap: 10px; padding: 8px 14px; border-bottom: 1px solid var(--color-ide-border); font-size: 13px; }
.file-result-row:last-child { border: none; }
.file-icon { width: 24px; text-align: center; }
.file-path-text { flex: 1; font-family: monospace; font-size: 12px; }
.file-size { color: var(--color-ide-fg-secondary); font-size: 11px; min-width: 60px; text-align: right; }
.file-time { color: var(--color-ide-fg-secondary); font-size: 11px; min-width: 140px; }

.loading, .empty { padding: 48px 0; text-align: center; color: var(--color-ide-fg-secondary); }
.hint { font-style: italic; }

.input { background: var(--color-ide-bg-secondary); border: 1px solid var(--color-ide-border); border-radius: 6px; padding: 6px 10px; font-size: 13px; color: var(--color-ide-fg); }
.input-sm { width: 110px; }
.input-xs { width: 80px; }
.btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid var(--color-ide-border); background: var(--color-ide-bg); color: var(--color-ide-fg); }
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--color-ide-accent, #4fc1ff); color: #fff; border-color: var(--color-ide-accent, #4fc1ff); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
</style>
