<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { openapiDiscoveryApi, type OpenAPIServerInfo, type OpenAPIToolSchema } from '@/api/model-features'
import { RefreshCw, Plus, Search, Trash2, Wrench, ExternalLink, Zap } from '@/components/icons'

const servers = ref<OpenAPIServerInfo[]>([])
const tools = ref<OpenAPIToolSchema[]>([])
const loading = ref(false)
const showDiscover = ref(false)
const discoverUrl = ref('')
const discoverName = ref('')
const selectedServerId = ref('')
const showToolCall = ref(false)
const callToolId = ref('')
const callArgs = ref('{}')
const callResult = ref<any>(null)

async function loadServers() {
  loading.value = true
  try {
    const res = await openapiDiscoveryApi.servers()
    servers.value = res.servers
  } finally { loading.value = false }
}

async function discover() {
  if (!discoverUrl.value) return
  const res = await openapiDiscoveryApi.discover(discoverUrl.value, discoverName.value)
  showDiscover.value = false
  discoverUrl.value = ''; discoverName.value = ''
  await loadServers()
  alert(`发现 ${res.tool_count} 个工具！`)
}

async function viewTools(serverId: string) {
  selectedServerId.value = serverId
  const res = await openapiDiscoveryApi.tools(serverId)
  tools.value = res.tools
}

async function deleteServer(id: string) {
  if (!confirm('删除此服务器？')) return
  await openapiDiscoveryApi.deleteServer(id)
  if (selectedServerId.value === id) { selectedServerId.value = ''; tools.value = [] }
  await loadServers()
}

async function openToolCall(tool: OpenAPIToolSchema) {
  callToolId.value = tool.function.name
  // 从 tool schema 提取参数名
  const params = tool.function.parameters
  if (params && (params as any).properties) {
    const defaults: Record<string, any> = {}
    for (const k of Object.keys((params as any).properties)) {
      defaults[k] = ''
    }
    callArgs.value = JSON.stringify(defaults, null, 2)
  } else {
    callArgs.value = '{}'
  }
  callResult.value = null
  showToolCall.value = true
}

async function doToolCall() {
  try {
    const args = JSON.parse(callArgs.value)
    // 找到 tool ID
    const toolData = tools.value.find(t => t.function.name === callToolId.value)
    if (!toolData) return
    // 从 servers 中找到对应的 tool
    const serverData = servers.value.find(s => s.tools.some((t: any) => t.function.name === callToolId.value))
    if (!serverData) return
    const tool = serverData.tools.find((t: any) => t.function.name === callToolId.value) as any
    if (tool?._id) {
      const res = await openapiDiscoveryApi.callTool(tool._id, args)
      callResult.value = res
    }
  } catch (e: any) {
    callResult.value = { error: e.message }
  }
}

onMounted(loadServers)
</script>

<template>
  <div class="p-6">
    <header class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-white">OpenAPI 发现</h1>
        <p class="text-sm text-gray-400 mt-1">自动发现 OpenAPI 端点并注册为 Agent 工具</p>
      </div>
      <button @click="showDiscover = true" class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium">
        <Plus class="w-4 h-4" /> 发现服务器
      </button>
    </header>

    <!-- Servers -->
    <div v-if="loading" class="flex items-center justify-center py-12"><RefreshCw class="w-6 h-6 animate-spin text-gray-500" /></div>
    <div v-else-if="servers.length === 0" class="text-center py-12 text-gray-500">
      <Wrench class="w-12 h-12 mx-auto mb-3 text-gray-600" />
      <p>暂无 OpenAPI 服务器 — 输入 Spec URL 开始发现</p>
      <button @click="showDiscover = true" class="mt-3 px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-sm">发现第一个 API</button>
    </div>
    <div v-else class="flex gap-4">
      <!-- Left: Server List -->
      <div class="w-64 shrink-0 space-y-1">
        <button v-for="svr in servers" :key="svr.id" @click="viewTools(svr.id)"
          :class="['w-full text-left px-3 py-2.5 rounded-lg transition text-sm', selectedServerId === svr.id ? 'bg-brand-500/15 text-brand-400' : 'bg-surface-800 hover:bg-surface-700 text-gray-300']">
          <div class="font-medium truncate">{{ svr.name }}</div>
          <div class="text-xs text-gray-500">{{ svr.tool_count }} tools · {{ svr.url }}</div>
        </button>
      </div>
      <!-- Right: Tools -->
      <div class="flex-1">
        <div v-if="!selectedServerId" class="text-center py-12 text-gray-500">选择左侧服务器查看工具</div>
        <div v-else-if="tools.length === 0" class="text-center py-12 text-gray-500">此服务器无工具</div>
        <div v-else class="grid gap-2">
          <div v-for="tool in tools" :key="tool.function.name" class="flex items-center gap-3 p-3 rounded-lg bg-surface-800 border border-white/5 hover:border-brand-500/30 transition group">
            <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-green-500/10 text-green-400 text-xs font-mono font-bold">
              {{ tool.function.name.substring(0, 4).toUpperCase() }}
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2">
                <code class="text-sm font-mono text-green-400">{{ tool.function.name }}</code>
              </div>
              <p class="text-xs text-gray-500 line-clamp-1">{{ tool.function.description || '无描述' }}</p>
            </div>
            <button @click="openToolCall(tool)" class="px-2 py-1 rounded text-xs bg-surface-700 hover:bg-green-500/20 text-green-400 transition opacity-0 group-hover:opacity-100">
              <Zap class="w-3.5 h-3.5 inline" /> 调用
            </button>
          </div>
        </div>
        <!-- Delete server -->
        <div v-if="selectedServerId" class="mt-4 pt-3 border-t border-white/10">
          <button @click="deleteServer(selectedServerId)" class="flex items-center gap-1 text-xs text-red-400 hover:text-red-300">
            <Trash2 class="w-3.5 h-3.5" /> 删除此服务器
          </button>
        </div>
      </div>
    </div>

    <!-- Discover Modal -->
    <Teleport to="body">
      <div v-if="showDiscover" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="showDiscover = false">
        <div class="bg-surface-900 rounded-xl border border-white/10 w-[480px] p-6 space-y-4">
          <h3 class="font-medium text-white text-lg">发现 OpenAPI 服务器</h3>
          <div>
            <label class="block text-xs text-gray-400 mb-1">OpenAPI Spec URL *</label>
            <input v-model="discoverUrl" placeholder="https://api.example.com/openapi.json" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white font-mono" />
          </div>
          <div>
            <label class="block text-xs text-gray-400 mb-1">服务器名称（可选）</label>
            <input v-model="discoverName" placeholder="My API" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white" />
          </div>
          <div class="flex gap-2 justify-end">
            <button @click="showDiscover = false" class="px-4 py-2 rounded-lg bg-surface-800 hover:bg-surface-700 text-sm">取消</button>
            <button @click="discover" class="px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium">发现并注册</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Tool Call Modal -->
    <Teleport to="body">
      <div v-if="showToolCall" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="showToolCall = false">
        <div class="bg-surface-900 rounded-xl border border-white/10 w-[520px] max-h-[80vh] flex flex-col">
          <div class="flex items-center justify-between p-4 border-b border-white/10">
            <h3 class="font-medium text-white">调用工具: <code class="text-green-400">{{ callToolId }}</code></h3>
            <button @click="showToolCall = false" class="text-gray-400">✕</button>
          </div>
          <div class="p-4 space-y-3 overflow-auto">
            <div>
              <label class="block text-xs text-gray-400 mb-1">参数 (JSON)</label>
              <textarea v-model="callArgs" rows="5" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white font-mono resize-none" />
            </div>
            <button @click="doToolCall" class="w-full px-4 py-2 rounded-lg bg-green-500 hover:bg-green-600 text-white text-sm font-medium">执行调用</button>
            <pre v-if="callResult" class="p-3 bg-surface-800 rounded-lg text-xs text-gray-300 whitespace-pre-wrap font-mono max-h-64 overflow-auto">{{ JSON.stringify(callResult, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
