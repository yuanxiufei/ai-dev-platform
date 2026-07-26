<script setup lang="ts">
/**
 * Agent 调用追踪详情页
 * 展示单次调用的完整信息：概览、工具调用、文件变更、日志
 */
import { ref, onMounted } from "vue"
import { useRoute, useRouter } from "vue-router"
import { ArrowLeft, RefreshCw, Clock, Zap, Wrench, FileText, ListTree, AlertCircle } from "lucide-vue-next"
import {
  getTrace, listToolCalls, listFileChanges, listTraceLogs,
  type TraceDetail, type ToolCall, type FileChange, type TraceLog,
} from "@/api/traces"

const route = useRoute()
const router = useRouter()

const traceId = route.params.traceId as string
const trace = ref<TraceDetail | null>(null)
const toolCalls = ref<ToolCall[]>([])
const fileChanges = ref<FileChange[]>([])
const logs = ref<TraceLog[]>([])
const activeTab = ref<"overview" | "toolcalls" | "files" | "logs">("overview")
const loading = ref(true)

const tabs = [
  { key: "overview", label: "概览", icon: ListTree },
  { key: "toolcalls", label: "工具调用", icon: Wrench },
  { key: "files", label: "文件变更", icon: FileText },
  { key: "logs", label: "日志", icon: AlertCircle },
] as const

// ── 数据加载 ──
async function loadData() {
  loading.value = true
  try {
    const [t, tc, fc, lg] = await Promise.all([
      getTrace(traceId),
      listToolCalls(traceId),
      listFileChanges(traceId),
      listTraceLogs(traceId),
    ])
    trace.value = t
    toolCalls.value = tc.data ?? []
    fileChanges.value = fc.data ?? []
    logs.value = lg.data ?? []
  } catch (e) {
    console.error("加载追踪详情失败:", e)
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.push("/traces")
}

function goAgent(agentName: string) {
  // 跳转到 Agent 追踪列表，过滤当前 agent
  router.push(`/traces?agent_name=${encodeURIComponent(agentName)}`)
}

// ── 格式化 ──
function statusLabel(s: string) {
  const m: Record<string, string> = { success: "成功", failed: "失败", running: "运行中", cancelled: "已取消" }
  return m[s] ?? s
}
function statusClass(s: string) {
  const m: Record<string, string> = {
    success: "badge-success", failed: "badge-danger", running: "badge-info", cancelled: "badge-muted"
  }
  return m[s] ?? "badge-muted"
}
function fmtMs(ms: number) {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}m`
}
function fmtTime(ts: string) {
  if (!ts) return "-"
  return new Date(ts).toLocaleString("zh-CN")
}
function logLevelClass(l: string) {
  return {
    info: "level-info", warn: "level-warn", error: "level-error", debug: "level-debug",
  }[l] ?? "level-debug"
}

onMounted(loadData)
</script>

<template>
  <div class="detail-page">
    <!-- 顶部导航 -->
    <header class="detail-header">
      <button class="btn btn-ghost" @click="goBack">
        <ArrowLeft :size="16" />
        返回列表
      </button>
      <button class="btn btn-ghost" @click="loadData" title="刷新">
        <RefreshCw :size="14" />
      </button>
    </header>

    <!-- 加载中 -->
    <div v-if="loading" class="loading-state">加载中...</div>

    <!-- 内容 -->
    <template v-else-if="trace">
      <!-- 追踪概览卡片 -->
      <section class="trace-card">
        <div class="trace-card-header">
          <div class="trace-id">{{ trace.trace_id }}</div>
          <span :class="['badge', statusClass(trace.status)]">{{ statusLabel(trace.status) }}</span>
        </div>
        <div class="trace-meta-grid">
          <div class="meta-item">
            <span class="meta-label">Agent</span>
            <button class="meta-value link" @click="goAgent(trace.agent_name)">
              {{ trace.agent_name || "—" }}
            </button>
          </div>
          <div class="meta-item">
            <span class="meta-label">模型</span>
            <span class="meta-value">{{ trace.model_name || "—" }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label"><Clock :size="12" /> 耗时</span>
            <span class="meta-value">{{ fmtMs(trace.duration_ms) }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label"><Zap :size="12" /> Token</span>
            <span class="meta-value">{{ trace.total_tokens }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label"><Wrench :size="12" /> 工具调用</span>
            <span class="meta-value">{{ trace.tool_call_count }}</span>
          </div>
          <div class="meta-item">
            <span class="meta-label">开始时间</span>
            <span class="meta-value">{{ fmtTime(trace.start_time) }}</span>
          </div>
        </div>
        <div v-if="trace.error_message" class="error-block">
          <AlertCircle :size="14" />
          <span>{{ trace.error_message }}</span>
        </div>
      </section>

      <!-- Tab 切换 -->
      <nav class="tab-nav">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          :class="['tab-btn', { active: activeTab === tab.key }]"
          @click="activeTab = tab.key"
        >
          <component :is="tab.icon" :size="14" />
          {{ tab.label }}
        </button>
      </nav>

      <!-- Tab 内容 -->
      <section class="tab-content">
        <!-- 概览 -->
        <div v-if="activeTab === 'overview'" class="overview-panel">
          <div class="code-block">
            <h3 class="block-title">输入 (Input)</h3>
            <pre>{{ trace.input || "(无)" }}</pre>
          </div>
          <div v-if="trace.plan" class="code-block">
            <h3 class="block-title">计划 (Plan)</h3>
            <pre>{{ trace.plan }}</pre>
          </div>
          <div class="code-block">
            <h3 class="block-title">输出 (Output)</h3>
            <pre>{{ trace.output || "(无)" }}</pre>
          </div>
          <div v-if="trace.metadata && Object.keys(trace.metadata).length" class="code-block">
            <h3 class="block-title">元数据</h3>
            <pre>{{ JSON.stringify(trace.metadata, null, 2) }}</pre>
          </div>
        </div>

        <!-- 工具调用 -->
        <div v-if="activeTab === 'toolcalls'">
          <div v-if="toolCalls.length === 0" class="empty-hint">无工具调用记录</div>
          <div v-for="tc in toolCalls" :key="tc.tool_call_id" class="tool-call-card">
            <div class="tc-header">
              <span class="tc-name">{{ tc.tool_name }}</span>
              <span :class="['badge', statusClass(tc.status)]">{{ statusLabel(tc.status) }}</span>
              <span class="tc-duration">{{ fmtMs(tc.duration_ms) }}</span>
            </div>
            <div v-if="tc.error" class="tc-error">
              <AlertCircle :size="12" /> {{ tc.error }}
            </div>
            <details class="tc-detail">
              <summary>参数</summary>
              <pre>{{ JSON.stringify(tc.arguments, null, 2) }}</pre>
            </details>
            <details v-if="tc.result" class="tc-detail">
              <summary>结果</summary>
              <pre>{{ tc.result }}</pre>
            </details>
          </div>
        </div>

        <!-- 文件变更 -->
        <div v-if="activeTab === 'files'">
          <div v-if="fileChanges.length === 0" class="empty-hint">无文件变更</div>
          <div v-for="fc in fileChanges" :key="fc.file_path + fc.timestamp" class="file-change-row">
            <span :class="['change-tag', `change-${fc.change_type}`]">
              {{ { create: "新增", modify: "修改", delete: "删除" }[fc.change_type] ?? fc.change_type }}
            </span>
            <code class="file-path">{{ fc.file_path }}</code>
            <span class="fc-time">{{ fmtTime(fc.timestamp) }}</span>
            <details v-if="fc.diff" class="diff-detail">
              <summary>查看 Diff</summary>
              <pre class="diff-content">{{ fc.diff }}</pre>
            </details>
          </div>
        </div>

        <!-- 日志 -->
        <div v-if="activeTab === 'logs'">
          <div v-if="logs.length === 0" class="empty-hint">无日志记录</div>
          <div v-for="lg in logs" :key="lg.log_id" :class="['log-row', logLevelClass(lg.level)]">
            <span class="log-time">{{ fmtTime(lg.timestamp) }}</span>
            <span class="log-level-badge">{{ lg.level.toUpperCase() }}</span>
            <span v-if="lg.category" class="log-category">[{{ lg.category }}]</span>
            <span class="log-msg">{{ lg.message }}</span>
          </div>
        </div>
      </section>
    </template>

    <!-- 无数据 -->
    <div v-else class="empty-state">追踪记录不存在</div>
  </div>
</template>

<style scoped>
/* ── 布局 ── */
.detail-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
  height: 100%;
  overflow: auto;
  background: var(--color-ide-bg, #0d1117);
  color: var(--color-ide-fg, #c9d1d9);
}

/* ── 顶部导航 ── */
.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
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
.btn-ghost { border-color: var(--color-ide-border, #30363d); }
.btn-ghost:hover { background: var(--color-ide-hover, #21262d); }

/* ── 加载/空态 ── */
.loading-state, .empty-state, .empty-hint {
  text-align: center;
  padding: 60px 20px;
  color: var(--color-ide-fg-muted, #8b949e);
  font-size: 14px;
}

/* ── 追踪概览卡片 ── */
.trace-card {
  background: var(--color-ide-panel-bg, #161b22);
  border: 1px solid var(--color-ide-border, #30363d);
  border-radius: 10px;
  padding: 20px;
}
.trace-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 14px;
}
.trace-id {
  font-family: monospace;
  font-size: 14px;
  font-weight: 600;
  word-break: break-all;
}
.trace-meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}
.meta-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.meta-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: .5px;
  color: var(--color-ide-fg-muted, #8b949e);
  display: flex;
  align-items: center;
  gap: 4px;
}
.meta-value { font-size: 14px; font-weight: 500; }
.meta-value.link { color: var(--color-ide-accent, #58a6ff); cursor: pointer; border: none; background: none; padding: 0; font-size: 14px; }
.meta-value.link:hover { text-decoration: underline; }

/* ── 错误信息 ── */
.error-block {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 14px;
  padding: 10px 14px;
  background: #f8514915;
  border: 1px solid #f8514940;
  border-radius: 6px;
  color: #f85149;
  font-size: 13px;
  border-radius: 8px;
}

/* ── Tab ── */
.tab-nav {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--color-ide-border, #30363d);
  padding-bottom: 0;
}
.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  background: transparent;
  color: var(--color-ide-fg-muted, #8b949e);
  font-size: 13px;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
  transition: all .15s;
}
.tab-btn:hover { color: var(--color-ide-fg, #c9d1d9); }
.tab-btn.active {
  color: var(--color-ide-accent, #58a6ff);
  border-bottom-color: var(--color-ide-accent, #58a6ff);
}

/* ── 概览面板 ── */
.overview-panel { display: flex; flex-direction: column; gap: 16px; }
.code-block {
  background: var(--color-ide-input-bg, #0d1117);
  border: 1px solid var(--color-ide-border, #30363d);
  border-radius: 8px;
  padding: 14px;
  overflow: auto;
}
.block-title {
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: .5px;
  color: var(--color-ide-fg-muted, #8b949e);
  margin: 0 0 8px 0;
}
.code-block pre {
  margin: 0;
  font-family: "Cascadia Code", "Fira Code", monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
}

/* ── 工具调用卡片 ── */
.tool-call-card {
  background: var(--color-ide-panel-bg, #161b22);
  border: 1px solid var(--color-ide-border, #30363d);
  border-radius: 8px;
  padding: 14px;
  margin-bottom: 10px;
}
.tc-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.tc-name { font-weight: 600; font-family: monospace; }
.tc-duration { font-size: 12px; color: var(--color-ide-fg-muted, #8b949e); margin-left: auto; }
.tc-error {
  display: flex;
  gap: 6px;
  color: #f85149;
  font-size: 12px;
  margin-bottom: 8px;
}
.tc-detail {
  margin-top: 8px;
  font-size: 13px;
}
.tc-detail summary {
  cursor: pointer;
  color: var(--color-ide-accent, #58a6ff);
  font-size: 12px;
  font-weight: 500;
}
.tc-detail pre {
  background: var(--color-ide-input-bg, #0d1117);
  border-radius: 4px;
  padding: 10px;
  margin-top: 6px;
  font-family: monospace;
  font-size: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

/* ── 文件变更行 ── */
.file-change-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--color-ide-border, #30363d);
  font-size: 13px;
  flex-wrap: wrap;
}
.change-tag {
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
}
.change-create { background: #3fb95020; color: #3fb950; }
.change-modify { background: #d2992220; color: #d29922; }
.change-delete { background: #f8514920; color: #f85149; }
.file-path { font-family: monospace; flex: 1; min-width: 200px; }
.fc-time { font-size: 12px; color: var(--color-ide-fg-muted, #8b949e); }
.diff-detail { width: 100%; margin-top: 6px; }
.diff-detail summary { cursor: pointer; color: var(--color-ide-accent, #58a6ff); font-size: 12px; }
.diff-content {
  background: var(--color-ide-input-bg, #0d1117);
  border-radius: 4px;
  padding: 10px;
  margin-top: 6px;
  font-family: monospace;
  font-size: 12px;
  overflow-x: auto;
  white-space: pre-wrap;
}

/* ── 日志行 ── */
.log-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--color-ide-border, #30363d);
  font-family: monospace;
  font-size: 12px;
  flex-wrap: wrap;
}
.log-time { color: var(--color-ide-fg-muted, #8b949e); white-space: nowrap; }
.log-level-badge { font-weight: 600; min-width: 48px; }
.log-category { color: var(--color-ide-fg-muted, #8b949e); }
.log-msg { flex: 1; word-break: break-word; }
.level-info .log-level-badge { color: #58a6ff; }
.level-warn .log-level-badge { color: #d29922; }
.level-error .log-level-badge { color: #f85149; }
.level-debug .log-level-badge { color: var(--color-ide-fg-muted, #8b949e); }

/* ── 通用徽章 ── */
.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}
.badge-success { background: #3fb95020; color: #3fb950; }
.badge-danger { background: #f8514920; color: #f85149; }
.badge-info { background: #58a6ff20; color: #58a6ff; }
.badge-muted { background: #484f5820; color: #8b949e; }
</style>
