<script setup lang="ts">
import { Globe, Server, Terminal } from "lucide-vue-next"
import {
  Activity, AlertCircle, Box, CheckCircle2, ChevronDown, ChevronRight, Clock, Copy,
  Download, ExternalLink, Heart, Loader2, Monitor, Plug, Pencil, Radio, RefreshCw, Search, ShieldCheck, Star, Store, Wrench, X, Zap
} from "lucide-vue-next"
import { computed, onMounted, reactive, ref } from "vue"
import {
  addMCPServer,
  checkMCPServerHealth,
  discoverMCPTools,
  getMCPMarketplace,
  getMCPMarketplaceCategories,
  installFromMarketplace,
  listMCPServers,
  type MCPAddServerPayload,
  type MCPCategory,
  type MCPConnState,
  type MCPHealthResult,
  type MCPMarketplaceServer,
  type MCPServerStatus,
  type MCPUpdateServerPayload,
  reconnectMCPServer,
  registerMCPTools,
  removeMCPServer,
  updateMCPServer,
} from "@/api/mcp"

// ── State ──
const activeTab = ref<"marketplace" | "my">("my")
const toast = ref("")
const error = ref("")

// -- 我的 MCP --
const servers = ref<MCPServerStatus[]>([])
const myLoading = ref(true)
const showAddForm = ref(false)
const newServer = reactive<MCPAddServerPayload>({
  name: "",
  transport: "sse",
  url: "",
  command: "",
  args: [],
  auto_discover: true,
  timeout: 30,
})
const adding = ref(false)

// 展开/编辑状态
const expandedServers = ref<Set<string>>(new Set())
const editingServer = ref<string | null>(null)
const editForm = reactive<MCPUpdateServerPayload>({})
const reconnecting = ref<string | null>(null)
const healthChecking = ref<string | null>(null)
const healthResults = ref<Record<string, MCPHealthResult>>({})

// -- MCP 市场 --
const marketplaceServers = ref<MCPMarketplaceServer[]>([])
const marketplaceLoading = ref(true)
const marketplaceTotal = ref(0)
const mpSearch = ref("")
const mpCategory = ref("")
const categories = ref<MCPCategory[]>([])
const installing = ref<string | null>(null)

// ── Constants ──
const transportLabel: Record<string, string> = {
  sse: "SSE",
  streamable_http: "HTTP",
  stdio: "Stdio",
}
const transportIcon: Record<string, typeof Globe> = {
  sse: Globe,
  streamable_http: Server,
  stdio: Terminal,
}

/** 连接状态 → 样式映射 */
function stateStyle(state: MCPConnState) {
  const map: Record<
    MCPConnState,
    { bg: string; border: string; text: string; dot: string; label: string }
  > = {
    connected: {
      bg: "bg-green-500/10",
      border: "border-green-500/20",
      text: "text-green-400",
      dot: "bg-green-400",
      label: "已连接",
    },
    connecting: {
      bg: "bg-blue-500/10",
      border: "border-blue-500/20",
      text: "text-blue-400",
      dot: "bg-blue-400 animate-pulse",
      label: "连接中",
    },
    reconnecting: {
      bg: "bg-yellow-500/10",
      border: "yellow-500/20",
      text: "text-yellow-400",
      dot: "bg-yellow-400 animate-ping opacity-40",
      label: "重连中",
    },
    failed: {
      bg: "bg-red-500/10",
      border: "red-500/20",
      text: "text-red-400",
      dot: "bg-red-500",
      label: "失败",
    },
    disconnected: {
      bg: "bg-gray-500/10",
      border: "gray-500/20",
      text: "text-gray-500",
      dot: "bg-gray-600",
      label: "未连接",
    },
    disabled: {
      bg: "bg-gray-800/30",
      border: "gray-700/20",
      text: "text-gray-600",
      dot: "bg-gray-700",
      label: "已禁用",
    },
  }
  return map[state] || map.disconnected
}

// ── Computed ──
const filteredMarketplace = computed(() => {
  let list = marketplaceServers.value
  if (mpSearch.value) {
    const q = mpSearch.value.toLowerCase()
    list = list.filter(
      (s) =>
        s.name.toLowerCase().includes(q) ||
        s.description.toLowerCase().includes(q) ||
        s.tags.some((t) => t.toLowerCase().includes(q)) ||
        s.features.some((f) => f.toLowerCase().includes(q)),
    )
  }
  if (mpCategory.value)
    list = list.filter((s) => s.category === mpCategory.value)
  return list
})

const categoryLabelMap: Record<string, string> = {
  dev_tools: "开发工具",
  cloud: "云服务",
  database: "数据库",
  productivity: "效率工具",
  ai_model: "AI 模型",
}

const connectedCount = computed(
  () => servers.value.filter((s) => s.connected).length,
)
const totalTools = computed(() =>
  servers.value.reduce((sum, s) => sum + s.tools_count, 0),
)
const sseCount = computed(
  () => servers.value.filter((s) => s.transport === "sse").length,
)
const httpCount = computed(
  () => servers.value.filter((s) => s.transport === "streamable_http").length,
)
const stdioCount = computed(
  () => servers.value.filter((s) => s.transport === "stdio").length,
)

// ── Lifecycle ──
onMounted(() => {
  refreshMyServers()
  loadMarketplace()
  loadCategories()
})

// ── Toast ──
const showToast = (msg: string) => {
  toast.value = msg
  setTimeout(() => {
    toast.value = ""
  }, 4000)
}

// ══════════════ 我的 MCP 方法 ══════════════

async function refreshMyServers() {
  myLoading.value = true
  try {
    const res = await listMCPServers()
    servers.value = res.data?.servers ?? []
  } catch (e: unknown) {
    error.value = (e as Error).message || "加载失败"
  } finally {
    myLoading.value = false
  }
}

async function handleAdd() {
  if (!newServer.name.trim()) return
  adding.value = true
  error.value = ""
  try {
    const res = await addMCPServer({ ...newServer })
    if (res.data?.success !== false) {
      showToast(
        `已连接 "${newServer.name}"，发现 ${res.data?.tools_discovered ?? 0} 个工具`,
      )
      showAddForm.value = false
      resetNewServer()
      await refreshMyServers()
    } else {
      error.value =
        res.data?.message || res.data?.errors?.join("; ") || "连接失败"
    }
  } catch (e: unknown) {
    const errData = (e as any)?.response?.data
    error.value =
      errData?.detail ?? errData?.error ?? (e as Error).message ?? "添加失败"
  } finally {
    adding.value = false
  }
}

function resetNewServer() {
  Object.assign(newServer, {
    name: "",
    transport: "sse",
    url: "",
    command: "",
    args: [],
    auto_discover: true,
    timeout: 30,
  })
}

async function handleRemove(name: string) {
  if (
    !confirm(
      `确定断开并移除 MCP 服务器 "${name}"？\n这将删除配置并断开所有连接。`,
    )
  )
    return
  try {
    await removeMCPServer(name)
    expandedServers.value.delete(name)
    await refreshMyServers()
    showToast(`已移除 "${name}"`)
  } catch (e: unknown) {
    error.value = (e as Error).message || "移除失败"
  }
}

async function handleReconnect(name: string) {
  reconnecting.value = name
  error.value = ""
  try {
    const res = await reconnectMCPServer(name)
    showToast(res.data?.message || `已触发 "${name}" 重连`)
    // 延迟刷新等待重连完成
    setTimeout(async () => {
      await refreshMyServers()
    }, 2000)
  } catch (e: unknown) {
    error.value = (e as Error).message || "重连失败"
  } finally {
    reconnecting.value = null
  }
}

async function handleHealthCheck(name: string) {
  healthChecking.value = name
  error.value = ""
  try {
    const res = await checkMCPServerHealth(name)
    healthResults.value[name] = res.data
  } catch (e: unknown) {
    healthResults.value[name] = {
      healthy: false,
      latency_ms: 0,
      state: "disconnected",
      connected: false,
      detail: (e as Error).message,
      uptime_seconds: 0,
      success_rate: 0,
      last_heartbeat_age_seconds: -1,
    }
  } finally {
    healthChecking.value = null
  }
}

function toggleExpand(name: string) {
  if (expandedServers.value.has(name)) expandedServers.value.delete(name)
  else {
    expandedServers.value.add(name)
    handleHealthCheck(name)
  }
}

function startEdit(server: MCPServerStatus) {
  editingServer.value = server.name
  Object.assign(editForm, {
    url: server.url || undefined,
    tool_prefix: server.tool_prefix || undefined,
    auto_discover: server.auto_discover,
    timeout: server.timeout_seconds,
  })
}
function cancelEdit() {
  editingServer.value = null
}

async function saveEdit(name: string) {
  try {
    await updateMCPServer(name, editForm)
    showToast(`"${name}" 配置已更新`)
    editingServer.value = null
    await refreshMyServers()
  } catch (e: unknown) {
    error.value = (e as Error).message || "更新失败"
  }
}

async function handleDiscover() {
  try {
    const res = await discoverMCPTools()
    showToast(`扫描完成，共发现 ${res.data?.total ?? 0} 个工具`)
    await refreshMyServers()
  } catch (e: unknown) {
    error.value = (e as Error).message || "扫描失败"
  }
}

async function handleRegister() {
  try {
    const res = await registerMCPTools()
    showToast(res.data?.message || "工具注册完成")
  } catch (e: unknown) {
    error.value = (e as Error).message || "注册失败"
  }
}

// ══════════════ MCP 市场方法 ══════════════

async function loadMarketplace() {
  marketplaceLoading.value = true
  try {
    const res = await getMCPMarketplace()
    marketplaceServers.value = res.data.servers
    marketplaceTotal.value = res.data.total
  } catch (e: unknown) {
    error.value = (e as Error).message || "加载市场失败"
  } finally {
    marketplaceLoading.value = false
  }
}

async function loadCategories() {
  try {
    const res = await getMCPMarketplaceCategories()
    categories.value = res.data.categories
  } catch {
    /* ignore */
  }
}

async function handleInstall(preset: MCPMarketplaceServer) {
  installing.value = preset.id
  error.value = ""
  try {
    const res = await installFromMarketplace({
      preset_id: preset.id,
      transport: preset.transport,
      url: preset.url,
      command: preset.command,
      args: preset.args,
      env: preset.env_config,
      timeout: 30,
    })
    if (res.data.success) {
      showToast(
        `已安装 "${preset.name}"，发现 ${res.data.tools_discovered} 个工具`,
      )
      activeTab.value = "my"
      await refreshMyServers()
    } else {
      error.value = res.data.message || "安装失败"
    }
  } catch (e: unknown) {
    error.value = (e as Error).message || "安装失败"
  } finally {
    installing.value = null
  }
}

const formatCount = (n: number): string =>
  n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`
const formatUptime = (s: number): string => {
  if (!s) return "-"
  if (s < 60) return `${Math.floor(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.floor(s % 60)}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
}
const successRateLabel = (rate: number): string =>
  rate >= 1 ? '100%' : `${(rate * 100).toFixed(0)}%`
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
    <header class="flex items-center justify-between px-6 md:px-8 pt-6 md:pt-8 pb-4 md:pb-6 border-b border-white/5 shrink-0">
      <div class="min-w-0">
        <h1 class="text-lg md:text-2xl font-bold text-white flex items-center gap-2.5 md:gap-3">
          <span class="w-9 h-9 md:w-10 md:h-10 rounded-xl bg-gradient-to-br from-blue-500/20 to-indigo-500/10 border border-blue-500/20 flex items-center justify-center shrink-0">
            <Server class="w-4 h-4 md:w-5 md:h-5 text-blue-400" />
          </span>
          <span class="truncate">MCP 管理</span>
        </h1>
        <p class="text-xs md:text-sm text-gray-500 mt-1 ml-[2.85rem] md:ml-[3.25rem] hidden sm:block">连接外部工具和数据源，扩展 AI 助手的能力边界</p>
      </div>

      <!-- Action buttons -->
      <div class="flex items-center gap-1.5 md:gap-2 shrink-0">
        <button @click="handleDiscover" class="hidden sm:flex items-center gap-1.5 px-2.5 md:px-3 py-1.5 md:py-2 rounded-xl bg-white/[0.04] border border-white/10 text-xs md:text-sm text-gray-400 hover:text-white transition-colors">
          <RefreshCw class="w-3.5 h-3.5" /> 扫描
        </button>
        <button @click="handleRegister" class="hidden sm:flex items-center gap-1.5 px-2.5 md:px-3 py-1.5 md:py-2 rounded-xl bg-white/[0.04] border border-white/10 text-xs md:text-sm text-gray-400 hover:text-white transition-colors">
          <Zap class="w-3.5 h-3.5" /> 注册
        </button>
        <button v-if="activeTab === 'my'" @click="showAddForm = !showAddForm" class="flex items-center gap-1.5 md:gap-2 px-3 md:px-4 py-2 md:py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-xs md:text-sm font-medium transition-colors shadow-lg shadow-brand-500/15">
          <Plus class="w-3.5 h-3.5" /> {{ showAddForm ? '取消' : '配置 MCP Server' }}
        </button>
      </div>
    </header>

    <!-- Error bar -->
    <Transition name="fade">
      <div v-if="error" class="mx-6 md:mx-8 mt-3 px-4 py-2.5 rounded-xl bg-red-500/10 border border-red-500/15 text-sm text-red-400 flex items-center justify-between shrink-0">
        <span class="truncate mr-3">{{ error }}</span>
        <button @click="error = ''" class="shrink-0"><X class="w-4 h-4" /></button>
      </div>
    </Transition>

    <!-- Tabs -->
    <nav class="px-6 md:px-8 pt-3 md:pt-4 pb-0 flex items-center gap-1 border-b border-white/5 shrink-0 overflow-x-auto hide-scrollbar">
      <button
        v-for="tab in [{ id: 'marketplace', label: 'MCP 市场', count: marketplaceTotal }, { id: 'my', label: '我的 MCP', count: servers.length }] as const"
        :key="tab.id"
        @click="activeTab = tab.id"
        :class="[
          'relative px-3 md:px-4 py-2 rounded-t-xl text-xs md:text-sm font-medium transition-all duration-200 flex items-center gap-1.5 whitespace-nowrap',
          activeTab === tab.id
            ? 'text-white bg-white/[0.03] border border-white/8 border-b-transparent -mb-[1px] z-10'
            : 'text-gray-500 hover:text-gray-300'
        ]"
      >
        <component :is="tab.id === 'marketplace' ? Store : Monitor" class="w-3.5 h-3.5" />
        {{ tab.label }}
        <span class="ml-0.5 rounded-full bg-white/10 px-1.5 py-0.5 text-[10px] text-gray-400">{{ tab.count }}</span>
      </button>
    </nav>

    <!-- Main content area -->
    <div class="flex-1 flex overflow-hidden">

      <!-- ═══════════════ MCP 市场 ═══════════════ -->
      <section v-if="activeTab === 'marketplace'" class="flex-1 flex overflow-hidden">
        <!-- Left sidebar: Categories -->
        <aside class="w-44 md:w-52 shrink-0 border-r border-white/5 p-3 md:p-4 space-y-2 overflow-y-auto hidden sm:flex flex-col">
          <div class="relative mb-2">
            <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-600" />
            <input v-model="mpSearch" placeholder="搜索..." class="w-full rounded-lg border border-white/10 bg-white/[0.03] pl-8 pr-3 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-brand-500/40 transition-all" />
          </div>
          <p class="text-[11px] font-medium text-gray-500 uppercase tracking-wider px-1">分类</p>
          <button @click="mpCategory = ''" :class="['w-full text-left rounded-lg px-2 py-1.5 text-xs transition-colors', !mpCategory ? 'bg-brand-500/10 text-brand-400' : 'text-gray-400 hover:text-white hover:bg-white/[0.04]']">
            全部 ({{ marketplaceTotal }})
          </button>
          <button v-for="cat in categories" :key="cat.id" @click="mpCategory = cat.id" :class="['w-full text-left rounded-lg px-2 py-1.5 text-xs transition-colors', mpCategory === cat.id ? 'bg-brand-500/10 text-brand-400' : 'text-gray-400 hover:text-white hover:bg-white/[0.04]']">
            {{ categoryLabelMap[cat.id] || cat.name }} ({{ cat.count }})
          </button>
        </aside>

        <!-- Main grid -->
        <main class="flex-1 overflow-y-auto p-4 md:p-6">
          <div v-if="marketplaceLoading" class="flex items-center justify-center py-24"><Loader2 class="w-8 h-8 animate-spin text-brand-400" /></div>
          <div v-else-if="!filteredMarketplace.length" class="flex flex-col items-center justify-center py-24 text-gray-600">
            <Store class="w-12 h-12 text-gray-700 mb-3" /><p class="text-sm text-gray-500">没有找到匹配的 MCP 服务</p><p class="text-xs text-gray-600 mt-1">尝试更换搜索词或分类</p>
          </div>
          <div v-else class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 md:gap-4">
            <article v-for="preset in filteredMarketplace" :key="preset.id" class="mcp-market-card group rounded-2xl border border-white/8 bg-white/[0.02] p-4 md:p-5 hover:border-white/15 transition-all duration-200 flex flex-col">
              <div class="flex items-start gap-3 mb-3">
                <div class="w-9 h-9 md:w-10 md:h-10 rounded-xl bg-gradient-to-br from-white/10 to-white/[0.02] flex items-center justify-center shrink-0 text-base md:lg border border-white/5">{{ preset.icon }}</div>
                <div class="min-w-0"><h3 class="text-sm font-semibold text-white truncate">{{ preset.name }}</h3><p class="text-[10px] text-gray-500">v{{ preset.version }} · {{ preset.author }}</p></div>
              </div>
              <p class="text-xs text-gray-400 leading-relaxed mb-3 line-clamp-2">{{ preset.description }}</p>
              <div class="flex flex-wrap gap-1 mb-3">
                <span v-for="feat in preset.features.slice(0, 4)" :key="feat" class="rounded-full bg-white/[0.03] border border-white/5 px-2 py-0.5 text-[10px] text-gray-500">{{ feat }}</span>
                <span v-if="preset.features.length > 4" class="text-[10px] text-gray-600 self-center">+{{ preset.features.length - 4 }}</span>
              </div>
              <div class="flex items-center gap-3 text-[10px] text-gray-600 mb-4 mt-auto">
                <span class="flex items-center gap-1"><Star class="w-3 h-3 text-yellow-500/70" />{{ formatCount(preset.stars) }}</span>
                <span class="flex items-center gap-1"><Download class="w-3 h-3 text-green-500/70" />{{ formatCount(preset.installs) }}</span>
                <span class="rounded-full bg-white/[0.03] border border-white/5 px-1.5 py-0.5">{{ transportLabel[preset.transport] || preset.transport }}</span>
              </div>
              <div class="flex items-center gap-2">
                <button @click="handleInstall(preset)" :disabled="installing === preset.id" class="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-brand-500/15 border border-brand-500/20 text-brand-400 hover:bg-brand-500/25 disabled:opacity-50 text-xs font-medium transition-all">
                  <Loader2 v-if="installing === preset.id" class="w-3.5 h-3.5 animate-spin" /><Plug v-else class="w-3.5 h-3.5" />{{ installing === preset.id ? '安装中...' : '安装' }}
                </button>
                <a v-if="preset.homepage" :href="preset.homepage" target="_blank" class="p-2 rounded-lg text-gray-600 hover:text-gray-300 hover:bg-white/5 transition-colors"><ExternalLink class="w-3.5 h-3.5" /></a>
              </div>
            </article>
          </div>
        </main>
      </section>

      <!-- ═══════════════ 我的 MCP ═══════════════ -->
      <section v-if="activeTab === 'my'" class="flex-1 flex overflow-hidden">
        <!-- Left sidebar: Stats -->
        <aside class="w-44 md:w-52 shrink-0 border-r border-white/5 p-3 md:p-4 space-y-1.5 overflow-y-auto hidden sm:flex flex-col">
          <p class="text-[11px] font-medium text-gray-500 uppercase tracking-wider px-2 mb-2">协议分布</p>
          <div class="space-y-0.5">
            <StatRow icon="Globe" label="SSE" :value="sseCount" color="text-blue-400" />
            <StatRow icon="Server" label="HTTP" :value="httpCount" color="text-indigo-400" />
            <StatRow icon="Terminal" label="Stdio" :value="stdioCount" color="text-emerald-400" />
          </div>

          <div class="mt-5 px-2 pt-4 border-t border-white/5 space-y-2">
            <div class="flex items-center gap-1.5 text-xs" :class="connectedCount > 0 ? 'text-green-400' : 'text-gray-600'">
              <div class="w-1.5 h-1.5 rounded-full" :class="connectedCount > 0 ? 'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.5)]' : 'bg-gray-500'" />
              <span>{{ connectedCount }} 已连接 / {{ servers.length }} 总计</span>
            </div>
            <div class="flex items-center gap-1.5 text-xs text-gray-600">
              <Wrench class="w-3 h-3" /><span>{{ totalTools }} 个工具</span>
            </div>
          </div>

          <div class="mt-auto pt-4 border-t border-white/5 px-2">
            <p class="text-[10px] text-gray-600 leading-relaxed">
              MCP 允许 AI 连接外部数据源和工具（文件系统、数据库、API 等），通过标准化 JSON-RPC 协议通信。
            </p>
          </div>
        </aside>

        <!-- Main content -->
        <main class="flex-1 overflow-y-auto p-4 md:p-6 space-y-4">
          <!-- Add form -->
          <div v-if="showAddForm" class="mcp-add-form rounded-2xl border border-brand-500/15 bg-white/[0.02] p-4 md:p-5 space-y-4">
            <div class="flex items-center gap-2 mb-1">
              <Plug class="w-4 h-4 text-brand-400" /><h3 class="text-sm font-semibold text-white">连接新的 MCP 服务器</h3>
            </div>
            <div class="grid gap-4 grid-cols-1 md:grid-cols-2">
              <div>
                <label class="block text-xs font-medium text-gray-400 mb-1.5">名称 <span class="text-red-400">*</span></label>
                <input v-model="newServer.name" placeholder="例如：my-filesystem" class="mcp-input" />
              </div>
              <div>
                <label class="block text-xs font-medium text-gray-400 mb-1.5">传输类型</label>
                <select v-model="newServer.transport" class="mcp-input">
                  <option value="sse">SSE (推荐)</option><option value="streamable_http">Streamable HTTP</option><option value="stdio">Stdio (本地进程)</option>
                </select>
              </div>
            </div>
            <div v-if="newServer.transport !== 'stdio'">
              <label class="block text-xs font-medium text-gray-400 mb-1.5">服务器 URL</label>
              <input v-model="newServer.url" placeholder="http://localhost:3001/sse" class="mcp-input font-mono" />
              <p class="text-[10px] text-gray-600 mt-1">MCP 服务器暴露的 SSE 或 HTTP 端点地址</p>
            </div>
            <div v-if="newServer.transport === 'stdio'">
              <label class="block text-xs font-medium text-gray-400 mb-1.5">启动命令</label>
              <input v-model="newServer.command" placeholder="npx -y @modelcontextprotocol/server-filesystem /path" class="mcp-input font-mono" />
              <p class="text-[10px] text-gray-600 mt-1">本地启动 MCP 服务器的命令（需通过安全白名单校验）</p>
            </div>
            <div class="flex items-center gap-6 flex-wrap">
              <label class="flex items-center gap-2 text-xs text-gray-400 cursor-pointer"><input v-model="newServer.auto_discover" type="checkbox" class="rounded border-white/20 bg-white/[0.03]" /> 自动发现工具</label>
              <label class="text-xs text-gray-400 flex items-center gap-2">超时<input v-model.number="newServer.timeout" type="number" min="5" max="120" class="mcp-number" />秒</label>
            </div>
            <div class="flex gap-3 pt-1">
              <button :disabled="adding || !newServer.name.trim()" @click="handleAdd" class="mcp-btn-primary">
                <Loader2 v-if="adding" class="w-4 h-4 animate-spin" /><Plug v-else class="w-4 h-4" />{{ adding ? '连接中...' : '连接' }}
              </button>
              <button @click="showAddForm = false" class="mcp-btn-secondary">取消</button>
            </div>
          </div>

          <!-- Loading -->
          <div v-if="myLoading && !servers.length" class="flex items-center justify-center py-24"><Loader2 class="w-8 h-8 animate-spin text-brand-400" /></div>

          <!-- Empty state (matches screenshot) -->
          <div v-else-if="!servers.length" class="mcp-empty-state flex flex-col items-center justify-center py-16 md:py-24 text-gray-600">
            <div class="w-14 h-14 md:w-16 md:h-16 rounded-2xl bg-white/[0.03] border border-white/5 flex items-center justify-center mb-4">
              <Box class="w-7 h-7 md:w-8 md:h-8 text-gray-700" />
            </div>
            <h3 class="text-sm md:text-base font-medium text-gray-400 mb-2">No MCP Tools</h3>
            <p class="text-xs text-gray-500 max-w-sm text-center mb-6 leading-relaxed">
              Connect Model Context Protocol (MCP) servers to extend AI capabilities with external tools, data sources, and services.
              您可以使用市场制作的服务器，也可以手动创建属于您的 MCP 服务器。
            </p>
            <button @click="showAddForm = true" class="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-500/80 hover:bg-emerald-500 text-white text-sm font-medium transition-colors shadow-lg shadow-emerald-500/15">
              配置 MCP Server
            </button>
          </div>

          <!-- Server cards -->
          <div v-else class="space-y-3">
            <div v-for="srv in servers" :key="srv.name" class="mcp-server-card rounded-2xl border border-white/8 bg-white/[0.02] overflow-hidden transition-all duration-200 group" :class="{ 'ring-1 ring-white/10': expandedServers.has(srv.name) }">
              <!-- Card header -->
              <div class="p-4 md:p-5" @click="toggleExpand(srv.name)">
                <div class="flex items-start justify-between gap-3">
                  <div class="flex items-start gap-3 md:gap-4 min-w-0 flex-1">
                    <!-- Status indicator -->
                    <div class="relative mt-1 shrink-0 cursor-pointer">
                      <div :class="['w-2.5 h-2.5 rounded-full', stateStyle(srv.state).dot]" />
                      <div v-if="srv.state === 'connecting' || srv.state === 'reconnecting'" class="absolute inset-0 w-2.5 h-2.5 rounded-full animate-ping opacity-30" :class="stateStyle(srv.state).dot.replace('animate-pulse','')" />
                      <ChevronRight v-if="!expandedServers.has(srv.name)" class="w-3.5 h-3.5 text-gray-600 absolute -left-4 top-1/2 -translate-y-1/2 hidden lg:block" />
                      <ChevronDown v-else class="w-3.5 h-3.5 text-gray-400 absolute -left-4 top-1/2 -translate-y-1/2 hidden lg:block" />
                    </div>

                    <!-- Server info -->
                    <div class="min-w-0 flex-1">
                      <div class="flex flex-wrap items-center gap-x-2 gap-y-1 mb-1">
                        <h3 class="text-sm font-semibold text-white truncate">{{ srv.name }}</h3>
                        <!-- State badge -->
                        <span :class="['shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium border', stateStyle(srv.state).bg, stateStyle(srv.state).border, stateStyle(srv.state).text]">
                          {{ stateStyle(srv.state).label }}
                        </span>
                        <!-- Transport badge -->
                        <span class="shrink-0 flex items-center gap-1 rounded-full bg-white/5 px-2 py-0.5 text-[10px] text-gray-500 border border-white/5">
                          <component :is="transportIcon[srv.transport] || Server" class="w-2.5 h-2.5" />{{ transportLabel[srv.transport] || srv.transport }}
                        </span>
                        <!-- Health indicator -->
                        <span v-if="healthResults[srv.name]?.healthy !== undefined" :class="['shrink-0 rounded-full px-1.5 py-0.5 text-[10px]', healthResults[srv.name].healthy ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400']">
                          {{ healthResults[srv.name].healthy ? `✓ ${Math.round(healthResults[srv.name].latency_ms)}ms` : '✗ 不健康' }}
                        </span>
                      </div>

                      <p class="text-xs text-gray-500 mb-2 font-mono truncate">{{ srv.url || srv.command || '—' }}</p>

                      <div class="flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] text-gray-600">
                        <span class="flex items-center gap-1"><Wrench class="w-3 h-3" />{{ srv.tools_count }} 个工具</span>
                        <span>{{ srv.timeout_seconds }}s 超时</span>
                        <span v-if="srv.tool_prefix" class="text-brand-400/70">前缀: {{ srv.tool_prefix }}</span>
                        <span v-if="srv.calls_total > 0" class="flex items-center gap-1"><Activity class="w-3 h-3" />{{ successRateLabel(srv.success_rate) }} 成功率</span>
                        <span v-if="srv.uptime_seconds > 0" class="flex items-center gap-1"><Clock class="w-3 h-3" />{{ formatUptime(srv.uptime_seconds) }}</span>
                      </div>
                    </div>
                  </div>

                  <!-- Actions row -->
                  <div class="flex items-center gap-1 shrink-0 opacity-100 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity" @click.stop>
                    <button v-if="!editingServer" @click="startEdit(srv)" class="action-icon" title="编辑配置"><Pencil class="w-3.5 h-3.5" /></button>
                    <button v-if="!editingServer" @click="handleReconnect(srv.name)" :disabled="reconnecting === srv.name" class="action-icon" title="重新连接">
                      <RefreshCw :class="['w-3.5 h-3.5', { 'animate-spin': reconnecting === srv.name }]" />
                    </button>
                    <button @click="handleRemove(srv.name)" class="action-icon hover:!text-red-400 hover:!bg-red-500/10" title="断开并移除"><Trash2 class="w-3.5 h-3.5" /></button>
                  </div>
                </div>
              </div>

              <!-- Edit inline form -->
              <div v-if="editingServer === srv.name" class="px-5 pb-4 border-t border-white/5 pt-3 space-y-3 bg-white/[0.01]">
                <p class="text-xs text-gray-400 font-medium">编辑 "{{ srv.name }}" 配置</p>
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="block text-[11px] text-gray-500 mb-1">URL</label>
                    <input v-model="editForm.url" placeholder="(保持不变留空)" class="mcp-input text-xs" />
                  </div>
                  <div>
                    <label class="block text-[11px] text-gray-500 mb-1">超时(秒)</label>
                    <input v-model.number="editForm.timeout" type="number" min="5" max="300" class="mcp-input text-xs" />
                  </div>
                </div>
                <div class="flex gap-2">
                  <button @click="saveEdit(srv.name)" class="mcp-btn-primary text-xs py-1.5 px-3">保存</button>
                  <button @click="cancelEdit()" class="mcp-btn-secondary text-xs py-1.5 px-3">取消</button>
                </div>
              </div>

              <!-- Expanded details -->
              <ExpandPanel v-if="expandedServers.has(srv.name)">
                <!-- Tools list placeholder (loaded lazily via detail API) -->
                <div class="px-5 py-4 border-t border-white/5 bg-black/10 space-y-3">
                  <h4 class="text-xs font-medium text-gray-400 flex items-center gap-2"><Wrench class="w-3.5 h-3.5" /> 工具列表 ({{ srv.tools_count }})</h4>
                  <div v-if="srv.tools?.length" class="grid gap-1.5">
                    <div v-for="tool in srv.tools" :key="tool.name" class="flex items-start gap-2 rounded-lg bg-white/[0.02] px-3 py-2 border border-white/5">
                      <ShieldCheck class="w-3.5 h-3.5 text-emerald-500/50 mt-0.5 shrink-0" />
                      <div class="min-w-0">
                        <code class="text-xs text-white font-mono">{{ tool.name }}</code>
                        <p class="text-[10px] text-gray-600 line-clamp-1 mt-0.5">{{ tool.description }}</p>
                      </div>
                    </div>
                  </div>
                  <div v-else class="text-xs text-gray-600 italic">点击上方「详情」按钮加载完整工具信息</div>

                  <!-- Stats -->
                  <div v-if="srv.calls_total > 0" class="grid grid-cols-2 md:grid-cols-4 gap-2 pt-2 border-t border-white/5">
                    <StatCard label="总调用" :value="String(srv.calls_total)" icon="Activity" />
                    <StatCard label="成功" :value="String(srv.calls_success)" icon="CheckCircle2" color="text-green-400" />
                    <StatCard label="失败" :value="String(srv.calls_failed)" icon="AlertCircle" color="text-red-400" />
                    <StatCard label="平均延迟" :value="`${Math.round(srv.avg_latency_ms)}ms`" icon="Clock" />
                  </div>

                  <!-- Last error -->
                  <div v-if="srv.last_error" class="flex items-start gap-2 rounded-lg bg-red-500/5 border border-red-500/10 px-3 py-2">
                    <AlertCircle class="w-3.5 h-3.5 text-red-400/60 mt-0.5 shrink-0" />
                    <p class="text-[11px] text-red-400/80 break-all">{{ srv.last_error }}</p>
                  </div>

                  <!-- Health result -->
                  <div v-if="healthResults[srv.name]" class="flex items-center gap-3 text-[11px]">
                    <span :class="['flex items-center gap-1', healthResults[srv.name].healthy ? 'text-green-400' : 'text-red-400']">
                      <Heart :class="['w-3.5 h-3.5', healthResults[srv.name].healthy ? '' : 'fill-red-400/20']" />
                      健康检查: {{ healthResults[srv.name].healthy ? '正常' : '异常' }}
                    </span>
                    <span class="text-gray-600">{{ Math.round(healthResults[srv.name].latency_ms) }}ms · {{ formatUptime(healthResults[srv.name].uptime_seconds) }} 运行时间</span>
                    <button @click.stop="handleHealthCheck(srv.name)" :disabled="healthChecking === srv.name" class="text-brand-400 hover:text-brand-300 ml-auto">
                      <RefreshCw :class="['w-3 h-3', { 'animate-spin': healthChecking === srv.name }]" />
                    </button>
                  </div>
                </div>
              </ExpandPanel>
            </div>
          </div>
        </main>
      </section>
    </div>
  </div>
</template>

<!-- ── 子组件 ── -->
<script lang="ts">
import { h, type FunctionalComponent } from "vue"
import { Activity, AlertCircle, CheckCircle2, Clock, Globe, Heart, Server, Terminal, Wrench } from "lucide-vue-next"

const iconMap: Record<string, any> = { Globe, Server, Terminal, Wrench, Activity, CheckCircle2, AlertCircle, Clock, Heart }
const statIconMap: Record<string, any> = { Activity, CheckCircle2, AlertCircle, Clock, }

/* StatRow — 左侧栏统计行 */
export const StatRow: FunctionalComponent<{ icon?: string; label?: string; value?: number; color?: string }> = (props) =>
  h("div", { class: "flex items-center justify-between text-xs text-gray-500 py-1.5" }, [
    h("span", { class: "flex items-center gap-1.5" }, [
      iconMap[props.icon || ""] ? h(iconMap[props.icon], { class: "w-3 h-3" }) : null,
      props.label,
    ]),
    h("span", { class: ["tabular-nums", props.color || ""] }, `${props.value ?? ""}`),
  ])

/* ExpandPanel — 折叠面板 */
export const ExpandPanel: FunctionalComponent = (_, { slots }) =>
  h("div", { class: "expand-panel" }, slots.default?.())

/* StatCard — 统计卡片 */
export const StatCard: FunctionalComponent<{ label?: string; value?: string | number; icon?: string; color?: string }> = (props) =>
  h("div", { class: "rounded-lg bg-white/[0.02] border border-white/5 px-3 py-2 text-center" }, [
    statIconMap[props.icon || ""] ? h(statIconMap[props.icon], { class: `w-3.5 h-3.5 mx-auto mb-1 ${props.color || "text-gray-400"}` }) : null,
    h("div", { class: `text-sm font-semibold ${props.color || "text-gray-400"}` }, `${props.value ?? ""}`),
    h("div", { class: "text-[10px] text-gray-600" }, props.label || ""),
  ])
</script>
<style scoped>
/* ── Transitions ── */
.toast-enter-active,.toast-leave-active{transition:all .3s cubic-bezier(.4,0,.2,1)}
.toast-enter-from,.toast-leave-to{opacity:0;transform:translateY(-12px) translateX(-50%)}
.fade-enter-active{transition:opacity .2s}.fade-leave-active{transition:opacity .15s}
.fade-enter-from,.fade-leave-to{opacity:0}

/* ── Shared input styles ── */
.mcp-input{width:100%;border-radius:.75rem;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.03);padding:1rem 1.5rem;font-size:.875rem;color:#fff;transition:border-color .15s,box-shadow .15s}.mcp-input::placeholder{color:#6b7280}.mcp-input:focus{outline:none;border-color:rgba(99,102,241,.4);box-shadow:0 0 0 1px rgba(99,102,241,.2)}
.mcp-input:focus{box-shadow:none}
.mcp-number{width:4rem;border-radius:.5rem;border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.03);padding:.25rem .5rem;font-size:.875rem;text-align:center;outline:none;transition:border-color .15s}.mcp-number:focus{border-color:rgba(99,102,241,.4)}

/* ── Buttons ── */
.mcp-btn-primary{display:inline-flex;align-items:center;gap:.5rem;padding:.5rem 1rem;border-radius:.75rem;background:var(--color-brand-500,#6366f1)}.mcp-btn-primary:hover{background:var(--color-brand-600,#4f46e5)}.mcp-btn-primary:disabled{opacity:.4}.mcp-btn-primary,.mcp-btn-secondary{font-size:.875rem;font-weight:500;color:#fff;transition:color .15s,background .15s}
.mcp-btn-secondary{padding:.5rem 1rem;border-radius:.75rem;font-size:.875rem;color:#9ca3af}.mcp-btn-secondary:hover{color:#fff}

/* ── Action icons (hover reveal) ── */
.action-icon{display:flex;align-items:center;justify-content:center;padding:.375rem;border-radius:.5rem;font-size:.875rem;color:#4b5563;transition:color .15s,background .15s}.action-icon:hover{color:#d1d5db;background:rgba(255,255,255,.05)}
.action-icon:disabled{opacity:.4;cursor:not-allowed}

/* ── Card hover effect ── */
.mcp-server-card:hover{border-color:white/12;background:white/[0.025]}
.mcp-server-card:hover .action-icon{opacity:1!important}
.mcp-market-card:hover{border-color:rgba(255,255,255,.12);background:rgba(255,255,255,.03)}

/* ── Scrollbar hide for mobile tabs ── */
.hide-scrollbar::-webkit-scrollbar{height:0;display:none}
.hide-scrollbar{-ms-overflow-style:none;scrollbar-width:none}
</style>
