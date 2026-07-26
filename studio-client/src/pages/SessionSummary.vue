<template>
  <div class="session-summary-page">
    <div class="page-header">
      <h2>会话汇总</h2>
      <p class="subtitle">Agent 会话内容汇总、压缩与 Markdown 导出</p>
    </div>

    <div class="toolbar">
      <input v-model="search" placeholder="搜索会话..." class="search-input" />
      <button class="btn btn-primary" @click="fetchList">刷新</button>
      <button class="btn btn-outline" @click="clearAll" :disabled="!sessions.length">清除所有</button>
    </div>

    <div v-if="loading" class="loading">加载中...</div>

    <div v-else-if="sessions.length === 0" class="empty">
      暂无会话记录
    </div>

    <div v-else class="session-list">
      <div
        v-for="s in filteredSessions"
        :key="s.session_id"
        class="session-card"
        :class="{ active: selectedId === s.session_id }"
        @click="selectSession(s)"
      >
        <div class="card-header">
          <span class="session-id">{{ s.session_id }}</span>
          <span class="session-date">{{ formatDate(s.updated_at) }}</span>
        </div>
        <div class="card-body">
          <span class="badge">{{ s.message_count ?? 0 }} 条消息</span>
          <span class="badge" v-if="s.total_tokens">~{{ s.total_tokens }} tokens</span>
        </div>
      </div>
    </div>

    <!-- 详情面板 -->
    <div v-if="selected" class="detail-panel">
      <div class="detail-toolbar">
        <h3>{{ selected.session_id }}</h3>
        <div class="detail-actions">
          <button class="btn btn-sm" @click="fetchSummary">摘要</button>
          <button class="btn btn-sm" @click="fetchCompact">压缩</button>
          <button class="btn btn-sm btn-primary" @click="fetchMarkdown">Markdown</button>
          <button class="btn btn-sm btn-outline" @click="closeDetail">关闭</button>
        </div>
      </div>

      <div v-if="detailLoading" class="loading-sm">加载中...</div>

      <div v-else-if="detailContent" class="detail-content">
        <pre v-if="detailType === 'markdown' || detailType === 'compact'" class="md-preview">{{ detailContent }}</pre>
        <div v-else class="summary-block">
          <div v-if="detailType === 'summary' && typeof detailContent === 'object'">
            <div v-for="(val, key) in detailContent" :key="key" class="summary-item">
              <strong>{{ key }}:</strong>
              <span>{{ val }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { lakeviewApi, type SessionItem } from '@/api/lakeview'

const sessions = ref<SessionItem[]>([])
const selectedId = ref<string | null>(null)
const selected = ref<SessionItem | null>(null)
const search = ref('')
const loading = ref(false)
const detailLoading = ref(false)
const detailContent = ref<any>(null)
const detailType = ref('')

const filteredSessions = computed(() => {
  if (!search.value) return sessions.value
  const q = search.value.toLowerCase()
  return sessions.value.filter(s => s.session_id?.toLowerCase().includes(q))
})

function formatDate(ts?: string) {
  if (!ts) return '-'
  return new Date(ts).toLocaleString()
}

async function fetchList() {
  loading.value = true
  try {
    const res = await lakeviewApi.listSessions()
    sessions.value = res.data ?? []
  } finally {
    loading.value = false
  }
}

function selectSession(s: SessionItem) {
  selectedId.value = s.session_id
  selected.value = s
  detailContent.value = null
  detailType.value = ''
}

function closeDetail() {
  selectedId.value = null
  selected.value = null
  detailContent.value = null
}

async function fetchSummary() {
  if (!selected.value) return
  detailLoading.value = true
  try {
    const res = await lakeviewApi.getSummary(selected.value.session_id)
    detailContent.value = res
    detailType.value = 'summary'
  } finally {
    detailLoading.value = false
  }
}

async function fetchCompact() {
  if (!selected.value) return
  detailLoading.value = true
  try {
    const res = await lakeviewApi.getCompact(selected.value.session_id)
    detailContent.value = res?.compact_text ?? res
    detailType.value = 'compact'
  } finally {
    detailLoading.value = false
  }
}

async function fetchMarkdown() {
  if (!selected.value) return
  detailLoading.value = true
  try {
    const res = await lakeviewApi.getMarkdown(selected.value.session_id)
    detailContent.value = res?.markdown ?? res
    detailType.value = 'markdown'
  } finally {
    detailLoading.value = false
  }
}

async function clearAll() {
  if (!confirm('确认清除所有会话记录？')) return
  await lakeviewApi.clearSessions()
  sessions.value = []
  closeDetail()
}

onMounted(fetchList)
</script>

<style scoped>
.session-summary-page {
  max-width: 1100px;
  margin: 0 auto;
  padding: 24px;
}

.page-header h2 { margin: 0; font-size: 22px; }
.subtitle { color: var(--color-ide-text-secondary); margin: 4px 0 16px; font-size: 14px; }

.toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.search-input {
  flex: 1;
  padding: 6px 12px;
  border: 1px solid var(--color-ide-border);
  border-radius: 6px;
  background: var(--color-ide-bg-secondary);
  color: var(--color-ide-text-primary);
}

.session-list {
  display: grid;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
}
.session-card {
  padding: 12px;
  border: 1px solid var(--color-ide-border);
  border-radius: 8px;
  cursor: pointer;
  background: var(--color-ide-bg-secondary);
  transition: border-color 0.15s;
}
.session-card:hover { border-color: var(--color-ide-accent); }
.session-card.active { border-color: var(--color-ide-accent); background: var(--color-ide-bg-active); }
.card-header {
  display: flex; justify-content: space-between;
  font-weight: 600; font-size: 13px;
}
.card-body { display: flex; gap: 8px; margin-top: 6px; }
.badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--color-ide-bg-tertiary);
  color: var(--color-ide-text-secondary);
}

.detail-panel {
  margin-top: 20px;
  border: 1px solid var(--color-ide-border);
  border-radius: 8px;
  padding: 16px;
  background: var(--color-ide-bg-secondary);
}
.detail-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px;
}
.detail-toolbar h3 { margin: 0; font-size: 15px; }
.detail-actions { display: flex; gap: 6px; }

.md-preview {
  background: var(--color-ide-bg-tertiary);
  padding: 16px;
  border-radius: 6px;
  font-size: 13px;
  white-space: pre-wrap;
  max-height: 500px;
  overflow: auto;
  color: var(--color-ide-text-primary);
}
.summary-item {
  padding: 6px 0;
  border-bottom: 1px solid var(--color-ide-border);
  font-size: 13px;
}
.summary-item strong { margin-right: 8px; }
.loading, .empty { text-align: center; padding: 40px; color: var(--color-ide-text-secondary); }
.loading-sm { padding: 20px; text-align: center; }

.btn {
  padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer;
  font-size: 13px; background: var(--color-ide-bg-tertiary);
  color: var(--color-ide-text-primary);
  transition: opacity 0.15s;
}
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-outline { border: 1px solid var(--color-ide-border); background: transparent; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
