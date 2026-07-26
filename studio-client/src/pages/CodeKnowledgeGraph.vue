<template>
  <div class="ckg-page">
    <div class="page-header">
      <h2>代码知识图谱</h2>
      <p class="subtitle">跨文件代码语义索引与搜索</p>
    </div>

    <div class="toolbar">
      <input v-model="query" placeholder="搜索代码符号 (函数/类/变量)..." class="search-input"
        @keyup.enter="doSearch" />
      <select v-model="filterType" class="select">
        <option value="">所有类型</option>
        <option value="function">函数</option>
        <option value="class">类</option>
        <option value="variable">变量</option>
        <option value="import">导入</option>
      </select>
      <button class="btn btn-primary" @click="doSearch" :disabled="!query.trim()">搜索</button>
      <button class="btn btn-outline" @click="fetchStats">统计</button>
    </div>

    <div v-if="stats" class="stats-bar">
      <span v-for="(v, k) in stats" :key="k" class="stat-item">
        <strong>{{ k }}:</strong> {{ v }}
      </span>
    </div>

    <div v-if="loading" class="loading">搜索中...</div>

    <div v-else-if="results.length > 0" class="results">
      <div v-for="r in results" :key="r.id ?? r.symbol" class="result-card">
        <div class="result-header">
          <span class="symbol-name">{{ r.name ?? r.symbol }}</span>
          <span class="symbol-type">{{ r.type ?? r.kind }}</span>
        </div>
        <div class="result-file">{{ r.file_path ?? r.file }}</div>
        <div v-if="r.signature" class="result-sig">{{ r.signature }}</div>
        <div v-if="r.doc" class="result-doc">{{ r.doc }}</div>
        <div class="result-meta">
          <span v-if="r.line">L{{ r.line }}</span>
          <span v-if="r.score !== undefined" class="score">相关度: {{ (r.score * 100).toFixed(0) }}%</span>
        </div>
      </div>
    </div>

    <div v-else-if="searched" class="empty">未找到匹配结果</div>

    <div class="index-section">
      <h3>索引管理</h3>
      <div class="index-actions">
        <button class="btn btn-primary" @click="triggerIndex">重建索引</button>
        <button class="btn btn-outline" @click="clearIndex">清除索引</button>
      </div>
      <div v-if="indexMsg" class="index-msg">{{ indexMsg }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ckgApi } from '@/api/ckg'

const query = ref('')
const filterType = ref('')
const results = ref<any[]>([])
const stats = ref<Record<string, any> | null>(null)
const loading = ref(false)
const searched = ref(false)
const indexMsg = ref('')

async function doSearch() {
  if (!query.value.trim()) return
  loading.value = true
  searched.value = false
  try {
    const res = await ckgApi.search({ q: query.value, type: filterType.value || undefined })
    results.value = res.data ?? res.results ?? res ?? []
    searched.value = true
  } finally {
    loading.value = false
  }
}

async function fetchStats() {
  try {
    const res = await ckgApi.getStats()
    stats.value = res
  } catch { /* ignore */ }
}

async function triggerIndex() {
  indexMsg.value = '索引重建中...'
  try {
    await ckgApi.index()
    indexMsg.value = '索引重建完成'
    await fetchStats()
  } catch (e: any) {
    indexMsg.value = `索引失败: ${e.message ?? e}`
  }
}

async function clearIndex() {
  if (!confirm('确认清除代码知识图谱索引？')) return
  await ckgApi.clear()
  stats.value = null
  indexMsg.value = '索引已清除'
}

onMounted(fetchStats)
</script>

<style scoped>
.ckg-page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 24px;
}

.page-header h2 { margin: 0; font-size: 22px; }
.subtitle { color: var(--color-ide-text-secondary); margin: 4px 0 16px; font-size: 14px; }

.toolbar {
  display: flex; gap: 8px; margin-bottom: 16px; align-items: center;
}
.search-input {
  flex: 1;
  padding: 6px 12px;
  border: 1px solid var(--color-ide-border);
  border-radius: 6px;
  background: var(--color-ide-bg-secondary);
  color: var(--color-ide-text-primary);
}
.select {
  padding: 6px 12px;
  border: 1px solid var(--color-ide-border);
  border-radius: 6px;
  background: var(--color-ide-bg-secondary);
  color: var(--color-ide-text-primary);
}

.stats-bar {
  display: flex; gap: 16px; padding: 10px 16px;
  background: var(--color-ide-bg-secondary);
  border-radius: 8px; margin-bottom: 16px;
  font-size: 13px;
}
.stat-item strong { margin-right: 4px; }

.results { display: grid; gap: 10px; }
.result-card {
  padding: 14px;
  border: 1px solid var(--color-ide-border);
  border-radius: 8px;
  background: var(--color-ide-bg-secondary);
}
.result-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 4px;
}
.symbol-name { font-weight: 700; font-size: 15px; color: var(--color-ide-accent); }
.symbol-type {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  background: var(--color-ide-bg-tertiary); color: var(--color-ide-text-secondary);
}
.result-file { font-size: 12px; color: var(--color-ide-text-secondary); margin: 4px 0; }
.result-sig {
  font-family: monospace; font-size: 12px; padding: 4px 8px;
  background: var(--color-ide-bg-tertiary); border-radius: 4px;
  margin: 6px 0;
}
.result-doc { font-size: 13px; color: var(--color-ide-text-secondary); margin-top: 4px; }
.result-meta {
  display: flex; gap: 12px; font-size: 12px; color: var(--color-ide-text-secondary);
  margin-top: 6px;
}

.index-section {
  margin-top: 32px; padding-top: 20px;
  border-top: 1px solid var(--color-ide-border);
}
.index-section h3 { margin: 0 0 12px; font-size: 16px; }
.index-actions { display: flex; gap: 8px; }
.index-msg { margin-top: 8px; font-size: 13px; color: var(--color-ide-text-secondary); }

.loading, .empty { text-align: center; padding: 40px; color: var(--color-ide-text-secondary); }

.btn {
  padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer;
  font-size: 13px; background: var(--color-ide-bg-tertiary);
  color: var(--color-ide-text-primary);
  transition: opacity 0.15s;
}
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-outline { border: 1px solid var(--color-ide-border); background: transparent; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
