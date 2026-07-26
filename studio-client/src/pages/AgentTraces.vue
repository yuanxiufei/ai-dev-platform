<script setup lang="ts">
/**
 * Agent 调用追踪列表页
 * 展示所有 Agent 执行追踪记录，支持筛选、分页、统计概览
 */
import { ref, reactive, onMounted, computed } from "vue"
import { useRouter } from "vue-router"
import {
  Search, Trash2, Eye, RefreshCw, Clock, CheckCircle,
  XCircle, PlayCircle, Monitor, BarChart3, Zap,
} from "lucide-vue-next"
import {
  listTraces, deleteTrace, getTraceStats,
  type TraceSummary, type TraceStats,
} from "@/api/traces"

const router = useRouter()

// ── 状态 ──
const traces = ref<TraceSummary[]>([])
const stats = ref<TraceStats | null>(null)
const loading = ref(false)
const filters = reactive({
  agent_name: "",
  model_name: "",
  status: "",
  page: 1,
  size: 20,
})
const total = ref(0)
const selectedIds = ref<Set<string>>(new Set())

// ── 计算属性 ──
const totalPages = computed(() => Math.max(1, Math.ceil(total.value / filters.size)))

const statusOptions = [
  { value: "", label: "全部状态" },
  { value: "success", label: "成功" },
  { value: "failed", label: "失败" },
  { value: "running", label: "运行中" },
  { value: "cancelled", label: "已取消" },
]

// ── 方法 ──
async function fetchTraces() {
  loading.value = true
  try {
    const res = await listTraces({
      page: filters.page,
      size: filters.size,
      agent_name: filters.agent_name || undefined,
      model_name: filters.model_name || undefined,
      status: filters.status || undefined,
    })
    traces.value = res.data
    total.value = res.total
  } catch (e) {
    console.error("获取追踪列表失败:", e)
  } finally {
    loading.value = false
  }
}

async function fetchStats() {
  try {
    stats.value = await getTraceStats()
  } catch (e) {
    console.error("获取统计失败:", e)
  }
}

function onSearch() {
  filters.page = 1
  fetchTraces()
}

function onPageChange(page: number) {
  filters.page = page
  fetchTraces()
}

function goDetail(traceId: string) {
  router.push(`/traces/${encodeURIComponent(traceId)}`)
}

async function onDelete(traceId: string) {
  if (!confirm("确认删除该追踪记录？")) return
  try {
    await deleteTrace(traceId)
    fetchTraces()
    fetchStats()
  } catch (e) {
    console.error("删除失败:", e)
  }
}

function toggleSelect(traceId: string) {
  const s = new Set(selectedIds.value)
  if (s.has(traceId)) s.delete(traceId)
  else s.add(traceId)
  selectedIds.value = s
}

function toggleAll() {
  if (selectedIds.value.size === traces.value.length) {
    selectedIds.value = new Set()
  } else {
    selectedIds.value = new Set(traces.value.map(t => t.trace_id))
  }
}

async function batchDelete() {
  if (selectedIds.value.size === 0) return
  if (!confirm(`确认删除 ${selectedIds.value.size} 条记录？`)) return
  for (const id of selectedIds.value) {
    await deleteTrace(id).catch(() => {})
  }
  selectedIds.value = new Set()
  fetchTraces()
  fetchStats()
}

function statusLabel(s: string) {
  const map: Record<string, string> = { success: "成功", failed: "失败", running: "运行中", cancelled: "已取消" }
  return map[s] ?? s
}

function statusClass(s: string) {
  const map: Record<string, string> = {
    success: "text-green-500 bg-green-500/10",
    failed: "text-red-500 bg-red-500/10",
    running: "text-blue-500 bg-blue-500/10",
    cancelled: "text-gray-400 bg-gray-500/10",
  }
  return map[s] ?? "text-gray-400 bg-gray-500/10"
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}m`
}

function formatTime(ts: string): string {
  if (!ts) return "-"
  return new Date(ts).toLocaleString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
}

// ── 生命周期 ──
onMounted(() => {
  fetchTraces()
  fetchStats()
})
</script>

<template>
  <div class="traces-page">
    <!-- 页面标题 & 操作栏 -->
    <header class="page-header">
      <div class="header-left">
        <h1 class="page-title">调用追踪</h1>
        <span class="page-subtitle">Agent 执行记录、工具调用与文件变更审计</span>
      </div>
      <button class="btn btn-ghost" @click="fetchTraces(); fetchStats()" title="刷新">
        <RefreshCw :size="16" />
      </button>
    </header>

    <!-- 统计卡片 -->
    <section v-if="stats" class="stats-cards">
      <div class="stat-card">
        <div class="stat-icon"><BarChart3 :size="20" /></div>
        <div class="stat-body">
          <span class="stat-value">{{ stats.total_traces }}</span>
          <span class="stat-label">总次数</span>
        </div>
      </div>
      <div class="stat-card success">
        <div class="stat-icon"><CheckCircle :size="20" /></div>
        <div class="stat-body">
          <span class="stat-value">{{ stats.success_count }}</span>
          <span class="stat-label">成功</span>
        </div>
      </div>
      <div class="stat-card fail">
        <div class="stat-icon"><XCircle :size="20" /></div>
        <div class="stat-body">
          <span class="stat-value">{{ stats.failed_count }}</span>
          <span class="stat-label">失败</span>
        </div>
      </div>
      <div class="stat-card running">
        <div class="stat-icon"><PlayCircle :size="20" /></div>
        <div class="stat-body">
          <span class="stat-value">{{ stats.running_count }}</span>
          <span class="stat-label">运行中</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon"><Clock :size="20" /></div>
        <div class="stat-body">
          <span class="stat-value">{{ formatDuration(stats.avg_duration_ms) }}</span>
          <span class="stat-label">平均耗时</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon"><Zap :size="20" /></div>
        <div class="stat-body">
          <span class="stat-value">{{ stats.avg_tokens?.toFixed(0) ?? 0 }}</span>
          <span class="stat-label">平均 Token</span>
        </div>
      </div>
    </section>

    <!-- 搜索栏 -->
    <section class="filters-bar">
      <div class="filter-group">
        <input
          v-model="filters.agent_name"
          type="text"
          placeholder="Agent 名称..."
          class="filter-input"
          @keyup.enter="onSearch"
        />
        <input
          v-model="filters.model_name"
          type="text"
          placeholder="模型名称..."
          class="filter-input"
          @keyup.enter="onSearch"
        />
        <select v-model="filters.status" class="filter-select" @change="onSearch">
          <option v-for="o in statusOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <button class="btn btn-primary" @click="onSearch">
          <Search :size="14" />
          <span>搜索</span>
        </button>
      </div>
      <button
        v-if="selectedIds.size > 0"
        class="btn btn-danger-ghost"
        @click="batchDelete"
      >
        <Trash2 :size="14" />
        <span>删除 ({{ selectedIds.size }})</span>
      </button>
    </section>

    <!-- 表格 -->
    <section class="table-wrapper">
      <table class="data-table">
        <thead>
          <tr>
            <th class="col-check">
              <input
                type="checkbox"
                :checked="selectedIds.size === traces.length && traces.length > 0"
                @change="toggleAll"
              />
            </th>
            <th>Agent</th>
            <th>模型</th>
            <th>状态</th>
            <th>耗时</th>
            <th>Token</th>
            <th>工具调用</th>
            <th>时间</th>
            <th>错误</th>
            <th class="col-actions">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading && traces.length === 0">
            <td :colspan="10" class="empty-cell">加载中...</td>
          </tr>
          <tr v-else-if="!loading && traces.length === 0">
            <td :colspan="10" class="empty-cell">暂无追踪记录</td>
          </tr>
          <tr
            v-for="t in traces"
            v-else
            :key="t.trace_id"
            class="trace-row"
            @click="goDetail(t.trace_id)"
          >
            <td class="col-check" @click.stop>
              <input
                type="checkbox"
                :checked="selectedIds.has(t.trace_id)"
                @change="toggleSelect(t.trace_id)"
              />
            </td>
            <td class="col-agent">
              <Monitor :size="14" class="inline-icon" />
              {{ t.agent_name || "—" }}
            </td>
            <td class="col-model">{{ t.model_name || "—" }}</td>
            <td>
              <span :class="['status-badge', statusClass(t.status)]">
                {{ statusLabel(t.status) }}
              </span>
            </td>
            <td class="col-num">{{ formatDuration(t.duration_ms) }}</td>
            <td class="col-num">{{ t.total_tokens }}</td>
            <td class="col-num">{{ t.tool_call_count }}</td>
            <td class="col-time">{{ formatTime(t.start_time) }}</td>
            <td class="col-error">
              <span v-if="t.error_message" :title="t.error_message" class="err-hint">
                {{ t.error_message.slice(0, 40) }}{{ t.error_message.length > 40 ? "..." : "" }}
              </span>
            </td>
            <td class="col-actions" @click.stop>
              <button class="btn-icon" title="查看详情" @click="goDetail(t.trace_id)">
                <Eye :size="14" />
              </button>
              <button class="btn-icon danger" title="删除" @click="onDelete(t.trace_id)">
                <Trash2 :size="14" />
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 分页 -->
    <section v-if="total > filters.size" class="pagination">
      <button class="btn btn-ghost" :disabled="filters.page <= 1" @click="onPageChange(filters.page - 1)">
        上一页
      </button>
      <span class="page-info">第 {{ filters.page }} / {{ totalPages }} 页，共 {{ total }} 条</span>
      <button class="btn btn-ghost" :disabled="filters.page >= totalPages" @click="onPageChange(filters.page + 1)">
        下一页
      </button>
    </section>
  </div>
</template>

<style scoped>
/* ── 页面布局 ── */
.traces-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
  height: 100%;
  overflow: auto;
  background: var(--color-ide-bg, #0d1117);
  color: var(--color-ide-fg, #c9d1d9);
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-left { display: flex; flex-direction: column; gap: 2px; }
.page-title { font-size: 20px; font-weight: 700; margin: 0; }
.page-subtitle { font-size: 13px; color: var(--color-ide-fg-muted, #8b949e); }

/* ── 统计卡片 ── */
.stats-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 12px;
}
.stat-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: 8px;
  background: var(--color-ide-panel-bg, #161b22);
  border: 1px solid var(--color-ide-border, #30363d);
}
.stat-card .stat-icon { color: var(--color-ide-accent, #58a6ff); flex-shrink: 0; }
.stat-card.success .stat-icon { color: #3fb950; }
.stat-card.fail .stat-icon { color: #f85149; }
.stat-card.running .stat-icon { color: #58a6ff; }
.stat-body { display: flex; flex-direction: column; }
.stat-value { font-size: 20px; font-weight: 700; }
.stat-label { font-size: 12px; color: var(--color-ide-fg-muted, #8b949e); }

/* ── 筛选栏 ── */
.filters-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.filter-group { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.filter-input, .filter-select {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid var(--color-ide-border, #30363d);
  background: var(--color-ide-input-bg, #0d1117);
  color: var(--color-ide-fg, #c9d1d9);
  font-size: 13px;
  outline: none;
}
.filter-input:focus, .filter-select:focus {
  border-color: var(--color-ide-accent, #58a6ff);
}
.filter-input { width: 160px; }
.filter-select { width: 120px; }

/* ── 按钮 ── */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid transparent;
  font-size: 13px;
  cursor: pointer;
  transition: all .15s;
  background: transparent;
  color: var(--color-ide-fg, #c9d1d9);
}
.btn-primary {
  background: var(--color-ide-accent, #238636);
  border-color: var(--color-ide-accent, #238636);
  color: #fff;
}
.btn-ghost { border-color: var(--color-ide-border, #30363d); }
.btn-ghost:hover { background: var(--color-ide-hover, #21262d); }
.btn-danger-ghost { border-color: #f85149; color: #f85149; }
.btn-danger-ghost:hover { background: #f8514920; }
.btn:disabled { opacity: .4; cursor: not-allowed; }
.btn-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px; height: 28px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--color-ide-fg-muted, #8b949e);
  cursor: pointer;
}
.btn-icon:hover { background: var(--color-ide-hover, #21262d); color: var(--color-ide-fg, #c9d1d9); }
.btn-icon.danger:hover { color: #f85149; }

/* ── 表格 ── */
.table-wrapper {
  border: 1px solid var(--color-ide-border, #30363d);
  border-radius: 8px;
  overflow: hidden;
}
.data-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.data-table th {
  padding: 10px 12px;
  text-align: left;
  font-weight: 600;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: .5px;
  color: var(--color-ide-fg-muted, #8b949e);
  background: var(--color-ide-panel-bg, #161b22);
  border-bottom: 1px solid var(--color-ide-border, #30363d);
  white-space: nowrap;
}
.data-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-ide-border, #30363d);
}
.trace-row { cursor: pointer; transition: background .1s; }
.trace-row:hover { background: var(--color-ide-hover, #1c2129); }
.trace-row:last-child td { border-bottom: none; }
.col-check { width: 36px; text-align: center; }
.col-actions { width: 80px; }
.col-num { text-align: right; font-variant-numeric: tabular-nums; }
.col-time { white-space: nowrap; font-size: 12px; color: var(--color-ide-fg-muted, #8b949e); }
.col-error { max-width: 200px; }
.empty-cell { text-align: center; padding: 40px 12px; color: var(--color-ide-fg-muted, #8b949e); }

/* ── 状态徽章 ── */
.status-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 500;
}

/* ── 错误提示 ── */
.err-hint { color: #f85149; font-size: 12px; cursor: help; }

/* ── 内联图标 ── */
.inline-icon { margin-right: 4px; vertical-align: -2px; }

/* ── 分页 ── */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 8px 0;
}
.page-info { font-size: 13px; color: var(--color-ide-fg-muted, #8b949e); }
</style>
