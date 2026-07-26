<script setup lang="ts">
/**
 * Agent 自省反思页面
 * 多维评估 Agent 执行质量，历史追踪与统计分析
 */
import { ref, reactive, onMounted, computed } from "vue"
import {
  Brain, BarChart3, TrendingUp, AlertTriangle, Lightbulb,
  CheckCircle, RefreshCw, Send, FileSearch, History, Target
} from "lucide-vue-next"
import {
  reflect, getReflectionHistory, getReflectionStats,
  type ReflectionResult, type ReflectionHistoryItem, type ReflectionStats
} from "@/api/reflection"

// ── Tab ──
const activeTab = ref<"reflect" | "history">("reflect")

// ── 执行自省 ──
const reflectForm = reactive({ trace_id: "", agent_name: "", input: "", output: "" })
const reflectLoading = ref(false)
const currentResult = ref<ReflectionResult | null>(null)
const reflectError = ref("")

async function doReflect() {
  if (!reflectForm.trace_id.trim()) {
    reflectError.value = "请输入 Trace ID"
    return
  }
  reflectError.value = ""
  reflectLoading.value = true
  try {
    currentResult.value = await reflect({
      trace_id: reflectForm.trace_id.trim(),
      agent_name: reflectForm.agent_name.trim() || undefined,
      input: reflectForm.input.trim() || undefined,
      output: reflectForm.output.trim() || undefined,
    })
    // 刷新历史列表和统计
    fetchHistory()
    fetchStats()
  } catch (e: any) {
    reflectError.value = e?.response?.data?.detail ?? e?.message ?? "自省执行失败"
  } finally {
    reflectLoading.value = false
  }
}

// ── 历史记录 ──
const history = ref<ReflectionHistoryItem[]>([])
const histPage = ref(1)
const histTotal = ref(0)
const histSize = 20
const histFilterAgent = ref("")
const histLoading = ref(false)
const histTotalPages = computed(() => Math.max(1, Math.ceil(histTotal.value / histSize)))

// ── 统计 ──
const stats = ref<ReflectionStats | null>(null)

// ── 数据加载 ──
async function fetchHistory() {
  histLoading.value = true
  try {
    const res = await getReflectionHistory({
      agent_name: histFilterAgent.value || undefined,
      page: histPage.value,
      size: histSize,
    })
    history.value = res.data
    histTotal.value = res.total
  } catch (e) {
    console.error("获取自省历史失败:", e)
  } finally {
    histLoading.value = false
  }
}

async function fetchStats() {
  try {
    stats.value = await getReflectionStats({
      agent_name: histFilterAgent.value || undefined,
    })
  } catch (e) {
    console.error("获取自省统计失败:", e)
  }
}

function onHistPageChange(p: number) {
  histPage.value = p
  fetchHistory()
}

function onAgentFilterChange() {
  histPage.value = 1
  fetchHistory()
  fetchStats()
}

// ── 评分颜色 ──
function scoreColor(v: number) {
  if (v >= 0.8) return "score-high"
  if (v >= 0.6) return "score-mid"
  return "score-low"
}
function scorePercent(v: number) { return `${(v * 100).toFixed(0)}%` }

// ── 生命周期 ──
onMounted(() => {
  fetchHistory()
  fetchStats()
})
</script>

<template>
  <div class="reflection-page">
    <!-- 页头 -->
    <header class="page-header">
      <div class="header-left">
        <h1 class="page-title">Agent 自省</h1>
        <span class="page-subtitle">多维度评估 Agent 表现，持续改进决策质量</span>
      </div>
      <button class="btn btn-ghost" @click="fetchHistory(); fetchStats()" title="刷新">
        <RefreshCw :size="16" />
      </button>
    </header>

    <!-- 统计卡片 -->
    <section v-if="stats" class="stats-cards">
      <div class="stat-card">
        <div class="stat-icon"><BarChart3 :size="18" /></div>
        <div class="stat-body">
          <span class="stat-value">{{ stats.total_reflections }}</span>
          <span class="stat-label">总自省次数</span>
        </div>
      </div>
      <div class="stat-card" :class="scoreColor(stats.avg_score)">
        <div class="stat-icon"><Target :size="18" /></div>
        <div class="stat-body">
          <span class="stat-value">{{ scorePercent(stats.avg_score) }}</span>
          <span class="stat-label">平均得分</span>
        </div>
      </div>
      <div class="stat-card score-high">
        <div class="stat-icon"><CheckCircle :size="18" /></div>
        <div class="stat-body">
          <span class="stat-value">{{ scorePercent(stats.max_score) }}</span>
          <span class="stat-label">最高得分</span>
        </div>
      </div>
      <div class="stat-card score-low">
        <div class="stat-icon"><AlertTriangle :size="18" /></div>
        <div class="stat-body">
          <span class="stat-value">{{ scorePercent(stats.min_score) }}</span>
          <span class="stat-label">最低得分</span>
        </div>
      </div>
    </section>

    <!-- Tab -->
    <nav class="tab-nav">
      <button :class="['tab-btn', { active: activeTab === 'reflect' }]" @click="activeTab = 'reflect'">
        <FileSearch :size="14" /> 执行自省
      </button>
      <button :class="['tab-btn', { active: activeTab === 'history' }]" @click="activeTab = 'history'">
        <History :size="14" /> 历史记录
      </button>
    </nav>

    <!-- 执行自省 -->
    <section v-if="activeTab === 'reflect'" class="reflect-panel">
      <div class="form-card">
        <h3 class="card-title">
          <Brain :size="16" /> 提交 Trace 进行多维评估
        </h3>
        <div class="form-grid">
          <div class="form-field">
            <label class="form-label">Trace ID <span class="required">*</span></label>
            <input v-model="reflectForm.trace_id" type="text" placeholder="输入追踪 ID..." class="form-input" />
          </div>
          <div class="form-field">
            <label class="form-label">Agent 名称</label>
            <input v-model="reflectForm.agent_name" type="text" placeholder="可选" class="form-input" />
          </div>
        </div>
        <div class="form-field">
          <label class="form-label">输入上下文 (可选)</label>
          <textarea v-model="reflectForm.input" placeholder="Agent 输入提示词..." class="form-textarea" rows="3" />
        </div>
        <div class="form-field">
          <label class="form-label">输出结果 (可选)</label>
          <textarea v-model="reflectForm.output" placeholder="Agent 输出..." class="form-textarea" rows="3" />
        </div>

        <div class="form-actions">
          <button class="btn btn-primary" :disabled="reflectLoading" @click="doReflect">
            <Send :size="14" />
            {{ reflectLoading ? "评估中..." : "开始自省" }}
          </button>
        </div>

        <div v-if="reflectError" class="error-msg">{{ reflectError }}</div>
      </div>

      <!-- 自省结果 -->
      <div v-if="currentResult" class="result-card">
        <div class="result-header">
          <Brain :size="18" />
          <span>自省结果</span>
          <span :class="['badge', scoreColor(currentResult.score_overall)]">
            总分 {{ scorePercent(currentResult.score_overall) }}
          </span>
        </div>

        <!-- 维度评分 -->
        <div v-if="currentResult.dimensions && Object.keys(currentResult.dimensions).length" class="dimensions-grid">
          <div v-for="(val, key) in currentResult.dimensions" :key="key" class="dimension-bar">
            <div class="dim-label">
              <span>{{ key }}</span>
              <span :class="scoreColor(val)">{{ scorePercent(val) }}</span>
            </div>
            <div class="dim-track">
              <div class="dim-fill" :class="scoreColor(val)" :style="{ width: `${val * 100}%` }" />
            </div>
          </div>
        </div>

        <!-- 总结 -->
        <div v-if="currentResult.summary" class="result-section">
          <h4>总结</h4>
          <p>{{ currentResult.summary }}</p>
        </div>

        <!-- 优势 -->
        <div v-if="currentResult.strengths.length" class="result-section">
          <h4><CheckCircle :size="14" /> 优势</h4>
          <ul>
            <li v-for="s in currentResult.strengths" :key="s">{{ s }}</li>
          </ul>
        </div>

        <!-- 薄弱点 -->
        <div v-if="currentResult.weaknesses.length" class="result-section">
          <h4><AlertTriangle :size="14" /> 需改进</h4>
          <ul>
            <li v-for="w in currentResult.weaknesses" :key="w">{{ w }}</li>
          </ul>
        </div>

        <!-- 建议 -->
        <div v-if="currentResult.suggestions.length" class="result-section">
          <h4><Lightbulb :size="14" /> 建议</h4>
          <ul>
            <li v-for="s in currentResult.suggestions" :key="s">{{ s }}</li>
          </ul>
        </div>
      </div>
    </section>

    <!-- 历史记录 -->
    <section v-if="activeTab === 'history'" class="history-panel">
      <!-- 筛选 -->
      <div class="history-filter">
        <input
          v-model="histFilterAgent"
          type="text"
          placeholder="按 Agent 筛选..."
          class="filter-input"
          @keyup.enter="onAgentFilterChange"
        />
        <button class="btn btn-ghost" @click="onAgentFilterChange">筛选</button>
      </div>

      <!-- 表格 -->
      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>自省 ID</th>
              <th>Trace ID</th>
              <th>Agent</th>
              <th>得分</th>
              <th>时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="histLoading"><td :colspan="5" class="empty-cell">加载中...</td></tr>
            <tr v-else-if="history.length === 0"><td :colspan="5" class="empty-cell">暂无自省记录</td></tr>
            <tr v-for="h in history" v-else :key="h.reflection_id" class="history-row">
              <td class="mono">{{ h.reflection_id.slice(0, 12) }}...</td>
              <td class="mono">{{ h.trace_id.slice(0, 16) }}...</td>
              <td>{{ h.agent_name || "—" }}</td>
              <td>
                <span :class="['badge', scoreColor(h.score_overall)]">
                  {{ scorePercent(h.score_overall) }}
                </span>
              </td>
              <td class="col-time">{{ new Date(h.created_at).toLocaleString("zh-CN") }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 分页 -->
      <div v-if="histTotal > histSize" class="pagination">
        <button class="btn btn-ghost" :disabled="histPage <= 1" @click="onHistPageChange(histPage - 1)">上一页</button>
        <span class="page-info">第 {{ histPage }} / {{ histTotalPages }} 页，共 {{ histTotal }} 条</span>
        <button class="btn btn-ghost" :disabled="histPage >= histTotalPages" @click="onHistPageChange(histPage + 1)">下一页</button>
      </div>
    </section>
  </div>
</template>

<style scoped>
/* ── 页面 ── */
.reflection-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
  height: 100%;
  overflow: auto;
  background: var(--color-ide-bg, #0d1117);
  color: var(--color-ide-fg, #c9d1d9);
}

/* ── 页头 ── */
.page-header { display: flex; justify-content: space-between; align-items: center; }
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
.stat-card .stat-icon { flex-shrink: 0; color: var(--color-ide-accent, #58a6ff); }
.stat-body { display: flex; flex-direction: column; }
.stat-value { font-size: 20px; font-weight: 700; }
.stat-label { font-size: 12px; color: var(--color-ide-fg-muted, #8b949e); }

/* ── Tab ── */
.tab-nav {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid var(--color-ide-border, #30363d);
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
.tab-btn.active { color: var(--color-ide-accent, #58a6ff); border-bottom-color: var(--color-ide-accent, #58a6ff); }

/* ── 表单 ── */
.form-card, .result-card {
  background: var(--color-ide-panel-bg, #161b22);
  border: 1px solid var(--color-ide-border, #30363d);
  border-radius: 10px;
  padding: 20px;
}
.card-title { font-size: 15px; font-weight: 600; margin: 0 0 16px 0; display: flex; align-items: center; gap: 8px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.form-field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 10px; }
.form-label { font-size: 13px; font-weight: 500; color: var(--color-ide-fg-muted, #8b949e); }
.required { color: #f85149; }
.form-input, .form-textarea {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--color-ide-border, #30363d);
  background: var(--color-ide-input-bg, #0d1117);
  color: var(--color-ide-fg, #c9d1d9);
  font-size: 13px;
  font-family: inherit;
  outline: none;
  resize: vertical;
}
.form-input:focus, .form-textarea:focus { border-color: var(--color-ide-accent, #58a6ff); }
.form-actions { margin-top: 12px; }
.error-msg { margin-top: 10px; color: #f85149; font-size: 13px; }

/* ── 结果卡片 ── */
.result-header { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; font-size: 15px; font-weight: 600; }

/* ── 维度评分 ── */
.dimensions-grid { display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }
.dimension-bar { }
.dim-label { display: flex; justify-content: space-between; font-size: 12px; font-weight: 500; margin-bottom: 3px; }
.dim-track {
  width: 100%;
  height: 6px;
  background: var(--color-ide-hover, #21262d);
  border-radius: 3px;
  overflow: hidden;
}
.dim-fill { height: 100%; border-radius: 3px; transition: width .4s ease; }
.score-high { background: #3fb950; }
.score-mid { background: #d29922; }
.score-low { background: #f85149; }

/* ── 结果段落 ── */
.result-section { margin-top: 14px; }
.result-section h4 {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-ide-fg-muted, #8b949e);
  margin: 0 0 6px 0;
  display: flex;
  align-items: center;
  gap: 6px;
}
.result-section p { font-size: 13px; line-height: 1.6; margin: 0; }
.result-section ul { margin: 0; padding-left: 18px; }
.result-section li { font-size: 13px; line-height: 1.6; }

/* ── 历史筛选 ── */
.history-filter { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
.filter-input {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid var(--color-ide-border, #30363d);
  background: var(--color-ide-input-bg, #0d1117);
  color: var(--color-ide-fg, #c9d1d9);
  font-size: 13px;
  outline: none;
  width: 220px;
}
.filter-input:focus { border-color: var(--color-ide-accent, #58a6ff); }

/* ── 表格 ── */
.table-wrapper {
  border: 1px solid var(--color-ide-border, #30363d);
  border-radius: 8px;
  overflow: hidden;
}
.data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
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
}
.data-table td { padding: 10px 12px; border-bottom: 1px solid var(--color-ide-border, #30363d); }
.history-row:hover { background: var(--color-ide-hover, #1c2129); }
.empty-cell { text-align: center; padding: 40px 12px; color: var(--color-ide-fg-muted, #8b949e); }
.col-time { font-size: 12px; color: var(--color-ide-fg-muted, #8b949e); white-space: nowrap; }
.mono { font-family: monospace; font-size: 12px; }

/* ── 通用 ── */
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
.btn-primary { background: var(--color-ide-accent, #238636); border-color: var(--color-ide-accent, #238636); color: #fff; }
.btn-ghost { border-color: var(--color-ide-border, #30363d); }
.btn-ghost:hover { background: var(--color-ide-hover, #21262d); }
.btn:disabled { opacity: .4; cursor: not-allowed; }

.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
}
.score-high.badge { background: #3fb95020; color: #3fb950; }
.score-mid.badge { background: #d2992220; color: #d29922; }
.score-low.badge { background: #f8514920; color: #f85149; }

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 8px 0;
}
.page-info { font-size: 13px; color: var(--color-ide-fg-muted, #8b949e); }
</style>
