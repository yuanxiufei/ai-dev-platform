<script setup lang="ts">
import { Cloud, Database, Globe, HardDrive, Server } from "lucide-vue-next"
import { computed, onMounted, ref } from "vue"
import {
  connectIntegration,
  createIntegration,
  deleteIntegration,
  disconnectIntegration,
  getIntegrationStats,
  type IntegrationCreatePayload,
  type IntegrationItem,
  listIntegrations,
} from "@/api/integrations"

const integrations = ref<IntegrationItem[]>([])
const loading = ref(true)
const connectingId = ref<string | null>(null)
const toast = ref("")

const activeCategory = ref("all")
const showCreate = ref(false)
const _showConfig = ref<IntegrationItem | null>(null)

const form = ref<IntegrationCreatePayload>({
  name: "",
  display_name: "",
  description: "",
  category: "service",
  config: {},
})

const formApiKey = ref("")
const formUrl = ref("")
const formToken = ref("")

const _categories = [
  { id: "all", label: "全部", icon: Globe },
  { id: "database", label: "数据库", icon: Database },
  { id: "deploy", label: "部署服务", icon: Cloud },
  { id: "storage", label: "对象存储", icon: HardDrive },
  { id: "service", label: "代码仓库", icon: Server },
]

// 预设集成模板
const presetIntegrations = [
  {
    name: "supabase",
    display_name: "Supabase",
    description: "PostgreSQL 数据库、认证、存储一体化后端",
    category: "database",
    icon: "🗄️",
  },
  {
    name: "tcb",
    display_name: "CloudBase",
    description: "微信云开发 — 数据库、云函数、存储、托管",
    category: "database",
    icon: "☁️",
  },
  {
    name: "cloudStudio",
    display_name: "Cloud Studio",
    description: "一键部署到远程开发服务器",
    category: "deploy",
    icon: "💻",
  },
  {
    name: "eop",
    display_name: "EdgeOne Pages",
    description: "前端项目快速部署到全球边缘网络",
    category: "deploy",
    icon: "🌍",
  },
  {
    name: "lighthouse",
    display_name: "Lighthouse",
    description: "轻量应用服务器实例管理与部署",
    category: "deploy",
    icon: "🖥️",
  },
  {
    name: "vercel",
    display_name: "Vercel",
    description: "前端项目一键部署与预览",
    category: "deploy",
    icon: "▲",
  },
  {
    name: "netlify",
    display_name: "Netlify",
    description: "Jamstack 部署与边缘函数",
    category: "deploy",
    icon: "🔺",
  },
  {
    name: "planetscale",
    display_name: "PlanetScale",
    description: "Serverless MySQL 数据库",
    category: "database",
    icon: "🐬",
  },
  {
    name: "s3",
    display_name: "S3 / MinIO",
    description: "对象存储服务 — 文件上传与托管",
    category: "storage",
    icon: "🪣",
  },
  {
    name: "github",
    display_name: "GitHub",
    description: "代码仓库连接、PR 管理、Actions 部署",
    category: "service",
    icon: "🐙",
  },
]

const stats = ref({
  total: 0,
  connected: 0,
  by_category: {} as Record<string, number>,
})
const _filtered = computed(() => {
  if (activeCategory.value === "all") return integrations.value
  return integrations.value.filter((i) => i.category === activeCategory.value)
})

function showToast(msg: string) {
  toast.value = msg
  setTimeout(() => {
    toast.value = ""
  }, 3000)
}

async function fetchData() {
  loading.value = true
  try {
    const res = await listIntegrations()
    integrations.value = res.data.data || []
  } catch {
    /* */
  }
  try {
    const s = await getIntegrationStats()
    stats.value = s.data
  } catch {
    /* */
  } finally {
    loading.value = false
  }
}

async function _handleConnect(integration: IntegrationItem) {
  if (connectingId.value) return
  connectingId.value = integration.id
  try {
    const res = await connectIntegration(integration.id, {
      config: integration.config || {},
    })
    integration.connected = res.data.data?.connected ?? true
    integration.status = "connected"
    showToast(`已连接 ${integration.display_name}`)
    fetchData()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "连接失败")
    integration.status = "disconnected"
  } finally {
    connectingId.value = null
  }
}

async function _handleDisconnect(integration: IntegrationItem) {
  if (!confirm(`确定断开 ${integration.display_name}？`)) return
  try {
    await disconnectIntegration(integration.id)
    integration.connected = false
    integration.status = "disconnected"
    showToast(`已断开 ${integration.display_name}`)
    fetchData()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "断开失败")
  }
}

async function _handleDelete(id: string) {
  if (!confirm("确定删除此集成？")) return
  try {
    await deleteIntegration(id)
    showToast("集成已删除")
    fetchData()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "删除失败")
  }
}

async function _handleCreate() {
  if (!form.value.name || !form.value.display_name) return
  const config: Record<string, unknown> = {}
  if (formApiKey.value) config.api_key = formApiKey.value
  if (formUrl.value) config.url = formUrl.value
  if (formToken.value) config.token = formToken.value
  form.value.config = config

  try {
    await createIntegration(form.value)
    showCreate.value = false
    form.value = {
      name: "",
      display_name: "",
      description: "",
      category: "service",
      config: {},
    }
    formApiKey.value = ""
    formUrl.value = ""
    formToken.value = ""
    showToast("集成已注册")
    fetchData()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "注册失败")
  }
}

function _usePreset(preset: (typeof presetIntegrations)[0]) {
  form.value = {
    name: preset.name,
    display_name: preset.display_name,
    description: preset.description,
    category: preset.category,
    config: {},
  }
  showCreate.value = true
}

onMounted(fetchData)
</script>

<template>
  <div class="h-full flex flex-col">
    <Transition name="toast">
      <div v-if="toast" class="fixed top-6 left-1/2 -translate-x-1/2 z-50 px-5 py-2.5 rounded-xl text-sm font-medium bg-green-500/15 border border-green-500/25 text-green-400 backdrop-blur-xl shadow-xl">
        {{ toast }}
      </div>
    </Transition>

    <!-- Header -->
    <div class="flex items-center justify-between px-8 pt-8 pb-6 border-b border-white/5">
      <div>
        <h1 class="text-2xl font-bold text-white flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500/20 to-cyan-500/10 border border-blue-500/20 flex items-center justify-center">
            <Link2 class="w-5 h-5 text-blue-400" />
          </div>
          集成服务
        </h1>
        <p class="text-sm text-gray-500 mt-1.5 ml-[3.25rem]">连接后端云服务和外部工具，扩展平台能力</p>
      </div>
      <button @click="showCreate = true" class="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium transition-colors shadow-lg shadow-brand-500/15">
        <Plus class="w-4 h-4" />
        注册集成
      </button>
    </div>

    <div class="flex-1 flex overflow-hidden">
      <div class="w-52 shrink-0 border-r border-white/5 p-4 space-y-1">
        <p class="text-[11px] font-medium text-gray-500 uppercase tracking-wider px-2 mb-3">服务分类</p>
        <button
          v-for="cat in categories" :key="cat.id"
          @click="activeCategory = cat.id"
          :class="['w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all duration-200 text-left', activeCategory === cat.id ? 'bg-brand-500/10 text-brand-400 font-medium' : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]']"
        >
          <component :is="cat.icon" class="w-4 h-4 shrink-0" />
          {{ cat.label }}
          <span class="ml-auto text-xs text-gray-600">{{ cat.id === 'all' ? integrations.length : integrations.filter(i => i.category === cat.id).length }}</span>
        </button>

        <div class="mt-6 px-2">
          <div class="flex items-center gap-1.5 text-xs text-gray-600">
            <div class="w-1.5 h-1.5 rounded-full bg-green-400" />
            <span>{{ stats.connected }} / {{ stats.total }} 已连接</span>
          </div>
        </div>

        <!-- Presets -->
        <div class="mt-6 pt-4 border-t border-white/5">
          <p class="text-[10px] text-gray-600 mb-2 px-2">快速注册</p>
          <div class="space-y-0.5">
            <button
              v-for="p in presetIntegrations.filter(pi => !integrations.find(i => i.name === pi.name))"
              :key="p.name"
              @click="usePreset(p)"
              class="w-full flex items-center gap-2 px-2 py-1.5 rounded-lg text-xs text-gray-500 hover:text-gray-300 hover:bg-white/[0.04] transition-colors text-left"
            >
              <span>{{ p.icon }}</span>
              <span class="truncate">{{ p.display_name }}</span>
              <Plus class="w-3 h-3 ml-auto" />
            </button>
          </div>
        </div>
      </div>

      <!-- Main -->
      <div class="flex-1 overflow-y-auto p-6">
        <div v-if="loading" class="flex items-center justify-center py-24">
          <Loader2 class="w-8 h-8 animate-spin text-blue-400" />
        </div>

        <div v-else-if="!integrations.length" class="flex flex-col items-center justify-center py-24 text-gray-600">
          <Link2 class="w-12 h-12 mb-4 opacity-30" />
          <p class="text-sm mb-4">还没有注册任何集成服务</p>
          <button @click="showCreate = true" class="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-500/15 text-blue-400 hover:bg-blue-500/25 text-sm transition-colors">
            <Plus class="w-4 h-4" /> 注册第一个集成
          </button>
        </div>

        <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          <div
            v-for="item in filtered()"
            :key="item.id"
            :class="['group rounded-2xl border p-5 transition-all duration-200 flex flex-col', item.connected ? 'border-green-500/15 bg-green-500/[0.03] hover:border-green-500/30' : 'border-white/8 bg-white/[0.02] hover:border-white/15 hover:bg-white/[0.04]']"
          >
            <div class="flex items-center gap-3 mb-3">
              <span class="text-2xl leading-none">{{ presetIntegrations.find(p => p.name === item.name)?.icon || '🔌' }}</span>
              <div class="min-w-0 flex-1">
                <h3 class="text-sm font-semibold text-white truncate">{{ item.display_name }}</h3>
                <p class="text-[11px] text-gray-500 mt-0.5">
                  {{ item.last_connected_at ? `上次连接 ${item.last_connected_at.slice(0, 10)}` : item.category }}
                </p>
              </div>
              <div :class="['w-2 h-2 rounded-full shrink-0', item.connected ? 'bg-green-400 shadow-[0_0_6px_rgba(74,222,128,0.4)] animate-pulse' : 'bg-gray-600']" />
            </div>

            <p class="text-xs text-gray-500 leading-relaxed mb-4 flex-1">{{ item.description || '无描述' }}</p>

            <div class="flex items-center gap-2 pt-3 border-t border-white/5">
              <button
                @click="item.connected ? handleDisconnect(item) : handleConnect(item)"
                :disabled="connectingId === item.id"
                :class="['flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all duration-200',
                  item.connected ? 'bg-red-500/10 text-red-400 hover:bg-red-500/20 border border-red-500/20' : 'bg-brand-500/15 text-brand-400 hover:bg-brand-500/25 border border-brand-500/20']"
              >
                <Loader2 v-if="connectingId === item.id" class="w-3.5 h-3.5 animate-spin" />
                <Unlink2 v-else-if="item.connected" class="w-3.5 h-3.5" />
                <Link2 v-else class="w-3.5 h-3.5" />
                {{ connectingId === item.id ? '连接中...' : item.connected ? '断开' : '连接' }}
              </button>
              <button @click="showConfig = item" class="p-2 rounded-lg text-gray-600 hover:text-gray-400 hover:bg-white/5 transition-colors" title="查看详情">
                <Settings2 class="w-3.5 h-3.5" />
              </button>
              <button @click="handleDelete(item.id)" class="p-2 rounded-lg text-gray-600 hover:text-red-400 hover:bg-red-500/10 transition-colors opacity-0 group-hover:opacity-100" title="删除">
                <Trash2 class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Create Modal -->
    <Teleport to="body">
      <div v-if="showCreate" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" @click.self="showCreate = false">
        <div class="bg-surface-900 rounded-2xl border border-white/10 w-[600px] max-h-[85vh] flex flex-col shadow-2xl">
          <div class="flex items-center justify-between p-5 border-b border-white/8">
            <h3 class="text-lg font-semibold text-white flex items-center gap-2"><Plus class="w-4 h-4 text-blue-400" />注册集成</h3>
            <button @click="showCreate = false" class="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 transition-colors"><X class="w-4 h-4" /></button>
          </div>
          <div class="flex-1 overflow-y-auto p-5 space-y-4">
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-xs font-medium text-gray-400 mb-1.5">标识 <span class="text-red-400">*</span></label>
                <input v-model="form.name" placeholder="supabase" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm font-mono text-white placeholder-gray-600 focus:outline-none focus:border-brand-500/40 transition-all" />
              </div>
              <div>
                <label class="block text-xs font-medium text-gray-400 mb-1.5">显示名称 <span class="text-red-400">*</span></label>
                <input v-model="form.display_name" placeholder="Supabase" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-500/40 transition-all" />
              </div>
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1.5">描述</label>
              <input v-model="form.description" placeholder="PostgreSQL 数据库、认证、存储一体化后端" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-500/40 transition-all" />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1.5">分类</label>
              <select v-model="form.category" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white focus:outline-none focus:border-brand-500/40 transition-all">
                <option value="database">数据库</option>
                <option value="deploy">部署服务</option>
                <option value="storage">对象存储</option>
                <option value="service">代码仓库</option>
              </select>
            </div>
            <div class="pt-2 border-t border-white/5">
              <p class="text-[11px] font-medium text-gray-400 mb-3">连接凭据</p>
              <div class="grid grid-cols-1 gap-3">
                <div>
                  <label class="block text-[10px] text-gray-500 mb-1">API Key</label>
                  <input v-model="formApiKey" type="password" placeholder="••••••••" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-500/40 transition-all" />
                </div>
                <div>
                  <label class="block text-[10px] text-gray-500 mb-1">URL / Endpoint</label>
                  <input v-model="formUrl" placeholder="https://api.example.com" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm font-mono text-white placeholder-gray-600 focus:outline-none focus:border-brand-500/40 transition-all" />
                </div>
                <div>
                  <label class="block text-[10px] text-gray-500 mb-1">Token / Secret</label>
                  <input v-model="formToken" type="password" placeholder="••••••••" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-500/40 transition-all" />
                </div>
              </div>
            </div>
          </div>
          <div class="flex gap-3 justify-end p-5 border-t border-white/8">
            <button @click="showCreate = false" class="px-5 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-sm text-gray-400 hover:text-white transition-colors">取消</button>
            <button @click="handleCreate()" :disabled="!form.name || !form.display_name" class="px-5 py-2.5 rounded-xl bg-blue-500 hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors">注册集成</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Config Detail Modal -->
    <Teleport to="body">
      <div v-if="showConfig" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" @click.self="showConfig = null">
        <div class="bg-surface-900 rounded-2xl border border-white/10 w-[500px] max-h-[70vh] flex flex-col shadow-2xl">
          <div class="flex items-center justify-between p-5 border-b border-white/8">
            <h3 class="font-semibold text-white flex items-center gap-2"><Settings2 class="w-4 h-4 text-blue-400" />{{ showConfig.display_name }} 详情</h3>
            <button @click="showConfig = null" class="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 transition-colors"><X class="w-4 h-4" /></button>
          </div>
          <div class="flex-1 overflow-y-auto p-5 space-y-3">
            <div class="flex justify-between text-sm">
              <span class="text-gray-500">状态</span>
              <span :class="showConfig.connected ? 'text-green-400' : 'text-gray-500'">{{ showConfig.connected ? '已连接' : '未连接' }}</span>
            </div>
            <div class="flex justify-between text-sm">
              <span class="text-gray-500">分类</span>
              <span class="text-gray-300">{{ showConfig.category }}</span>
            </div>
            <div v-if="showConfig.config" class="pt-2 border-t border-white/5">
              <p class="text-[11px] text-gray-500 mb-2">配置信息</p>
              <pre class="text-xs text-gray-400 whitespace-pre-wrap font-mono bg-white/[0.02] p-3 rounded-xl">{{ JSON.stringify(showConfig.config, null, 2) }}</pre>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.toast-enter-active, .toast-leave-active { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(-12px) translateX(-50%); }
</style>
