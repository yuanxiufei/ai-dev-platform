<script setup lang="ts">
import { ref, reactive, onMounted, computed } from "vue"
import { Bot, Plus, Edit3, Trash2, Zap, FolderOpen, Search, X } from "lucide-vue-next"
import { listModes, createMode, updateMode, deleteMode, loadModesFile, activateMode } from "@/api/agentModes"
import type { AgentMode, ModeCreateRequest, ModeUpdateRequest } from "@/api/agentModes"

const modeList = ref<AgentMode[]>([])
const loading = ref(false)
const searchQuery = ref("")
const activateLoading = ref<string | null>(null)
const errorMsg = ref("")

const showModal = ref(false)
const editingSlug = ref<string | null>(null)
const modalForm = reactive<ModeCreateRequest>({ slug: "", name: "", description: "", role_instructions: "", tools: [], tool_categories: [], preferred_model: "", temperature: 0.7, max_turns: 10, icon: "🤖", color: "#6366f1" })
const toolsInput = ref("")
const categoriesInput = ref("")

const activateResult = ref<any>(null)
const showActivatePanel = ref(false)

const filteredModes = computed(() => {
  if (!searchQuery.value) return modeList.value
  const q = searchQuery.value.toLowerCase()
  return modeList.value.filter(m => m.name.toLowerCase().includes(q) || m.slug.toLowerCase().includes(q) || m.description.toLowerCase().includes(q))
})

const colorPresets = ["#6366f1", "#8b5cf6", "#ec4899", "#ef4444", "#f59e0b", "#22c55e", "#06b6d4", "#3b82f6"]

async function fetchModes() {
  loading.value = true; errorMsg.value = ""
  try { const res = await listModes(); modeList.value = res.data.data || [] } catch (e: any) { errorMsg.value = e.response?.data?.detail || e.message || "加载失败" } finally { loading.value = false }
}

function openCreateModal() {
  editingSlug.value = null; modalForm.slug = ""; modalForm.name = ""; modalForm.description = ""; modalForm.role_instructions = ""
  modalForm.tools = []; modalForm.tool_categories = []; modalForm.preferred_model = ""; modalForm.temperature = 0.7
  modalForm.max_turns = 10; modalForm.icon = "🤖"; modalForm.color = "#6366f1"; toolsInput.value = ""; categoriesInput.value = ""; showModal.value = true
}

function openEditModal(mode: AgentMode) {
  editingSlug.value = mode.slug; modalForm.slug = mode.slug; modalForm.name = mode.name; modalForm.description = mode.description
  modalForm.role_instructions = mode.role_instructions; modalForm.tools = [...mode.tools]; modalForm.tool_categories = [...mode.tool_categories]
  modalForm.preferred_model = mode.preferred_model; modalForm.temperature = mode.temperature; modalForm.max_turns = mode.max_turns
  modalForm.icon = mode.icon; modalForm.color = mode.color; toolsInput.value = mode.tools.join(", "); categoriesInput.value = mode.tool_categories.join(", "); showModal.value = true
}

async function handleSave() {
  errorMsg.value = ""
  modalForm.tools = toolsInput.value.split(",").map(s => s.trim()).filter(Boolean)
  modalForm.tool_categories = categoriesInput.value.split(",").map(s => s.trim()).filter(Boolean)
  try {
    if (editingSlug.value) {
      const payload: ModeUpdateRequest = { name: modalForm.name, description: modalForm.description, role_instructions: modalForm.role_instructions, tools: modalForm.tools, tool_categories: modalForm.tool_categories, preferred_model: modalForm.preferred_model, temperature: modalForm.temperature, max_turns: modalForm.max_turns, icon: modalForm.icon, color: modalForm.color }
      await updateMode(editingSlug.value, payload)
    } else { await createMode({ ...modalForm }) }
    showModal.value = false; await fetchModes()
  } catch (e: any) { errorMsg.value = e.response?.data?.detail || e.message || "保存失败" }
}

async function handleDelete(slug: string) {
  if (!confirm(`确定删除模式 "${slug}"？`)) return
  try { await deleteMode(slug); await fetchModes() } catch (e: any) { errorMsg.value = e.response?.data?.detail || e.message || "删除失败" }
}

async function handleActivate(slug: string) {
  activateLoading.value = slug; errorMsg.value = ""
  try { const res = await activateMode(slug); activateResult.value = res.data.data; showActivatePanel.value = true } catch (e: any) { errorMsg.value = e.response?.data?.detail || e.message || "激活失败" } finally { activateLoading.value = null }
}

async function handleLoadFile() {
  if (!confirm("从 .roomodes 文件加载模式？")) return
  errorMsg.value = ""
  try { const res = await loadModesFile(); alert(res.data.message); await fetchModes() } catch (e: any) { errorMsg.value = e.response?.data?.detail || e.message || "加载失败" }
}

onMounted(fetchModes)
</script>

<template>
  <div class="g-container">
    <div class="g-header">
      <div class="g-header-left"><Bot :size="22" class="g-header-icon" /><h1 class="g-header-title">Agent 模式</h1><span class="g-header-sub">自定义行为模式</span></div>
      <div class="g-header-actions">
        <button class="g-btn g-btn-ghost" @click="handleLoadFile"><FolderOpen :size="15" />加载文件</button>
        <button class="g-btn g-btn-primary" @click="openCreateModal"><Plus :size="15" />创建模式</button>
      </div>
    </div>

    <div class="g-search-bar"><Search :size="14" class="g-search-icon" /><input v-model="searchQuery" class="g-search-input" placeholder="搜索模式..." /></div>

    <div v-if="errorMsg" class="g-error-msg">{{ errorMsg }}<button class="g-error-close" @click="errorMsg = ''"><X :size="14" /></button></div>

    <!-- 激活结果 -->
    <div v-if="showActivatePanel && activateResult" class="g-activate-panel">
      <div class="g-activate-header"><Zap :size="16" />激活 — {{ activateResult.mode?.name }}<button class="g-activate-close" @click="showActivatePanel = false"><X :size="14" /></button></div>
      <div class="g-activate-body">
        <div class="g-act-item"><span class="g-act-label">指令</span><span class="g-act-mono">{{ activateResult.config?.instructions }}</span></div>
        <div class="g-act-item"><span class="g-act-label">工具</span><div class="g-act-tags"><span v-for="t in activateResult.config?.tools" :key="t" class="g-act-tag">{{ t }}</span></div></div>
        <div class="g-act-item"><span class="g-act-label">模型</span><span>{{ activateResult.config?.preferred_model || "默认" }}</span></div>
        <div class="g-act-item"><span class="g-act-label">温度 / 最大轮数</span><span>{{ activateResult.mode?.temperature }} / {{ activateResult.config?.max_turns }}</span></div>
      </div>
    </div>

    <div v-if="loading" class="g-loading">加载中...</div>

    <div v-else class="g-grid">
      <div v-for="mode in filteredModes" :key="mode.slug" :class="['g-card', { 'g-preset': mode.is_preset }]" :style="{ borderLeftColor: mode.color }">
        <div class="g-card-header"><span class="g-card-icon">{{ mode.icon }}</span><div class="g-card-title"><span class="g-card-name">{{ mode.name }}</span><span v-if="mode.is_preset" class="g-preset-badge">预设</span></div></div>
        <p v-if="mode.description" class="g-card-desc">{{ mode.description }}</p>
        <div class="g-card-meta">
          <span>模型: {{ mode.preferred_model || "默认" }}</span>
          <span>温度: {{ mode.temperature }}</span>
          <span>工具: {{ mode.tools.length }}</span>
        </div>
        <div class="g-card-footer">
          <button class="g-card-btn g-card-btn-primary" :disabled="activateLoading === mode.slug" @click="handleActivate(mode.slug)"><Zap :size="13" />{{ activateLoading === mode.slug ? "激活中..." : "激活" }}</button>
          <button class="g-card-btn" @click="openEditModal(mode)" :disabled="!!mode.is_preset"><Edit3 :size="13" /></button>
          <button class="g-card-btn g-card-btn-danger" @click="handleDelete(mode.slug)" :disabled="!!mode.is_preset"><Trash2 :size="13" /></button>
        </div>
      </div>
    </div>

    <div v-if="!loading && filteredModes.length === 0" class="g-empty-page">暂无模式数据</div>

    <!-- 弹窗 -->
    <Teleport to="body">
      <div v-if="showModal" class="g-overlay" @click.self="showModal = false">
        <div class="g-modal">
          <div class="g-modal-header"><h3>{{ editingSlug ? "编辑模式" : "创建模式" }}</h3><button class="g-modal-close" @click="showModal = false"><X :size="18" /></button></div>
          <div class="g-modal-body">
            <div class="g-form-row">
              <label class="g-form-col"><span>图标</span><input v-model="modalForm.icon" class="g-input" maxlength="4" size="4" /></label>
              <label class="g-form-col"><span>颜色</span><div class="g-color-row"><input v-model="modalForm.color" type="color" class="g-color-picker" /><span v-for="c in colorPresets" :key="c" class="g-color-dot" :style="{ background: c }" @click="modalForm.color = c" /></div></label>
            </div>
            <label class="g-form-field"><span>唯一标识 (slug)</span><input v-model="modalForm.slug" class="g-input" :disabled="!!editingSlug" placeholder="my-custom-mode" /></label>
            <label class="g-form-field"><span>名称</span><input v-model="modalForm.name" class="g-input" placeholder="模式名称" /></label>
            <label class="g-form-field"><span>描述</span><textarea v-model="modalForm.description" class="g-input g-textarea" rows="2" placeholder="简短描述" /></label>
            <label class="g-form-field"><span>角色指令</span><textarea v-model="modalForm.role_instructions" class="g-input g-textarea" rows="3" placeholder="Agent 角色指令文本" /></label>
            <div class="g-form-row">
              <label class="g-form-col"><span>工具列表 (逗号分隔)</span><input v-model="toolsInput" class="g-input" placeholder="read_file, write_to_file" /></label>
              <label class="g-form-col"><span>工具类别</span><input v-model="categoriesInput" class="g-input" placeholder="file, search" /></label>
            </div>
            <div class="g-form-row">
              <label class="g-form-col"><span>偏好模型</span><input v-model="modalForm.preferred_model" class="g-input" placeholder="模型名或留空" /></label>
              <label class="g-form-col"><span>温度</span><input v-model.number="modalForm.temperature" type="number" class="g-input" min="0" max="2" step="0.1" /></label>
              <label class="g-form-col"><span>最大轮数</span><input v-model.number="modalForm.max_turns" type="number" class="g-input" min="1" max="100" /></label>
            </div>
            <div v-if="errorMsg" class="g-error-msg g-modal-error">{{ errorMsg }}</div>
          </div>
          <div class="g-modal-footer">
            <button class="g-btn g-btn-ghost" @click="showModal = false">取消</button>
            <button class="g-btn g-btn-primary" @click="handleSave">保存</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.g-container { padding: 24px; max-width: 1100px; margin: 0 auto; }
.g-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }
.g-header-left { display: flex; align-items: center; gap: 10px; }
.g-header-icon { color: var(--color-ide-accent, #a855f7); }
.g-header-title { font-size: 20px; font-weight: 600; color: var(--color-ide-fg, #e2e8f0); margin: 0; }
.g-header-sub { font-size: 13px; color: var(--color-ide-fg-secondary, #94a3b8); }
.g-header-actions { display: flex; gap: 8px; }
.g-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border: none; border-radius: 7px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.15s; }
.g-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.g-btn-primary { background: var(--color-ide-accent, #a855f7); color: #fff; }
.g-btn-ghost { background: transparent; color: var(--color-ide-fg-secondary, #94a3b8); border: 1px solid var(--color-ide-border, #334155); }
.g-btn-ghost:hover { color: var(--color-ide-fg, #e2e8f0); border-color: var(--color-ide-fg-secondary, #94a3b8); }
.g-search-bar { position: relative; margin-bottom: 20px; }
.g-search-icon { position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--color-ide-fg-secondary, #94a3b8); }
.g-search-input { width: 100%; padding: 9px 12px 9px 34px; border: 1px solid var(--color-ide-border, #334155); border-radius: 8px; background: var(--color-ide-bg-secondary, #1e293b); color: var(--color-ide-fg, #e2e8f0); font-size: 13px; outline: none; box-sizing: border-box; }
.g-search-input:focus { border-color: var(--color-ide-accent, #a855f7); }
.g-error-msg { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; margin-bottom: 16px; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 7px; color: #ef4444; font-size: 13px; }
.g-error-close { background: none; border: none; color: #ef4444; cursor: pointer; padding: 2px; }
.g-loading { color: var(--color-ide-fg-secondary, #94a3b8); font-size: 13px; padding: 40px 0; }
.g-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
.g-card { background: var(--color-ide-bg-secondary, #1e293b); border: 1px solid var(--color-ide-border, #334155); border-left: 3px solid #6366f1; border-radius: 10px; padding: 16px; transition: all 0.15s; }
.g-card:hover { border-color: var(--color-ide-accent, #a855f7); }
.g-card.g-preset { opacity: 0.8; }
.g-card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.g-card-icon { font-size: 24px; }
.g-card-title { display: flex; align-items: center; gap: 6px; }
.g-card-name { font-size: 15px; font-weight: 600; color: var(--color-ide-fg, #e2e8f0); }
.g-preset-badge { font-size: 10px; padding: 1px 6px; border-radius: 8px; background: var(--color-ide-accent, #a855f7); color: #fff; }
.g-card-desc { font-size: 12px; color: var(--color-ide-fg-secondary, #94a3b8); margin: 0 0 10px 0; line-height: 1.5; }
.g-card-meta { display: flex; gap: 12px; margin-bottom: 12px; font-size: 11px; color: var(--color-ide-fg-secondary, #94a3b8); }
.g-card-footer { display: flex; gap: 6px; }
.g-card-btn { display: inline-flex; align-items: center; gap: 4px; padding: 5px 10px; border: 1px solid var(--color-ide-border, #334155); border-radius: 6px; background: var(--color-ide-bg-primary, #0f172a); color: var(--color-ide-fg-secondary, #94a3b8); font-size: 12px; cursor: pointer; }
.g-card-btn:hover { color: var(--color-ide-fg, #e2e8f0); border-color: var(--color-ide-fg-secondary, #94a3b8); }
.g-card-btn-primary { background: var(--color-ide-accent, #a855f7); color: #fff; border-color: transparent; }
.g-card-btn-primary:hover { filter: brightness(1.1); }
.g-card-btn-danger:hover { color: #ef4444; border-color: #ef4444; }
.g-empty-page { text-align: center; padding: 60px 0; color: var(--color-ide-fg-secondary, #94a3b8); font-size: 14px; }

/* 激活面板 */
.g-activate-panel { background: var(--color-ide-bg-secondary, #1e293b); border: 1px solid var(--color-ide-accent, #a855f7); border-radius: 10px; margin-bottom: 16px; overflow: hidden; }
.g-activate-header { display: flex; align-items: center; gap: 8px; padding: 12px 16px; background: var(--color-ide-accent, #a855f7); color: #fff; font-size: 14px; font-weight: 600; }
.g-activate-close { margin-left: auto; background: none; border: none; color: #fff; cursor: pointer; }
.g-activate-body { padding: 14px 16px; }
.g-act-item { display: flex; gap: 12px; padding: 6px 0; font-size: 13px; color: var(--color-ide-fg, #e2e8f0); }
.g-act-label { width: 60px; flex-shrink: 0; color: var(--color-ide-fg-secondary, #94a3b8); font-size: 12px; }
.g-act-mono { font-family: monospace; font-size: 12px; max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.g-act-tags { display: flex; flex-wrap: wrap; gap: 4px; }
.g-act-tag { padding: 2px 8px; border-radius: 4px; background: var(--color-ide-bg-primary, #0f172a); font-size: 11px; font-family: monospace; }

/* 弹窗 */
.g-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.g-modal { background: var(--color-ide-bg-secondary, #1e293b); border: 1px solid var(--color-ide-border, #334155); border-radius: 12px; width: 580px; max-width: 90vw; max-height: 85vh; overflow-y: auto; }
.g-modal-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--color-ide-border, #334155); }
.g-modal-header h3 { margin: 0; font-size: 16px; color: var(--color-ide-fg, #e2e8f0); }
.g-modal-close { background: none; border: none; color: var(--color-ide-fg-secondary, #94a3b8); cursor: pointer; }
.g-modal-body { padding: 20px; display: flex; flex-direction: column; gap: 14px; }
.g-modal-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--color-ide-border, #334155); }
.g-modal-error { margin-top: 4px; }
.g-form-field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--color-ide-fg-secondary, #94a3b8); }
.g-form-row { display: flex; gap: 12px; }
.g-form-col { flex: 1; display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--color-ide-fg-secondary, #94a3b8); }
.g-input { padding: 8px 10px; border: 1px solid var(--color-ide-border, #334155); border-radius: 6px; background: var(--color-ide-bg-primary, #0f172a); color: var(--color-ide-fg, #e2e8f0); font-size: 13px; outline: none; box-sizing: border-box; width: 100%; }
.g-input:focus { border-color: var(--color-ide-accent, #a855f7); }
.g-input:disabled { opacity: 0.5; }
.g-textarea { resize: vertical; min-height: 50px; font-family: inherit; }
.g-color-row { display: flex; align-items: center; gap: 6px; }
.g-color-picker { width: 28px; height: 28px; border: none; border-radius: 4px; cursor: pointer; padding: 0; }
.g-color-dot { width: 16px; height: 16px; border-radius: 50%; cursor: pointer; border: 2px solid transparent; transition: all 0.1s; }
.g-color-dot:hover { border-color: var(--color-ide-fg, #e2e8f0); transform: scale(1.2); }
</style>
