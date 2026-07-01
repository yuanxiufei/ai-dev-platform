<script setup lang="ts">
import {
  Bot, ChevronDown, ChevronRight, Copy, Edit3, FileText, Globe, Loader2, Plus, RefreshCw,
  Search, Sparkles, Terminal, Trash2, Wrench
} from "lucide-vue-next"
import { computed, onMounted, ref } from "vue"
import ToggleSwitch from "@/components/ToggleSwitch.vue"
import {
  type AgentCreatePayload,
  type AgentItem,
  type AgentUpdatePayload,
  cloneAgent,
  createAgent,
  deleteAgent,
  getToolsMetadata,
  listAgents,
  type MCPStatus,
  type ToolCategory,
  toggleAgent,
  updateAgent,
} from "@/api/agents-mgmt"

// ── Tab state ──────────────────────────────────────────
type TabScope = "user" | "project"
const activeTab = ref<TabScope>("user")

const agents = ref<AgentItem[]>([])
const loading = ref(true)
const toast = ref("")

// 筛选模式下拉
const filterMode = ref("")

// ── Tools Metadata ─────────────────────────────────────
const toolCategories = ref<ToolCategory[]>([])
const mcpStatus = ref<MCPStatus>({ connected: false, servers: [], tools: [] })
const toolsMetaLoaded = ref(false)

// ── Dialog state ───────────────────────────────────────
const showCreate = ref(false)
const editAgent = ref<AgentItem | null>(null)
const expandedAgent = ref<string | null>(null)

// ── Available Models ───────────────────────────────────
const availableModels = [
  { value: "auto", label: "Auto (自动选择)", provider: "系统" },
  { value: "openai-gpt4o", label: "GPT-4o", provider: "OpenAI" },
  { value: "openai-o3", label: "o3", provider: "OpenAI" },
  { value: "claude-sonnet", label: "Claude Sonnet 4", provider: "Anthropic" },
  { value: "deepseek-v3", label: "DeepSeek-V3", provider: "DeepSeek" },
  { value: "qwen25-coder-7b", label: "Qwen2.5-Coder-7B", provider: "本地" },
  { value: "gemma-31b", label: "Gemma-3-1B", provider: "本地" },
]

// ── 搜索 ───────────────────────────────────────────────
const searchQuery = ref("")

// ── 表单 ───────────────────────────────────────────────
function defaultForm(): AgentCreatePayload & {
  tool_cats_map?: Record<string, boolean>
} {
  return {
    name: "",
    description: "",
    mode: "craft",
    agentic_mode: "agentic",
    model: "auto",
    system_prompt: "",
    tools: ["code-search", "filesystem-read"],
    tool_categories: ["read", "edit", "execute"],
    mcp_servers: [],
    auto_run: true,
    enabled: true,
    scope: "user",
  }
}
const form = ref<ReturnType<typeof defaultForm>>(defaultForm())

const formExpandedCategories = ref<Record<string, boolean>>({})

function toggleFormCategory(catId: string) {
  if (!form.value.tool_categories) form.value.tool_categories = []
  const idx = form.value.tool_categories.indexOf(catId)
  if (idx === -1) {
    form.value.tool_categories.push(catId)
    formExpandedCategories.value[catId] = true
  } else {
    form.value.tool_categories.splice(idx, 1)
  }
}

function toggleFormTool(toolId: string) {
  if (!form.value.tools) form.value.tools = []
  const idx = form.value.tools.indexOf(toolId)
  if (idx === -1) form.value.tools.push(toolId)
  else form.value.tools.splice(idx, 1)
}

function isCatExpanded(catId: string) {
  if (catId in formExpandedCategories.value)
    return formExpandedCategories.value[catId]
  return false
}

function isFormToolEnabled(toolId: string): boolean {
  return (form.value.tools || []).includes(toolId)
}

function mcpToolId(server: string, toolName: string) {
  return `mcp:${server}:${toolName}`
}

function isMcpToolEnabled(server: string, toolName: string): boolean {
  return (form.value.mcp_servers || []).includes(mcpToolId(server, toolName))
}

function toggleMcpTool(server: string, toolName: string) {
  if (!form.value.mcp_servers) form.value.mcp_servers = []
  const id = mcpToolId(server, toolName)
  const idx = form.value.mcp_servers.indexOf(id)
  if (idx === -1) form.value.mcp_servers.push(id)
  else form.value.mcp_servers.splice(idx, 1)
}

// ── Computed ───────────────────────────────────────────
const filteredAgents = computed(() => {
  let list = agents.value.filter((a) => a.scope === activeTab.value)
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        (a.description || "").toLowerCase().includes(q),
    )
  }
  if (filterMode.value) {
    list = list.filter((a) => a.mode === filterMode.value)
  }
  return list
})

const catIconMap: Record<string, any> = {
  FileText,
  Edit3,
  Terminal,
  Globe,
  Sparkles,
  Wrench,
}

// ── 生命周期 ───────────────────────────────────────────
onMounted(async () => {
  await Promise.all([fetchAgents(), fetchToolsMetadata()])
})

async function fetchAgents() {
  loading.value = true
  try {
    const res = await listAgents()
    agents.value = res.data?.data || []
  } catch {
    /* */
  } finally {
    loading.value = false
  }
}

async function fetchToolsMetadata() {
  try {
    const res = await getToolsMetadata()
    if (res.data) {
      toolCategories.value = res.data.categories || []
      mcpStatus.value = res.data.mcp || {
        connected: false,
        servers: [],
        tools: [],
      }
    }
    toolsMetaLoaded.value = true
  } catch {
    toolsMetaLoaded.value = true
  }
}

// ── Toast ──────────────────────────────────────────────
function showToast(msg: string) {
  toast.value = msg
  setTimeout(() => {
    toast.value = ""
  }, 3000)
}

// ── CRUD Handlers ──────────────────────────────────────
async function handleCreate() {
  if (!form.value.name || !form.value.system_prompt) return
  try {
    await createAgent({ ...form.value, scope: activeTab.value })
    showCreate.value = false
    form.value = defaultForm()
    formExpandedCategories.value = {}
    showToast("Agent 已创建")
    await fetchAgents()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "创建失败")
  }
}

async function saveEdit() {
  if (!editAgent.value) return
  try {
    const { id, created_at, updated_at, ...rest } = editAgent.value
    const payload: AgentUpdatePayload = { ...rest }
    await updateAgent(id, payload)
    editAgent.value = null
    showToast("Agent 已更新")
    await fetchAgents()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "更新失败")
  }
}

async function handleDelete(id: string) {
  if (!confirm("确定删除此 Agent？")) return
  try {
    await deleteAgent(id)
    showToast("Agent 已删除")
    await fetchAgents()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "删除失败")
  }
}

async function handleToggle(agent: AgentItem) {
  try {
    await toggleAgent(agent.id)
    agent.enabled = !agent.enabled
  } catch {
    /* */
  }
}

async function handleClone(agent: AgentItem) {
  try {
    await cloneAgent(agent.id)
    showToast("Agent 已克隆")
    await fetchAgents()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "克隆失败")
  }
}

function startEdit(agent: AgentItem) {
  editAgent.value = { ...agent }
}

function getModelLabel(modelVal: string) {
  return availableModels.find((m) => m.value === modelVal)?.label || modelVal
}
function getModelProvider(modelVal: string) {
  return availableModels.find((m) => m.value === modelVal)?.provider || "系统"
}

// 编辑表单中工具的处理（复用 form 的函数逻辑）
function editToggleCategory(catId: string) {
  if (!editAgent.value) return
  const cats = editAgent.value.tool_categories || []
  const idx = cats.indexOf(catId)
  if (idx === -1) cats.push(catId)
  else cats.splice(idx, 1)
  editAgent.value.tool_categories = [...cats]
}

function editToggleTool(toolId: string) {
  if (!editAgent.value) return
  const tools = editAgent.value.tools || []
  const idx = tools.indexOf(toolId)
  if (idx === -1) tools.push(toolId)
  else tools.splice(idx, 1)
  editAgent.value.tools = [...tools]
}

function editIsToolEnabled(toolId: string): boolean {
  return (editAgent.value?.tools || []).includes(toolId)
}
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Toast -->
    <Transition name="toast">
      <div v-if="toast" class="fixed top-6 left-1/2 -translate-x-1/2 z-50 px-5 py-2.5 rounded-xl text-sm font-medium bg-green-500/15 border border-green-500/25 text-green-400 backdrop-blur-xl shadow-xl">
        {{ toast }}
      </div>
    </Transition>

    <!-- Header -->
    <div class="flex items-center justify-between px-8 pt-8 pb-6 border-b border-[var(--color-ide-border)]">
      <div>
        <h1 class="text-2xl font-bold text-white flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-500/20 to-purple-500/10 border border-violet-500/20 flex items-center justify-center">
            <Bot class="w-5 h-5 text-violet-400" />
          </div>
          Agent 管理
        </h1>
        <p class="text-sm text-[var(--color-ide-text-dim)] mt-1.5 ml-[3.25rem]">创建和管理 AI Agent，配置模型、工具和系统提示词</p>
      </div>
      <div class="flex items-center gap-3">
        <!-- 搜索 -->
        <div class="relative">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--color-ide-text-dim)]" />
          <input
            v-model="searchQuery"
            placeholder="搜索 Agent..."
            class="w-52 pl-9 pr-4 py-2 rounded-xl bg-[var(--color-ide-surface-hover)] border border-[var(--color-ide-border)] text-sm text-white placeholder-[var(--color-ide-text-dim)] focus:outline-none focus:border-violet-500/30 transition-all"
          />
        </div>
        <!-- 模式筛选 -->
        <select
          v-model="filterMode"
          class="px-3 py-2 rounded-xl bg-[var(--color-ide-surface-hover)] border border-[var(--color-ide-border)] text-sm text-[var(--color-ide-text-dim)] focus:outline-none focus:border-violet-500/30 transition-all"
        >
          <option value="">全部模式</option>
          <option value="craft">Craft</option>
          <option value="ask">Ask</option>
          <option value="plan">Plan</option>
        </select>
        <button
          @click="showCreate = true"
          class="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium transition-colors shadow-lg shadow-brand-500/15"
        >
          <Plus class="w-4 h-4" />
          创建 Agent
        </button>
      </div>
    </div>

    <!-- 标签栏: 用户Agent / 项目Agent -->
    <div class="px-8 pt-4 pb-3 flex items-center gap-1 border-b border-[var(--color-ide-border)]">
      <button
        v-for="tab in [
          { id: 'user' as TabScope, label: '用户 Agent', icon: Users, desc: '个人空间中生效' },
          { id: 'project' as TabScope, label: '项目 Agent', icon: FolderGit2, desc: '绑定特定项目中生效' },
        ]"
        :key="tab.id"
        @click="activeTab = tab.id"
        :class="[
          'flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-all duration-200',
          activeTab === tab.id
            ? 'bg-violet-500/10 text-violet-400 border border-violet-500/20'
            : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] border border-transparent',
        ]"
      >
        <component :is="tab.icon" class="w-4 h-4" />
        {{ tab.label }}
      </button>
      <div class="ml-auto text-xs text-[var(--color-ide-text-dim)] flex items-center gap-2">
        <div class="flex items-center gap-1.5">
          <div class="w-1.5 h-1.5 rounded-full bg-green-400" />
          <span>{{ filteredAgents.filter(a => a.enabled).length }} 已启用</span>
        </div>
        <span class="text-gray-700">/</span>
        <span>{{ filteredAgents.length }} 个</span>
      </div>
    </div>

    <!-- Main Content -->
    <div class="flex-1 overflow-y-auto">
      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-24">
        <Loader2 class="w-8 h-8 animate-spin text-violet-400" />
      </div>

      <!-- Empty -->
      <div v-else-if="!filteredAgents.length" class="flex flex-col items-center justify-center py-24 text-[var(--color-ide-text-dim)]">
        <Bot class="w-12 h-12 mb-4 opacity-30" />
        <p class="text-sm mb-1">{{ activeTab === 'user' ? '还没有用户 Agent' : '还没有项目 Agent' }}</p>
        <p class="text-xs text-gray-700 mb-4">点击右上角"创建 Agent"开始使用</p>
        <button
          @click="showCreate = true"
          class="flex items-center gap-2 px-4 py-2 rounded-xl bg-violet-500/15 text-violet-400 hover:bg-violet-500/25 text-sm transition-colors"
        >
          <Plus class="w-4 h-4" /> 创建第一个 Agent
        </button>
      </div>

      <!-- Agent Cards -->
      <div v-else class="p-6 space-y-4">
        <div
          v-for="agent in filteredAgents"
          :key="agent.id"
          :class="[
            'rounded-2xl border transition-all duration-200',
            expandedAgent === agent.id
              ? 'border-violet-500/20 bg-[var(--color-ide-surface-hover)]'
              : agent.enabled
                ? 'border-[var(--color-ide-border)] bg-[var(--color-ide-surface-hover)] hover:border-[var(--color-ide-border)]'
                : 'border-[var(--color-ide-border)] bg-[var(--color-ide-surface)] opacity-60',
          ]"
        >
          <!-- Card Header -->
          <div class="p-5 flex items-start gap-4 cursor-pointer" @click="expandedAgent = expandedAgent === agent.id ? null : agent.id">
            <!-- Avatar -->
            <div class="w-11 h-11 rounded-xl bg-gradient-to-br from-violet-500/20 to-purple-500/10 border border-violet-500/20 flex items-center justify-center shrink-0">
              <Bot class="w-5 h-5 text-violet-400" />
            </div>

            <!-- Info -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-3 mb-1">
                <h3 class="text-sm font-semibold text-white">{{ agent.name }}</h3>
                <!-- Mode Badge -->
                <span :class="[
                  'text-[10px] px-2 py-0.5 rounded-full font-medium border',
                  agent.mode === 'craft'
                    ? 'bg-orange-500/10 text-orange-400 border-orange-500/20'
                    : agent.mode === 'ask'
                      ? 'bg-blue-500/10 text-blue-400 border-blue-500/20'
                      : 'bg-green-500/10 text-green-400 border-green-500/20',
                ]">
                  {{ agent.mode === 'craft' ? 'Craft' : agent.mode === 'ask' ? 'Ask' : 'Plan' }}
                </span>
                <!-- Agentic/Manual Badge -->
                <span :class="[
                  'text-[10px] px-2 py-0.5 rounded-full font-medium border',
                  agent.agentic_mode === 'agentic'
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                    : 'bg-gray-500/10 text-[var(--color-ide-text-dim)] border-gray-500/20',
                ]">
                  <Zap class="w-2.5 h-2.5 inline mr-0.5" />
                  {{ agent.agentic_mode === 'agentic' ? 'Agentic' : 'Manual' }}
                </span>
                <!-- Auto Run -->
                <span :class="[
                  'text-[10px] px-2 py-0.5 rounded-full font-medium border',
                  agent.auto_run
                    ? 'bg-teal-500/10 text-teal-400 border-teal-500/20'
                    : 'bg-gray-500/10 text-[var(--color-ide-text-dim)] border-gray-500/20',
                ]">
                  {{ agent.auto_run ? 'Auto Run' : 'Manual Run' }}
                </span>
                <!-- Provider -->
                <span class="text-[10px] px-2 py-0.5 rounded-full bg-[var(--color-ide-surface-hover)] border border-[var(--color-ide-border)] text-[var(--color-ide-text-dim)]">{{ getModelProvider(agent.model) }}</span>
                <!-- Date -->
                <span class="text-[10px] text-gray-700 ml-auto">{{ agent.created_at?.slice(0, 10) || '-' }}</span>
              </div>
              <p class="text-xs text-[var(--color-ide-text-dim)] line-clamp-2">{{ agent.description || '无描述' }}</p>
            </div>

            <!-- Actions -->
            <div class="flex items-center gap-1 shrink-0" @click.stop>
              <ToggleSwitch :model-value="agent.enabled" size="md" @update:model-value="handleToggle(agent)" />
              <button
                @click.stop="expandedAgent = expandedAgent === agent.id ? null : agent.id"
                class="p-1.5 rounded-lg text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
              >
                <ChevronDown :class="['w-4 h-4 transition-transform duration-200', expandedAgent === agent.id && 'rotate-180']" />
              </button>
            </div>
          </div>

          <!-- Expanded Detail -->
          <Transition name="expand">
            <div v-if="expandedAgent === agent.id" class="border-t border-[var(--color-ide-border)] px-5 py-4 space-y-5">
              <!-- System Prompt -->
              <div>
                <p class="text-[11px] font-medium text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-2 flex items-center gap-2">
                  <Brain class="w-3.5 h-3.5" /> System Prompt
                </p>
                <div class="p-3 rounded-xl bg-[var(--color-ide-surface-hover)] border border-[var(--color-ide-border)]">
                  <pre class="text-xs text-[var(--color-ide-text-dim)] whitespace-pre-wrap font-mono leading-relaxed">{{ agent.system_prompt }}</pre>
                </div>
              </div>

              <!-- Model -->
              <div class="flex items-center gap-2">
                <p class="text-[11px] font-medium text-[var(--color-ide-text-dim)] uppercase tracking-wider">模型:</p>
                <span class="text-xs text-white bg-[var(--color-ide-surface-hover)] border border-[var(--color-ide-border)] px-2.5 py-1 rounded-lg">
                  <Cpu class="w-3 h-3 inline mr-1 text-violet-400" />
                  {{ getModelLabel(agent.model) }}
                  <span class="text-[var(--color-ide-text-dim)] ml-1 text-[10px]">({{ getModelProvider(agent.model) }})</span>
                </span>
              </div>

              <!-- Agentic Mode -->
              <div class="flex items-center gap-2">
                <p class="text-[11px] font-medium text-[var(--color-ide-text-dim)] uppercase tracking-wider">Agent 模式:</p>
                <span :class="[
                  'text-xs px-2.5 py-1 rounded-lg border',
                  agent.agentic_mode === 'agentic'
                    ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                    : 'bg-gray-500/10 text-[var(--color-ide-text-dim)] border-gray-500/20',
                ]">
                  <Zap class="w-3 h-3 inline mr-1" />
                  {{ agent.agentic_mode === 'agentic' ? 'Agentic (自主运行)' : 'Manual (手动触发)' }}
                </span>
              </div>

              <!-- Auto Run -->
              <div class="flex items-center gap-2">
                <p class="text-[11px] font-medium text-[var(--color-ide-text-dim)] uppercase tracking-wider">Auto Run:</p>
                <span :class="[
                  'text-xs px-2.5 py-1 rounded-lg border',
                  agent.auto_run
                    ? 'bg-teal-500/10 text-teal-400 border-teal-500/20'
                    : 'bg-gray-500/10 text-[var(--color-ide-text-dim)] border-gray-500/20',
                ]">
                  <component :is="agent.auto_run ? Play : Pause" class="w-3 h-3 inline mr-1" />
                  {{ agent.auto_run ? 'Enabled' : 'Disabled' }}
                </span>
              </div>

              <!-- Tools Built-In -->
              <div>
                <p class="text-[11px] font-medium text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-3 flex items-center gap-2">
                  <Wrench class="w-3.5 h-3.5" /> Tools Built-In {{ (agent.tools || []).length }}
                </p>
                <div class="space-y-2">
                  <div
                    v-for="cat in toolCategories"
                    :key="cat.id"
                    class="rounded-xl border border-[var(--color-ide-border)] bg-[var(--color-ide-surface)] overflow-hidden"
                  >
                    <button
                      @click="editToggleCategory(cat.id)"
                      :class="[
                        'w-full flex items-center gap-3 px-3 py-2.5 text-xs transition-colors',
                        (agent.tool_categories || []).includes(cat.id)
                          ? 'bg-violet-500/8 text-violet-400'
                          : 'text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]',
                      ]"
                    >
                      <component :is="catIconMap[cat.icon] || Wrench" class="w-3.5 h-3.5 shrink-0" />
                      <span class="font-medium">{{ cat.label }}</span>
                      <span class="text-gray-700 ml-auto text-[10px]">{{ cat.tools.filter(t => (agent.tools || []).includes(t.id)).length }}/{{ cat.tools.length }}</span>
                    </button>
                  </div>
                </div>
              </div>

              <!-- MCP 工具 -->
              <div>
                <p class="text-[11px] font-medium text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-2 flex items-center gap-2">
                  <Unplug class="w-3.5 h-3.5" /> Tools MCP
                </p>
                <div v-if="!mcpStatus.connected || !mcpStatus.tools.length" class="p-4 rounded-xl bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] text-center">
                  <p class="text-xs text-[var(--color-ide-text-dim)]">未找到 MCP 服务器</p>
                  <p class="text-[10px] text-gray-700 mt-1">前往 MCP 管理添加服务器后可用</p>
                </div>
                <div v-else class="space-y-1">
                  <button
                    v-for="tool in mcpStatus.tools"
                    :key="tool.name"
                    @click="editToggleTool(mcpToolId(tool.server, tool.name))"
                    :class="[
                      'w-full flex items-center gap-2 px-3 py-2 rounded-lg text-xs border transition-all',
                      editIsToolEnabled(mcpToolId(tool.server, tool.name))
                        ? 'bg-violet-500/10 border-violet-500/20 text-violet-400'
                        : 'bg-[var(--color-ide-surface-hover)] border-[var(--color-ide-border)] text-[var(--color-ide-text-dim)] hover:border-[var(--color-ide-border)]',
                    ]"
                  >
                    <span class="w-2 h-2 rounded-full bg-green-400/60" />
                    <span class="truncate">{{ tool.name }}</span>
                    <span class="text-gray-700 text-[10px]">{{ tool.server }}</span>
                  </button>
                </div>
              </div>

              <!-- Footer actions -->
              <div class="flex items-center gap-2 pt-2 border-t border-[var(--color-ide-border)]">
                <button
                  @click="startEdit(agent)"
                  class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-[var(--color-ide-text-dim)] hover:text-white hover:bg-[var(--color-ide-surface-hover)] transition-colors"
                >
                  <Edit3 class="w-3.5 h-3.5" /> 编辑
                </button>
                <button
                  @click="handleClone(agent)"
                  class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-[var(--color-ide-text-dim)] hover:text-white hover:bg-[var(--color-ide-surface-hover)] transition-colors"
                >
                  <Copy class="w-3.5 h-3.5" /> 克隆
                </button>
                <button
                  @click="handleDelete(agent.id)"
                  class="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs text-[var(--color-ide-text-dim)] hover:text-red-400 hover:bg-red-500/10 transition-colors ml-auto"
                >
                  <Trash2 class="w-3.5 h-3.5" /> 删除
                </button>
              </div>
            </div>
          </Transition>
        </div>
      </div>
    </div>

    <!-- ═══ Create Modal ═══ -->
    <Teleport to="body">
      <div v-if="showCreate" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" @click.self="showCreate = false">
        <div class="bg-surface-900 rounded-2xl border border-[var(--color-ide-border)] w-[760px] max-h-[90vh] flex flex-col shadow-2xl">
          <!-- Modal Header -->
          <div class="flex items-center justify-between p-5 border-b border-[var(--color-ide-border)]">
            <h3 class="text-lg font-semibold text-white flex items-center gap-2">
              <Bot class="w-4 h-4 text-violet-400" />创建 Agent — {{ activeTab === 'user' ? '用户' : '项目' }}
            </h3>
            <button @click="showCreate = false" class="p-1.5 rounded-lg hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] transition-colors"><X class="w-4 h-4" /></button>
          </div>

          <!-- Modal Body -->
          <div class="flex-1 overflow-y-auto p-5 space-y-5">
            <!-- Row 1: 名称 + Agent 模式 -->
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-xs font-medium text-[var(--color-ide-text-dim)] mb-1.5">名称 <span class="text-red-400">*</span></label>
                <input
                  v-model="form.name"
                  placeholder="例如：Code Reviewer"
                  class="w-full rounded-xl border border-[var(--color-ide-border)] bg-[var(--color-ide-surface-hover)] px-4 py-2.5 text-sm text-white placeholder-[var(--color-ide-text-dim)] focus:outline-none focus:border-violet-500/40 transition-all"
                />
              </div>
              <div>
                <label class="block text-xs font-medium text-[var(--color-ide-text-dim)] mb-1.5">Agent 模式 <span class="text-red-400">*</span></label>
                <div class="flex gap-2">
                  <button
                    v-for="opt in [{ id: 'agentic', label: 'Agentic', desc: '自主决策与执行', icon: Zap }, { id: 'manual', label: 'Manual', desc: '手动触发确认', icon: ArrowRightLeft }]"
                    :key="opt.id"
                    @click="form.agentic_mode = opt.id as any"
                    :class="[
                      'flex-1 flex flex-col items-center gap-1 p-3 rounded-xl border text-sm transition-all duration-200',
                      form.agentic_mode === opt.id
                        ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
                        : 'border-[var(--color-ide-border)] bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] hover:border-[var(--color-ide-border)]',
                    ]"
                  >
                    <component :is="opt.icon" class="w-4 h-4" />
                    <span class="font-medium text-xs">{{ opt.label }}</span>
                    <span class="text-[10px] opacity-60">{{ opt.desc }}</span>
                  </button>
                </div>
              </div>
            </div>

            <!-- Row 2: 描述 + 模型 -->
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-xs font-medium text-[var(--color-ide-text-dim)] mb-1.5">描述 <span class="text-red-400">*</span></label>
                <input
                  v-model="form.description"
                  placeholder="简要说明 Agent 的用途..."
                  class="w-full rounded-xl border border-[var(--color-ide-border)] bg-[var(--color-ide-surface-hover)] px-4 py-2.5 text-sm text-white placeholder-[var(--color-ide-text-dim)] focus:outline-none focus:border-violet-500/40 transition-all"
                />
              </div>
              <div>
                <label class="block text-xs font-medium text-[var(--color-ide-text-dim)] mb-1.5">Model</label>
                <select
                  v-model="form.model"
                  class="w-full rounded-xl border border-[var(--color-ide-border)] bg-[var(--color-ide-surface-hover)] px-4 py-2.5 text-sm text-white focus:outline-none focus:border-violet-500/40 transition-all"
                >
                  <option v-for="m in availableModels" :key="m.value" :value="m.value">{{ m.label }} ({{ m.provider }})</option>
                </select>
              </div>
            </div>

            <!-- Row 3: 模式 + Auto Run -->
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-xs font-medium text-[var(--color-ide-text-dim)] mb-1.5">对话模式</label>
                <div class="flex gap-2">
                  <button
                    v-for="opt in [{ id: 'craft', label: 'Craft', desc: '编辑模式' }, { id: 'ask', label: 'Ask', desc: '问答模式' }, { id: 'plan', label: 'Plan', desc: '规划模式' }]"
                    :key="opt.id"
                    @click="form.mode = opt.id as any"
                    :class="[
                      'flex-1 flex flex-col items-center gap-1 p-2.5 rounded-xl border text-sm transition-all duration-200',
                      form.mode === opt.id
                        ? 'border-violet-500/30 bg-violet-500/10 text-violet-400'
                        : 'border-[var(--color-ide-border)] bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] hover:border-[var(--color-ide-border)]',
                    ]"
                  >
                    <span class="font-medium text-xs">{{ opt.label }}</span>
                    <span class="text-[10px] opacity-60">{{ opt.desc }}</span>
                  </button>
                </div>
              </div>
              <div>
                <label class="block text-xs font-medium text-[var(--color-ide-text-dim)] mb-1.5">Auto Run</label>
                <div class="flex gap-2">
                  <button
                    @click="form.auto_run = true"
                    :class="[
                      'flex-1 flex items-center justify-center gap-2 p-2.5 rounded-xl border text-sm transition-all',
                      form.auto_run
                        ? 'border-teal-500/30 bg-teal-500/10 text-teal-400'
                        : 'border-[var(--color-ide-border)] bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]',
                    ]"
                  >
                    <Play class="w-3.5 h-3.5" />
                    <span class="text-xs">Enabled</span>
                  </button>
                  <button
                    @click="form.auto_run = false"
                    :class="[
                      'flex-1 flex items-center justify-center gap-2 p-2.5 rounded-xl border text-sm transition-all',
                      !form.auto_run
                        ? 'border-gray-500/30 bg-gray-500/10 text-[var(--color-ide-text-dim)]'
                        : 'border-[var(--color-ide-border)] bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]',
                    ]"
                  >
                    <Pause class="w-3.5 h-3.5" />
                    <span class="text-xs">Disabled</span>
                  </button>
                </div>
              </div>
            </div>

            <!-- System Prompt -->
            <div>
              <label class="block text-xs font-medium text-[var(--color-ide-text-dim)] mb-1.5">System Prompt <span class="text-red-400">*</span></label>
              <textarea
                v-model="form.system_prompt"
                rows="5"
                placeholder="定义 Agent 的角色、行为和能力..."
                class="w-full rounded-xl border border-[var(--color-ide-border)] bg-[var(--color-ide-surface-hover)] px-4 py-2.5 text-sm text-white font-mono placeholder-[var(--color-ide-text-dim)] focus:outline-none focus:border-violet-500/40 transition-all resize-none"
              ></textarea>
            </div>

            <!-- Tools Built-In -->
            <div>
              <label class="block text-xs font-medium text-[var(--color-ide-text-dim)] mb-2 flex items-center gap-2">
                <Wrench class="w-3.5 h-3.5" /> Tools Built-In
              </label>
              <div class="space-y-2 max-h-[320px] overflow-y-auto pr-1">
                <div
                  v-for="cat in toolCategories"
                  :key="cat.id"
                  class="rounded-xl border border-[var(--color-ide-border)] bg-[var(--color-ide-surface)] overflow-hidden"
                >
                  <!-- Category header -->
                  <button
                    @click="toggleFormCategory(cat.id)"
                    :class="[
                      'w-full flex items-center gap-3 px-4 py-3 text-sm transition-colors text-left',
                      (form.tool_categories || []).includes(cat.id)
                        ? 'bg-violet-500/8 text-violet-400'
                        : 'text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]',
                    ]"
                  >
                    <component :is="catIconMap[cat.icon] || Wrench" class="w-4 h-4 shrink-0" />
                    <div class="flex-1">
                      <span class="font-medium text-xs">{{ cat.label }}</span>
                      <p class="text-[10px] text-[var(--color-ide-text-dim)]">{{ cat.description }}</p>
                    </div>
                    <ChevronDown
                      :class="[
                        'w-4 h-4 shrink-0 transition-transform duration-200',
                        isCatExpanded(cat.id) && 'rotate-180',
                      ]"
                    />
                  </button>

                  <!-- Tool list -->
                  <Transition name="expand">
                    <div
                      v-if="isCatExpanded(cat.id) && (form.tool_categories || []).includes(cat.id)"
                      class="border-t border-[var(--color-ide-border)]"
                    >
                      <div class="p-3 space-y-1.5 bg-[var(--color-ide-surface)]">
                        <button
                          v-for="tool in cat.tools"
                          :key="tool.id"
                          @click="toggleFormTool(tool.id)"
                          :class="[
                            'w-full flex items-center gap-3 px-3 py-2 rounded-lg text-xs border transition-all duration-150 text-left',
                            isFormToolEnabled(tool.id)
                              ? 'bg-violet-500/10 border-violet-500/20 text-violet-400'
                              : 'bg-[var(--color-ide-surface-hover)] border-transparent text-[var(--color-ide-text-dim)] hover:border-[var(--color-ide-border)]',
                          ]"
                        >
                          <div
                            :class="[
                              'w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors',
                              isFormToolEnabled(tool.id)
                                ? 'bg-violet-500 border-violet-500'
                                : 'border-[var(--color-ide-border)]',
                            ]"
                          >
                            <svg v-if="isFormToolEnabled(tool.id)" class="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3">
                              <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                            </svg>
                          </div>
                          <div class="flex-1 min-w-0">
                            <span class="text-xs font-medium">{{ tool.name }}</span>
                            <p class="text-[10px] text-[var(--color-ide-text-dim)] truncate">{{ tool.description }}</p>
                          </div>
                        </button>
                      </div>
                    </div>
                  </Transition>
                </div>
              </div>
            </div>

            <!-- Tools MCP -->
            <div>
              <label class="block text-xs font-medium text-[var(--color-ide-text-dim)] mb-2 flex items-center gap-2">
                <Unplug class="w-3.5 h-3.5" /> Tools MCP
              </label>
              <div v-if="!toolsMetaLoaded" class="flex items-center gap-2 py-3 text-xs text-[var(--color-ide-text-dim)]">
                <Loader2 class="w-3.5 h-3.5 animate-spin" /> 加载中...
              </div>
              <div v-else-if="!mcpStatus.connected || !mcpStatus.tools.length" class="p-4 rounded-xl bg-[var(--color-ide-surface)] border border-dashed border-[var(--color-ide-border)] text-center">
                <Unplug class="w-5 h-5 mx-auto mb-2 text-[var(--color-ide-text-dim)]" />
                <p class="text-xs text-[var(--color-ide-text-dim)] mb-3">
                  {{ mcpStatus.servers.length ? `已连接 ${mcpStatus.servers.length} 个 MCP 服务器，但未发现工具` : '未找到 MCP 服务器' }}
                </p>
                <p class="text-[10px] text-gray-700">前往 MCP 管理添加服务器后，此处将自动列出可用工具</p>
              </div>
              <div v-else class="space-y-1">
                <div
                  v-for="server in mcpStatus.servers"
                  :key="server.name"
                  class="rounded-xl border border-[var(--color-ide-border)] bg-[var(--color-ide-surface)] overflow-hidden"
                >
                  <div class="flex items-center gap-2 px-3 py-2 text-xs text-[var(--color-ide-text-dim)] border-b border-[var(--color-ide-border)]">
                    <div class="w-2 h-2 rounded-full bg-green-400" />
                    <span class="font-medium">{{ server.name }}</span>
                    <span class="text-[var(--color-ide-text-dim)] text-[10px]">{{ server.transport }}</span>
                  </div>
                  <div class="p-2 space-y-1">
                    <button
                      v-for="tool in mcpStatus.tools.filter(t => (t as any).server === server.name)"
                      :key="tool.name"
                      @click="toggleMcpTool(server.name, tool.name)"
                      :class="[
                        'w-full flex items-center gap-3 px-3 py-1.5 rounded-lg text-xs border transition-all text-left',
                        isMcpToolEnabled(server.name, tool.name)
                          ? 'bg-violet-500/10 border-violet-500/20 text-violet-400'
                          : 'bg-[var(--color-ide-surface-hover)] border-transparent text-[var(--color-ide-text-dim)] hover:border-[var(--color-ide-border)]',
                      ]"
                    >
                      <div
                        :class="[
                          'w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0',
                          isMcpToolEnabled(server.name, tool.name)
                            ? 'bg-violet-500 border-violet-500'
                            : 'border-[var(--color-ide-border)]',
                        ]"
                      >
                        <svg v-if="isMcpToolEnabled(server.name, tool.name)" class="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3">
                          <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                        </svg>
                      </div>
                      <span class="truncate">{{ tool.name }}</span>
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Modal Footer -->
          <div class="flex gap-3 justify-end p-5 border-t border-[var(--color-ide-border)]">
            <button
              @click="showCreate = false"
              class="px-5 py-2.5 rounded-xl bg-[var(--color-ide-surface-hover)] border border-[var(--color-ide-border)] text-sm text-[var(--color-ide-text-dim)] hover:text-white transition-colors"
            >取消</button>
            <button
              @click="handleCreate()"
              :disabled="!form.name || !form.system_prompt"
              class="px-5 py-2.5 rounded-xl bg-violet-500 hover:bg-violet-600 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
            >创建 Agent</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ═══ Edit Modal ═══ -->
    <Teleport to="body">
      <div v-if="editAgent" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" @click.self="editAgent = null">
        <div class="bg-surface-900 rounded-2xl border border-[var(--color-ide-border)] w-[760px] max-h-[90vh] flex flex-col shadow-2xl">
          <div class="flex items-center justify-between p-5 border-b border-[var(--color-ide-border)]">
            <h3 class="text-lg font-semibold text-white flex items-center gap-2">
              <Edit3 class="w-4 h-4 text-violet-400" />编辑 Agent
            </h3>
            <button @click="editAgent = null" class="p-1.5 rounded-lg hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] transition-colors"><X class="w-4 h-4" /></button>
          </div>
          <div class="flex-1 overflow-y-auto p-5 space-y-4">
            <!-- 名称 + model -->
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-xs font-medium text-[var(--color-ide-text-dim)] mb-1.5">名称</label>
                <input
                  v-model="editAgent.name"
                  class="w-full rounded-xl border border-[var(--color-ide-border)] bg-[var(--color-ide-surface-hover)] px-4 py-2.5 text-sm text-white focus:outline-none focus:border-violet-500/40 transition-all"
                />
              </div>
              <div>
                <label class="block text-xs font-medium text-[var(--color-ide-text-dim)] mb-1.5">Model</label>
                <select
                  v-model="editAgent.model"
                  class="w-full rounded-xl border border-[var(--color-ide-border)] bg-[var(--color-ide-surface-hover)] px-4 py-2.5 text-sm text-white focus:outline-none focus:border-violet-500/40 transition-all"
                >
                  <option v-for="m in availableModels" :key="m.value" :value="m.value">{{ m.label }}</option>
                </select>
              </div>
            </div>
            <!-- 描述 -->
            <div>
              <label class="block text-xs font-medium text-[var(--color-ide-text-dim)] mb-1.5">描述</label>
              <input
                v-model="editAgent.description"
                class="w-full rounded-xl border border-[var(--color-ide-border)] bg-[var(--color-ide-surface-hover)] px-4 py-2.5 text-sm text-white focus:outline-none focus:border-violet-500/40 transition-all"
              />
            </div>
            <!-- System Prompt -->
            <div>
              <label class="block text-xs font-medium text-[var(--color-ide-text-dim)] mb-1.5">System Prompt</label>
              <textarea
                v-model="editAgent.system_prompt"
                rows="6"
                class="w-full rounded-xl border border-[var(--color-ide-border)] bg-[var(--color-ide-surface-hover)] px-4 py-2.5 text-sm text-white font-mono focus:outline-none focus:border-violet-500/40 transition-all resize-none"
              ></textarea>
            </div>
            <!-- Agentic mode + auto_run (readonly info) -->
            <div class="flex items-center gap-6 text-xs text-[var(--color-ide-text-dim)]">
              <div class="flex items-center gap-1.5">
                <Zap class="w-3 h-3 text-emerald-400" />
                模式: {{ editAgent.agentic_mode === 'agentic' ? 'Agentic' : 'Manual' }}
              </div>
              <div class="flex items-center gap-1.5">
                <component :is="editAgent.auto_run ? Play : Pause" class="w-3 h-3 text-teal-400" />
                Auto Run: {{ editAgent.auto_run ? 'On' : 'Off' }}
              </div>
            </div>
          </div>
          <div class="flex gap-3 justify-end p-5 border-t border-[var(--color-ide-border)]">
            <button
              @click="editAgent = null"
              class="px-5 py-2.5 rounded-xl bg-[var(--color-ide-surface-hover)] border border-[var(--color-ide-border)] text-sm text-[var(--color-ide-text-dim)] hover:text-white transition-colors"
            >取消</button>
            <button
              @click="saveEdit()"
              class="px-5 py-2.5 rounded-xl bg-violet-500 hover:bg-violet-600 text-white text-sm font-medium transition-colors"
            >保存</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.toast-enter-active,
.toast-leave-active { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.toast-enter-from,
.toast-leave-to { opacity: 0; transform: translateY(-12px) translateX(-50%); }

.expand-enter-active,
.expand-leave-active { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); overflow: hidden; }
.expand-enter-from,
.expand-leave-to { opacity: 0; max-height: 0; }
.expand-enter-to,
.expand-leave-from { opacity: 1; max-height: 2000px; }
</style>
