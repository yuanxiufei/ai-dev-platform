<script setup lang="ts">
import { onMounted, ref } from "vue"
import {
  type OpenAPIServerInfo,
  type OpenAPIToolSchema,
  openapiDiscoveryApi,
} from "@/api/model-features"
import { Globe, Plus, RefreshCw, Zap } from "lucide-vue-next"

const servers = ref<OpenAPIServerInfo[]>([])
const tools = ref<OpenAPIToolSchema[]>([])
const loading = ref(false)
const selectedServerId = ref("")

const showDiscover = ref(false)
const discoverUrl = ref("")
const discoverName = ref("")

const showToolCall = ref(false)
const callToolId = ref("")
const callArgs = ref("{}")
const callResult = ref<any>(null)

async function loadServers() {
  loading.value = true
  try {
    const res = await openapiDiscoveryApi.servers()
    servers.value = res.data.servers
  } finally {
    loading.value = false
  }
}

async function discover() {
  if (!discoverUrl.value) return
  await openapiDiscoveryApi.discover(discoverUrl.value, discoverName.value)
  showDiscover.value = false
  discoverUrl.value = ""
  discoverName.value = ""
  await loadServers()
}

async function viewTools(serverId: string) {
  selectedServerId.value = serverId
  const res = await openapiDiscoveryApi.tools(serverId)
  tools.value = res.data.tools
}

function openToolCall(tool: OpenAPIToolSchema) {
  callToolId.value = tool.function.name
  const params = tool.function.parameters
  if (params && (params as any).properties) {
    const defaults: Record<string, any> = {}
    for (const k of Object.keys((params as any).properties)) defaults[k] = ""
    callArgs.value = JSON.stringify(defaults, null, 2)
  } else callArgs.value = "{}"
  callResult.value = null
  showToolCall.value = true
}

async function doToolCall() {
  try {
    const args = JSON.parse(callArgs.value)
    const tool = tools.value.find((t) => t.function.name === callToolId.value)
    const server = servers.value.find(
      (s) =>
        s.tools &&
        (s.tools as any[]).some(
          (t: any) => t.function.name === callToolId.value,
        ),
    )
    const toolData = server
      ? (server as any).tools.find(
          (t: any) => t.function.name === callToolId.value,
        )
      : null
    if (toolData?._id) {
      const res = await openapiDiscoveryApi.callTool(toolData._id, args)
      callResult.value = res.data
    }
  } catch (e: any) {
    callResult.value = { error: e.message }
  }
}

onMounted(loadServers)
</script>

<template>
  <div class="p-6 max-w-5xl mx-auto space-y-6">
    <header class="flex items-center justify-between">
      <div>
        <h1 class="text-3xl font-bold text-white">OpenAPI 发现</h1>
        <p class="text-gray-400 mt-2">自动发现 OpenAPI 端点并调用</p>
      </div>
      <button @click="showDiscover = true" class="px-4 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 text-white font-medium flex items-center gap-2 text-sm">
        <Plus class="w-4 h-4" /> 发现
      </button>
    </header>

    <div v-if="loading" class="text-center py-12"><RefreshCw class="w-6 h-6 animate-spin text-gray-500 mx-auto" /></div>
    <div v-else-if="!servers.length" class="text-center py-16 text-gray-500 bg-gray-900/50 rounded-2xl border border-gray-800/50">
      <Globe class="w-10 h-10 mx-auto mb-3 text-gray-600" />
      <p>输入 OpenAPI Spec URL 开始发现</p>
      <button @click="showDiscover = true" class="mt-3 px-4 py-2 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-sm">发现 API</button>
    </div>
    <div v-else class="flex gap-4">
      <div class="w-56 shrink-0 space-y-1">
        <button v-for="svr in servers" :key="svr.id" @click="viewTools(svr.id)"
          :class="['w-full text-left px-3 py-2.5 rounded-xl transition text-sm', selectedServerId === svr.id ? 'bg-brand-500/15 text-brand-400' : 'bg-gray-800/50 hover:bg-gray-800 text-gray-300']">
          <div class="font-medium truncate">{{ svr.name }}</div>
          <div class="text-xs text-gray-500">{{ svr.tool_count }} tools</div>
        </button>
      </div>
      <div class="flex-1">
        <div v-if="!selectedServerId" class="text-center py-16 text-gray-500">选择左侧服务器查看工具</div>
        <div v-else-if="!tools.length" class="text-center py-16 text-gray-500">此服务器无工具</div>
        <div v-else class="space-y-2">
          <div v-for="tool in tools" :key="tool.function.name" class="flex items-center gap-3 p-3 rounded-xl bg-gray-900/50 border border-gray-800/50 hover:border-brand-500/30 transition group">
            <div class="w-8 h-8 flex items-center justify-center rounded-lg bg-green-500/10 text-green-400 text-xs font-mono font-bold">{{ tool.function.name.substring(0, 4).toUpperCase() }}</div>
            <div class="flex-1 min-w-0">
              <code class="text-sm font-mono text-green-400">{{ tool.function.name }}</code>
              <p class="text-xs text-gray-500 line-clamp-1">{{ tool.function.description || '无描述' }}</p>
            </div>
            <button @click="openToolCall(tool)" class="px-2 py-1 rounded-lg text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 transition opacity-0 group-hover:opacity-100">
              <Zap class="w-3 h-3 inline" /> 调用
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- Discover Modal -->
    <Teleport to="body">
      <div v-if="showDiscover" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="showDiscover = false">
        <div class="bg-gray-900 rounded-2xl border border-gray-800 w-[480px] p-6 space-y-4">
          <h3 class="font-medium text-white text-lg">发现 OpenAPI 服务器</h3>
          <div><label class="block text-xs text-gray-400 mb-1">Spec URL *</label><input v-model="discoverUrl" placeholder="https://api.example.com/openapi.json" class="w-full px-3 py-2 bg-gray-800 border border-gray-700/50 rounded-xl text-sm text-white font-mono outline-none" /></div>
          <div><label class="block text-xs text-gray-400 mb-1">名称（可选）</label><input v-model="discoverName" class="w-full px-3 py-2 bg-gray-800 border border-gray-700/50 rounded-xl text-sm text-white outline-none" /></div>
          <div class="flex gap-2 justify-end">
            <button @click="showDiscover = false" class="px-4 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-sm">取消</button>
            <button @click="discover" class="px-4 py-2 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium">发现并注册</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Tool Call Modal -->
    <Teleport to="body">
      <div v-if="showToolCall" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="showToolCall = false">
        <div class="bg-gray-900 rounded-2xl border border-gray-800 w-[520px] max-h-[80vh] flex flex-col">
          <div class="flex items-center justify-between p-4 border-b border-gray-800">
            <h3 class="font-medium text-white">调用: <code class="text-green-400">{{ callToolId }}</code></h3>
            <button @click="showToolCall = false" class="text-gray-400">✕</button>
          </div>
          <div class="p-4 space-y-3 overflow-auto">
            <div><label class="block text-xs text-gray-400 mb-1">参数 (JSON)</label><textarea v-model="callArgs" rows="5" class="w-full px-3 py-2 bg-gray-800 border border-gray-700/50 rounded-xl text-sm text-white font-mono outline-none resize-none" /></div>
            <button @click="doToolCall" class="w-full py-2.5 rounded-xl bg-green-500 hover:bg-green-600 text-white font-medium">执行调用</button>
            <pre v-if="callResult" class="p-3 bg-gray-800 rounded-xl text-xs text-gray-300 whitespace-pre-wrap font-mono max-h-64 overflow-auto">{{ JSON.stringify(callResult, null, 2) }}</pre>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
