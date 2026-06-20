<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  listMCPServers,
  addMCPServer,
  removeMCPServer,
  discoverMCPTools,
  registerMCPTools,
  type MCPServer,
  type MCPAddServerPayload,
} from '@/api/mcp'
import { Server, Plus, Trash2, Link, Terminal, Loader2, Check, X, RefreshCw, Zap } from 'lucide-vue-next'

const servers = ref<MCPServer[]>([])
const loading = ref(true)
const error = ref('')
const connectResult = ref('')

// 添加表单
const showAddForm = ref(false)
const newServer: Ref<MCPAddServerPayload> = ref({
  name: '',
  transport: 'sse',
  url: '',
  command: '',
  args: [],
  auto_discover: true,
  timeout: 30,
})
const adding = ref(false)

onMounted(() => refresh())

const refresh = async () => {
  loading.value = true
  try {
    const res = await listMCPServers()
    servers.value = res.data.servers ?? []
  } catch (e: unknown) {
    error.value = (e as Error).message || '加载失败'
  } finally {
    loading.value = false
  }
}

const handleAdd = async () => {
  if (!newServer.value.name.trim()) return
  adding.value = true
  connectResult.value = ''
  try {
    const res = await addMCPServer(newServer.value)
    connectResult.value = res.data.success
      ? `连接成功，发现 ${res.data.tools_discovered || 0} 个工具`
      : `连接失败: ${res.data.message}`
    if (res.data.success) {
      showAddForm.value = false
      newServer.value = { name: '', transport: 'sse', url: '', command: '', args: [], auto_discover: true, timeout: 30 }
    }
    await refresh()
  } catch (e: unknown) {
    error.value = (e as Error).message || '添加失败'
  } finally {
    adding.value = false
  }
}

const handleRemove = async (name: string) => {
  if (!confirm(`确定断开并移除 MCP 服务器 "${name}"？`)) return
  try {
    await removeMCPServer(name)
    await refresh()
  } catch (e: unknown) {
    error.value = (e as Error).message || '移除失败'
  }
}

const handleDiscover = async () => {
  try {
    const res = await discoverMCPTools()
    connectResult.value = `发现 ${res.data.total} 个工具`
  } catch (e: unknown) {
    error.value = (e as Error).message || '扫描失败'
  }
}

const handleRegister = async () => {
  try {
    const res = await registerMCPTools()
    connectResult.value = res.data.message
  } catch (e: unknown) {
    error.value = (e as Error).message || '注册失败'
  }
}

const transportLabel: Record<string, string> = {
  sse: 'SSE',
  streamable_http: 'HTTP Stream',
  stdio: 'Stdio',
}
</script>

<script lang="ts">
import { type Ref } from 'vue'
</script>

<template>
  <div class="space-y-6">
    <!-- 页头 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">MCP 服务器</h1>
        <p class="text-sm text-gray-500 mt-1">管理 Model Context Protocol 服务器，扩展 Agent 能力</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="rounded-lg bg-white/5 hover:bg-white/10 px-3 py-2 text-xs text-gray-400 hover:text-gray-200 transition-colors flex items-center gap-1.5"
          @click="handleDiscover"
        >
          <RefreshCw class="w-3.5 h-3.5" />
          扫描工具
        </button>
        <button
          class="rounded-lg bg-white/5 hover:bg-white/10 px-3 py-2 text-xs text-gray-400 hover:text-gray-200 transition-colors flex items-center gap-1.5"
          @click="handleRegister"
        >
          <Zap class="w-3.5 h-3.5" />
          注册工具
        </button>
        <button
          class="flex items-center gap-2 rounded-lg bg-brand-500 hover:bg-brand-600 px-4 py-2.5 text-sm font-medium transition-colors"
          @click="showAddForm = !showAddForm"
        >
          <Plus class="w-4 h-4" />
          添加服务器
        </button>
      </div>
    </div>

    <!-- 提示信息 -->
    <div v-if="connectResult" :class="[
      'rounded-lg border px-4 py-3 text-sm',
      connectResult.includes('成功') ? 'bg-green-500/10 border-green-500/20 text-green-400' : 'bg-red-500/10 border-red-500/20 text-red-400'
    ]">
      {{ connectResult }}
    </div>
    <div v-if="error" class="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-400 flex justify-between">
      {{ error }}
      <button @click="error = ''"><X class="w-4 h-4" /></button>
    </div>

    <!-- 添加表单 -->
    <div v-if="showAddForm" class="rounded-xl border border-white/10 bg-surface-800 p-6 space-y-4">
      <h3 class="text-sm font-semibold text-gray-200">添加 MCP 服务器</h3>
      <div class="grid gap-4 grid-cols-1 md:grid-cols-2">
        <div>
          <label class="block text-xs font-medium text-gray-400 mb-1">名称 *</label>
          <input v-model="newServer.name" class="w-full rounded-lg border border-white/10 bg-surface-900 px-3 py-2 text-sm placeholder-gray-600 focus:border-brand-500/50 focus:outline-none" placeholder="my-mcp-server" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-400 mb-1">传输类型</label>
          <select v-model="newServer.transport" class="w-full rounded-lg border border-white/10 bg-surface-900 px-3 py-2 text-sm focus:border-brand-500/50 focus:outline-none">
            <option value="sse">SSE</option>
            <option value="streamable_http">Streamable HTTP</option>
            <option value="stdio">Stdio</option>
          </select>
        </div>
      </div>

      <div v-if="newServer.transport !== 'stdio'">
        <label class="block text-xs font-medium text-gray-400 mb-1">URL</label>
        <input v-model="newServer.url" class="w-full rounded-lg border border-white/10 bg-surface-900 px-3 py-2 text-sm placeholder-gray-600 focus:border-brand-500/50 focus:outline-none" placeholder="http://localhost:3001/sse" />
      </div>

      <div v-if="newServer.transport === 'stdio'">
        <label class="block text-xs font-medium text-gray-400 mb-1">命令</label>
        <input v-model="newServer.command" class="w-full rounded-lg border border-white/10 bg-surface-900 px-3 py-2 text-sm placeholder-gray-600 focus:border-brand-500/50 focus:outline-none" placeholder="node /path/to/server.js" />
      </div>

      <div class="flex items-center gap-4">
        <label class="flex items-center gap-2 text-xs text-gray-400">
          <input v-model="newServer.auto_discover" type="checkbox" class="rounded border-white/20 bg-surface-900" />
          自动发现工具
        </label>
        <label class="text-xs text-gray-400">
          超时
          <input v-model.number="newServer.timeout" type="number" class="ml-1 w-16 rounded border border-white/10 bg-surface-900 px-2 py-1 text-sm focus:border-brand-500/50 focus:outline-none" />
          秒
        </label>
      </div>

      <div class="flex gap-3">
        <button :disabled="adding" class="rounded-lg bg-brand-500 hover:bg-brand-600 disabled:opacity-50 px-4 py-2 text-sm font-medium transition-colors flex items-center gap-2" @click="handleAdd">
          <Loader2 v-if="adding" class="w-4 h-4 animate-spin" />
          <Server v-else class="w-4 h-4" />
          连接
        </button>
        <button class="rounded-lg text-gray-500 hover:text-gray-300 px-4 py-2 text-sm transition-colors" @click="showAddForm = false">取消</button>
      </div>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="py-20 text-center text-gray-500">
      <Loader2 class="w-6 h-6 animate-spin mx-auto mb-2 text-brand-400" />
      加载中...
    </div>

    <!-- 空状态 -->
    <div v-else-if="!servers.length" class="py-20 text-center">
      <Server class="w-10 h-10 text-gray-600 mx-auto mb-3" />
      <p class="text-gray-400 text-sm">暂无 MCP 服务器</p>
      <p class="text-gray-600 text-xs mt-1">点击"添加服务器"连接外部 MCP 服务</p>
    </div>

    <!-- 服务器列表 -->
    <div v-else class="space-y-3">
      <div
        v-for="srv in servers"
        :key="srv.name"
        class="rounded-xl border border-white/10 bg-surface-800 hover:border-white/15 transition-colors p-5"
      >
        <div class="flex items-start justify-between">
          <div class="flex items-start gap-3">
            <div :class="[
              'w-9 h-9 rounded-lg flex items-center justify-center shrink-0',
              srv.connected ? 'bg-green-500/10' : 'bg-gray-500/10'
            ]">
              <Server :class="['w-4 h-4', srv.connected ? 'text-green-400' : 'text-gray-500']" />
            </div>
            <div>
              <div class="flex items-center gap-2">
                <h3 class="text-sm font-semibold text-gray-200">{{ srv.name }}</h3>
                <span :class="[
                  'rounded-full px-2 py-0.5 text-[10px] font-medium',
                  srv.connected ? 'bg-green-500/15 text-green-400' : 'bg-gray-500/15 text-gray-500'
                ]">
                  {{ srv.connected ? '已连接' : '未连接' }}
                </span>
              </div>
              <p class="text-xs text-gray-500 mt-0.5">
                {{ transportLabel[srv.transport] || srv.transport }}
                <span v-if="srv.url"> · {{ srv.url }}</span>
                <span v-if="srv.command"> · {{ srv.command }}</span>
              </p>
              <div class="flex items-center gap-3 mt-2 text-xs text-gray-600">
                <span>{{ srv.tools_count || 0 }} 个工具</span>
                <span>{{ srv.timeout }}s 超时</span>
              </div>
            </div>
          </div>
          <button
            class="rounded-lg p-2 text-gray-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
            @click="handleRemove(srv.name)"
          >
            <Trash2 class="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
