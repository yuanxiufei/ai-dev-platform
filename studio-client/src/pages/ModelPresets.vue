<template>
  <div class="model-presets-page">
    <!-- 头部 -->
    <header class="page-header">
      <div class="header-left">
        <h1 class="page-title">模型预设</h1>
        <span class="page-desc">管理模型参数的预设配置，一键切换最优配置</span>
      </div>
      <button class="btn-primary" @click="openCreate">
        <Plus :size="16" />
        新建预设
      </button>
    </header>

    <!-- 搜索 & 筛选 -->
    <div class="toolbar">
      <div class="search-box">
        <Search :size="16" class="search-icon" />
        <input
          v-model="searchQuery"
          placeholder="搜索预设名称..."
          class="search-input"
          @keyup.enter="fetchList"
        />
      </div>
      <button class="btn-ghost" @click="fetchList">
        <RefreshCw :size="14" />
        刷新
      </button>
    </div>

    <!-- 预设列表 -->
    <div v-if="loading" class="loading-state">
      <Loader :size="24" class="spinner" /> 加载中...
    </div>

    <div v-else-if="presets.length === 0" class="empty-state">
      <Database :size="48" class="empty-icon" />
      <p>暂无预设</p>
      <button class="btn-primary" @click="openCreate">创建第一个预设</button>
    </div>

    <div v-else class="preset-grid">
      <div
        v-for="preset in presets"
        :key="preset.id"
        class="preset-card"
        :class="{ 'preset-public': preset.is_public }"
      >
        <div class="card-header">
          <div class="card-title-row">
            <h3 class="card-name">{{ preset.name }}</h3>
            <span v-if="preset.is_public" class="badge-public">公开</span>
          </div>
          <p v-if="preset.description" class="card-desc">{{ preset.description }}</p>
        </div>

        <div class="card-meta">
          <div class="meta-row">
            <span class="meta-label">模型</span>
            <span class="meta-value">{{ preset.model_name || '未指定' }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">温度</span>
            <span class="meta-value">{{ preset.temperature ?? '默认' }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">最大 Tokens</span>
            <span class="meta-value">{{ preset.max_tokens ?? '默认' }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">使用次数</span>
            <span class="meta-value">{{ preset.usage_count }}</span>
          </div>
          <div v-if="preset.tools?.length" class="meta-row">
            <span class="meta-label">工具</span>
            <span class="meta-value chips">
              <span v-for="t in preset.tools" :key="t" class="chip">{{ t }}</span>
            </span>
          </div>
          <div v-if="preset.knowledge_bases?.length" class="meta-row">
            <span class="meta-label">知识库</span>
            <span class="meta-value chips">
              <span v-for="kb in preset.knowledge_bases" :key="kb" class="chip chip-kb">{{ kb }}</span>
            </span>
          </div>
        </div>

        <div class="card-actions">
          <button class="btn-action btn-apply" title="应用预设" @click="handleApply(preset)">
            <Zap :size="14" /> 应用
          </button>
          <button class="btn-action btn-resolve" title="解析变量" @click="handleResolve(preset)">
            <Braces :size="14" /> 解析
          </button>
          <button class="btn-action btn-edit" title="编辑" @click="openEdit(preset)">
            <Pencil :size="14" />
          </button>
          <button class="btn-action btn-delete" title="删除" @click="handleDelete(preset)">
            <Trash2 :size="14" />
          </button>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="total > pageSize" class="pagination">
      <button :disabled="page <= 1" @click="page--; fetchList()">上一页</button>
      <span class="page-info">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
      <button :disabled="page * pageSize >= total" @click="page++; fetchList()">下一页</button>
    </div>

    <!-- ── 创建/编辑弹窗 ── -->
    <div v-if="showEditor" class="modal-overlay" @click.self="closeEditor">
      <div class="modal-content modal-lg">
        <div class="modal-header">
          <h2>{{ isEditing ? '编辑预设' : '新建预设' }}</h2>
          <button class="btn-close" @click="closeEditor">&times;</button>
        </div>
        <div class="modal-body">
          <!-- 基本信息 -->
          <fieldset class="form-section">
            <legend>基本信息</legend>
            <div class="form-row">
              <label class="form-label">名称 <span class="required">*</span></label>
              <input v-model="form.name" class="form-input" placeholder="预设名称" />
            </div>
            <div class="form-row">
              <label class="form-label">描述</label>
              <textarea v-model="form.description" class="form-textarea" rows="2" placeholder="简要描述该预设的用途" />
            </div>
            <div class="form-row">
              <label class="form-label">绑定模型</label>
              <input v-model="form.model_name" class="form-input" placeholder="如 gpt-4o, claude-3, 或留空自动选择" />
            </div>
            <div class="form-row form-check">
              <label class="form-check-label">
                <input v-model="form.is_public" type="checkbox" />
                公开（其他用户可见）
              </label>
            </div>
          </fieldset>

          <!-- 模型参数 -->
          <fieldset class="form-section">
            <legend>模型参数</legend>
            <div class="form-row">
              <label class="form-label">System Prompt</label>
              <textarea
                v-model="form.system_prompt"
                class="form-textarea form-mono"
                rows="4"
                placeholder="系统提示词，支持 {{ USER_NAME }}, {{ CURRENT_DATE }} 等动态变量"
              />
            </div>
            <div class="form-row form-row-3col">
              <div class="form-col">
                <label class="form-label">Temperature</label>
                <input v-model.number="form.temperature" type="number" class="form-input" min="0" max="2" step="0.1" placeholder="默认" />
              </div>
              <div class="form-col">
                <label class="form-label">Max Tokens</label>
                <input v-model.number="form.max_tokens" type="number" class="form-input" min="1" max="131072" placeholder="默认" />
              </div>
              <div class="form-col">
                <label class="form-label">Top P</label>
                <input v-model.number="form.top_p" type="number" class="form-input" min="0" max="1" step="0.05" placeholder="默认" />
              </div>
            </div>
            <div class="form-row form-check">
              <label class="form-check-label">
                <input v-model="form.force_tools" type="checkbox" />
                强制使用工具
              </label>
            </div>
          </fieldset>

          <!-- 工具 & 知识库 -->
          <fieldset class="form-section">
            <legend>工具 & 知识库</legend>
            <div class="form-row">
              <label class="form-label">工具列表（逗号分隔）</label>
              <input
                v-model="toolsInput"
                class="form-input"
                placeholder="如: web_search, code_interpreter, image_gen"
                @change="syncToolsArray"
              />
            </div>
            <div class="form-row">
              <label class="form-label">知识库 ID（逗号分隔）</label>
              <input
                v-model="kbInput"
                class="form-input"
                placeholder="如: kb-001, kb-002"
                @change="syncKbArray"
              />
            </div>
          </fieldset>
        </div>
        <div class="modal-footer">
          <button class="btn-ghost" @click="closeEditor">取消</button>
          <button class="btn-primary" :disabled="!form.name" @click="handleSave">
            {{ isEditing ? '保存修改' : '创建预设' }}
          </button>
        </div>
      </div>
    </div>

    <!-- ── 解析结果弹窗 ── -->
    <div v-if="resolveResult" class="modal-overlay" @click.self="resolveResult = null">
      <div class="modal-content modal-md">
        <div class="modal-header">
          <h2>解析结果: {{ resolveResult.preset_id }}</h2>
          <button class="btn-close" @click="resolveResult = null">&times;</button>
        </div>
        <div class="modal-body">
          <div class="resolve-section">
            <h4>System Prompt</h4>
            <pre class="resolve-pre">{{ resolveResult.system_prompt }}</pre>
          </div>
          <div class="resolve-section">
            <h4>模型参数</h4>
            <div class="resolve-grid">
              <div><strong>模型:</strong> {{ resolveResult.model_name || 'auto' }}</div>
              <div><strong>温度:</strong> {{ resolveResult.temperature ?? '默认' }}</div>
              <div><strong>Max Tokens:</strong> {{ resolveResult.max_tokens ?? '默认' }}</div>
              <div><strong>强制工具:</strong> {{ resolveResult.force_tools ? '是' : '否' }}</div>
            </div>
          </div>
          <div v-if="resolveResult.tools.length" class="resolve-section">
            <h4>工具</h4>
            <div class="chip-group">
              <span v-for="t in resolveResult.tools" :key="t" class="chip">{{ t }}</span>
            </div>
          </div>
          <div v-if="resolveResult.knowledge_bases.length" class="resolve-section">
            <h4>知识库</h4>
            <div class="chip-group">
              <span v-for="kb in resolveResult.knowledge_bases" :key="kb" class="chip chip-kb">{{ kb }}</span>
            </div>
          </div>
          <div class="resolve-section">
            <h4>已解析变量</h4>
            <pre class="resolve-pre">{{ JSON.stringify(resolveResult.resolved_variables, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Toast 提示 ── -->
    <div v-if="toast" class="toast" :class="toast.type">{{ toast.message }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from "vue"
import {
  Plus, Search, RefreshCw, Loader, Database,
  Zap, Braces, Pencil, Trash2,
} from "lucide-vue-next"
import { modelPresetsApi, type ModelPreset } from "@/api/modelPresets"

// ── State ────────────────────────────────────────────

const presets = ref<ModelPreset[]>([])
const loading = ref(false)
const searchQuery = ref("")
const page = ref(1)
const pageSize = 20
const total = ref(0)

// ── Editor ───────────────────────────────────────────

const showEditor = ref(false)
const isEditing = ref(false)
const editingId = ref<string | null>(null)

const form = reactive({
  name: "",
  description: "",
  model_name: "",
  system_prompt: "",
  temperature: undefined as number | undefined,
  max_tokens: undefined as number | undefined,
  top_p: undefined as number | undefined,
  force_tools: false,
  is_public: false,
  tools: [] as string[],
  knowledge_bases: [] as string[],
  variables: undefined as Record<string, string> | undefined,
})

const toolsInput = ref("")
const kbInput = ref("")

// ── Resolve ──────────────────────────────────────────

const resolveResult = ref<any>(null)

// ── Toast ────────────────────────────────────────────

const toast = ref<{ message: string; type: string } | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | null = null

function showToast(message: string, type = "success") {
  toast.value = { message, type }
  if (toastTimer) clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { toast.value = null }, 3000)
}

// ── Data Fetching ────────────────────────────────────

async function fetchList() {
  loading.value = true
  try {
    const res = await modelPresetsApi.list(page.value, pageSize, searchQuery.value || undefined)
    presets.value = res.data.data
    total.value = res.data.total
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "加载预设列表失败", "error")
  } finally {
    loading.value = false
  }
}

// ── CRUD Operations ──────────────────────────────────

function openCreate() {
  isEditing.value = false
  editingId.value = null
  resetForm()
  showEditor.value = true
}

function openEdit(preset: ModelPreset) {
  isEditing.value = true
  editingId.value = preset.id
  form.name = preset.name
  form.description = preset.description || ""
  form.model_name = preset.model_name || ""
  form.system_prompt = preset.system_prompt || ""
  form.temperature = preset.temperature ?? undefined
  form.max_tokens = preset.max_tokens ?? undefined
  form.top_p = preset.top_p ?? undefined
  form.force_tools = preset.force_tools
  form.is_public = preset.is_public
  form.tools = preset.tools || []
  form.knowledge_bases = preset.knowledge_bases || []
  form.variables = preset.variables || undefined
  toolsInput.value = (preset.tools || []).join(", ")
  kbInput.value = (preset.knowledge_bases || []).join(", ")
  showEditor.value = true
}

function closeEditor() {
  showEditor.value = false
}

function resetForm() {
  form.name = ""
  form.description = ""
  form.model_name = ""
  form.system_prompt = ""
  form.temperature = undefined
  form.max_tokens = undefined
  form.top_p = undefined
  form.force_tools = false
  form.is_public = false
  form.tools = []
  form.knowledge_bases = []
  form.variables = undefined
  toolsInput.value = ""
  kbInput.value = ""
}

function syncToolsArray() {
  form.tools = toolsInput.value
    .split(",")
    .map(s => s.trim())
    .filter(Boolean)
}

function syncKbArray() {
  form.knowledge_bases = kbInput.value
    .split(",")
    .map(s => s.trim())
    .filter(Boolean)
}

async function handleSave() {
  if (!form.name.trim()) return

  syncToolsArray()
  syncKbArray()

  try {
    if (isEditing.value && editingId.value) {
      await modelPresetsApi.update(editingId.value, {
        name: form.name,
        description: form.description || undefined,
        model_name: form.model_name || undefined,
        system_prompt: form.system_prompt || undefined,
        temperature: form.temperature,
        max_tokens: form.max_tokens,
        top_p: form.top_p,
        force_tools: form.force_tools,
        is_public: form.is_public,
        tools: form.tools.length ? form.tools : undefined,
        knowledge_bases: form.knowledge_bases.length ? form.knowledge_bases : undefined,
        variables: form.variables,
      } as any)
      showToast("预设已更新")
    } else {
      await modelPresetsApi.create({
        name: form.name,
        description: form.description || undefined,
        model_name: form.model_name || undefined,
        system_prompt: form.system_prompt || undefined,
        temperature: form.temperature,
        max_tokens: form.max_tokens,
        top_p: form.top_p,
        force_tools: form.force_tools,
        is_public: form.is_public,
        tools: form.tools.length ? form.tools : undefined,
        knowledge_bases: form.knowledge_bases.length ? form.knowledge_bases : undefined,
        variables: form.variables,
      } as any)
      showToast("预设已创建")
    }
    closeEditor()
    fetchList()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "保存失败", "error")
  }
}

async function handleDelete(preset: ModelPreset) {
  if (!confirm(`确定删除预设 "${preset.name}"？`)) return
  try {
    await modelPresetsApi.delete(preset.id)
    showToast(`预设 "${preset.name}" 已删除`)
    fetchList()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "删除失败", "error")
  }
}

async function handleApply(preset: ModelPreset) {
  try {
    const res = await modelPresetsApi.apply(preset.id)
    showToast(`已应用预设 "${preset.name}"（使用次数 +1）`)
    fetchList()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "应用失败", "error")
  }
}

async function handleResolve(preset: ModelPreset) {
  try {
    const res = await modelPresetsApi.resolve(preset.id)
    resolveResult.value = res.data
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "解析失败", "error")
  }
}

// ── Init ─────────────────────────────────────────────

onMounted(() => {
  fetchList()
})
</script>

<style scoped>
/* ── Page Layout ── */
.model-presets-page {
  padding: 24px 32px;
  height: 100%;
  overflow-y: auto;
  background: var(--color-ide-bg);
  color: var(--color-ide-fg);
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20px;
  gap: 16px;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
}

.page-desc {
  font-size: 13px;
  color: var(--color-ide-fg-muted);
}

/* ── Buttons ── */
.btn-primary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: 6px;
  background: var(--color-ide-accent);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: opacity 0.15s;
  white-space: nowrap;
}
.btn-primary:hover { opacity: 0.85; }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-ghost {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  border: 1px solid var(--color-ide-border);
  border-radius: 6px;
  background: transparent;
  color: var(--color-ide-fg);
  font-size: 13px;
  cursor: pointer;
}
.btn-ghost:hover { background: var(--color-ide-bg-hover); }

/* ── Toolbar ── */
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}

.search-box {
  position: relative;
  flex: 1;
  max-width: 360px;
}

.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--color-ide-fg-muted);
}

.search-input {
  width: 100%;
  padding: 8px 12px 8px 32px;
  border: 1px solid var(--color-ide-border);
  border-radius: 6px;
  background: var(--color-ide-bg-input);
  color: var(--color-ide-fg);
  font-size: 13px;
  outline: none;
}
.search-input::placeholder { color: var(--color-ide-fg-muted); }
.search-input:focus { border-color: var(--color-ide-accent); }

/* ── States ── */
.loading-state,
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 80px 0;
  color: var(--color-ide-fg-muted);
}

.spinner { animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }

.empty-icon { opacity: 0.3; }

/* ── Preset Grid ── */
.preset-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.preset-card {
  background: var(--color-ide-bg-panel);
  border: 1px solid var(--color-ide-border);
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: border-color 0.15s;
}
.preset-card:hover { border-color: var(--color-ide-accent); }
.preset-public { border-left: 3px solid var(--color-ide-accent); }

.card-header { display: flex; flex-direction: column; gap: 4px; }

.card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-name {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.badge-public {
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 10px;
  background: var(--color-ide-accent);
  color: #fff;
}

.card-desc {
  margin: 0;
  font-size: 12px;
  color: var(--color-ide-fg-muted);
  line-height: 1.4;
}

/* ── Meta ── */
.card-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.meta-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
}

.meta-label {
  color: var(--color-ide-fg-muted);
  min-width: 80px;
  flex-shrink: 0;
}

.meta-value {
  color: var(--color-ide-fg);
  word-break: break-all;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.chip {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 4px;
  background: var(--color-ide-bg-hover);
  font-size: 11px;
}

.chip-kb { background: rgba(99, 102, 241, 0.15); color: #818cf8; }

/* ── Card Actions ── */
.card-actions {
  display: flex;
  gap: 6px;
  margin-top: auto;
  padding-top: 8px;
  border-top: 1px solid var(--color-ide-border);
}

.btn-action {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border: 1px solid var(--color-ide-border);
  border-radius: 5px;
  background: transparent;
  color: var(--color-ide-fg);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.12s;
}
.btn-action:hover { background: var(--color-ide-bg-hover); }
.btn-apply:hover { color: #22c55e; border-color: #22c55e; }
.btn-resolve:hover { color: #a78bfa; border-color: #a78bfa; }
.btn-edit:hover { color: var(--color-ide-accent); border-color: var(--color-ide-accent); }
.btn-delete:hover { color: #ef4444; border-color: #ef4444; }

/* ── Pagination ── */
.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  margin-top: 24px;
}
.pagination button {
  padding: 6px 14px;
  border: 1px solid var(--color-ide-border);
  border-radius: 6px;
  background: transparent;
  color: var(--color-ide-fg);
  font-size: 13px;
  cursor: pointer;
}
.pagination button:hover:not(:disabled) { background: var(--color-ide-bg-hover); }
.pagination button:disabled { opacity: 0.4; cursor: not-allowed; }
.page-info { font-size: 13px; color: var(--color-ide-fg-muted); }

/* ── Modal ── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal-content {
  background: var(--color-ide-bg-panel);
  border: 1px solid var(--color-ide-border);
  border-radius: 10px;
  max-height: 85vh;
  overflow-y: auto;
  width: 90%;
}
.modal-lg { max-width: 640px; }
.modal-md { max-width: 560px; }

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-ide-border);
}
.modal-header h2 { margin: 0; font-size: 17px; }

.btn-close {
  border: none;
  background: transparent;
  color: var(--color-ide-fg-muted);
  font-size: 20px;
  cursor: pointer;
  line-height: 1;
}
.btn-close:hover { color: var(--color-ide-fg); }

.modal-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 20px;
  border-top: 1px solid var(--color-ide-border);
}

/* ── Form ── */
.form-section {
  border: 1px solid var(--color-ide-border);
  border-radius: 6px;
  padding: 14px;
  margin: 0;
}

.form-section legend {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-ide-fg-muted);
  padding: 0 6px;
}

.form-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}
.form-row:last-child { margin-bottom: 0; }

.form-label {
  font-size: 12px;
  color: var(--color-ide-fg-muted);
}

.required { color: #ef4444; }

.form-input,
.form-textarea {
  width: 100%;
  padding: 7px 10px;
  border: 1px solid var(--color-ide-border);
  border-radius: 5px;
  background: var(--color-ide-bg-input);
  color: var(--color-ide-fg);
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
}
.form-input:focus,
.form-textarea:focus { border-color: var(--color-ide-accent); }

.form-textarea { resize: vertical; }

.form-mono {
  font-family: "Cascadia Code", "Fira Code", monospace;
  font-size: 12px;
}

.form-row-3col {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 10px;
}
.form-col { display: flex; flex-direction: column; gap: 4px; }

.form-check { flex-direction: row; }
.form-check-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  cursor: pointer;
}

/* ── Resolve View ── */
.resolve-section { margin-bottom: 16px; }
.resolve-section h4 {
  margin: 0 0 6px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-ide-fg-muted);
}
.resolve-pre {
  margin: 0;
  padding: 10px 12px;
  border-radius: 6px;
  background: var(--color-ide-bg-input);
  font-size: 12px;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}
.resolve-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 16px;
  font-size: 13px;
}
.chip-group {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

/* ── Toast ── */
.toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  padding: 10px 20px;
  border-radius: 6px;
  font-size: 13px;
  z-index: 200;
  animation: slideUp 0.25s ease;
}
.toast.success { background: #16a34a; color: #fff; }
.toast.error { background: #dc2626; color: #fff; }

@keyframes slideUp {
  from { opacity: 0; transform: translateY(12px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
