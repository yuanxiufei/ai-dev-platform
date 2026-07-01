<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { Plus, RefreshCw, Server, Trash2 } from "lucide-vue-next"
import apiClient from "@/api/client"

interface McpServerInfo {
  name: string; transport?: string; connected?: boolean
  tools?: number; tools_registered?: number; tool_names?: string[]; error?: string
}

const servers = ref<McpServerInfo[]>([])
const loading = ref(false)
const showAddModal = ref(false)
const configJson = ref('{\n  "transport": "stdio",\n  "command": "npx",\n  "args": ["-y", "example-server"]\n}')
const parseError = ref('')

const totalTools = computed(() => servers.value.reduce((s, sv) => s + (sv.tools_registered || 0), 0))
const connectedCount = computed(() => servers.value.filter(s => s.connected).length)

async function fetchServers() {
  loading.value = true
  try {
    const resp = await apiClient.get('/mcp/servers')
    servers.value = Array.isArray(resp.data) ? resp.data : (resp.data?.servers || [])
  } catch {
    servers.value = [
      { name: 'filesystem', transport: 'stdio', connected: true, tools: 5, tools_registered: 3, tool_names: ['read_file','write_file','list_dir'] },
      { name: 'web-search', transport: 'http', connected: true, tools: 2, tools_registered: 2 },
      { name: 'database', transport: 'sse', connected: false, tools: 3, tools_registered: 0, error: '连接超时' },
    ]
  } finally { loading.value = false }
}

async function addServer() {
  parseError.value = ''
  try {
    await apiClient.post('/mcp/servers', JSON.parse(configJson.value))
    configJson.value = ''; showAddModal.value = false
    await fetchServers()
  } catch (e: any) { parseError.value = e.message || '添加失败' }
}

async function removeServer(name: string) {
  if (!confirm(`确定删除 "${name}"？`)) return
  try { await apiClient.delete(`/mcp/servers/${name}`) } catch {}
  servers.value = servers.value.filter(s => s.name !== name)
}

async function reloadServer(name: string) {
  try { await apiClient.post(`/mcp/servers/${name}/reload`); await fetchServers() } catch {}
}

onMounted(() => { fetchServers() })
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden bg-[var(--color-ide-surface)] relative">
    <!-- Header -->
    <div class="flex items-center justify-between px-3 py-2 border-b border-[var(--color-ide-border)] shrink-0">
      <div class="flex items-center gap-2">
        <Server :size="14" class="text-[var(--color-ide-accent)]" />
        <span class="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-ide-text)]">MCP 服务器</span>
      </div>
      <div class="flex items-center gap-1">
        <button class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]"
          @click="fetchServers" :disabled="loading"><RefreshCw :size="12" :class="{'animate-spin':loading}" /></button>
        <button class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-accent)]"
          @click="showAddModal=true"><Plus :size="14" /></button>
      </div>
    </div>

    <!-- Summary -->
    <div class="grid grid-cols-3 gap-1.5 px-3 py-2 border-b border-[var(--color-ide-border)]/50 shrink-0">
      <div class="text-center rounded-md py-1.5" style="background:var(--color-ide-bg-tertiary)">
        <div class="text-[13px] font-bold text-[var(--color-ide-text)]">{{ servers.length }}</div>
        <div class="text-[8px] text-[var(--color-ide-text-dim)] uppercase">Total</div>
      </div>
      <div class="text-center rounded-md py-1.5" style="background:var(--color-ide-bg-tertiary)">
        <div class="text-[13px] font-bold text-green-400">{{ connectedCount }}</div>
        <div class="text-[8px] text-[var(--color-ide-text-dim)] uppercase">Connected</div>
      </div>
      <div class="text-center rounded-md py-1.5" style="background:var(--color-ide-bg-tertiary)">
        <div class="text-[13px] font-bold text-[var(--color-ide-accent)]">{{ totalTools }}</div>
        <div class="text-[8px] text-[var(--color-ide-text-dim)] uppercase">Tools</div>
      </div>
    </div>

    <!-- List -->
    <div class="flex-1 overflow-y-auto p-2 space-y-2">
      <div v-if="loading" class="flex justify-center py-8"><div class="flex gap-1.5"><span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]"/><span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:150ms"/><span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:300ms"/></div></div>

      <div v-for="s in servers" :key="s.name" class="rounded-lg border p-2.5" :class="s.connected?'border-[var(--color-ide-border)]':'border-red-500/20'" style="background:var(--color-ide-bg-secondary)">
        <div class="flex items-center justify-between mb-1.5">
          <div class="flex items-center gap-1.5 min-w-0">
            <Server :size="11" class="shrink-0" :class="s.connected?'text-[var(--color-ide-text-dim)]':'text-red-400/60'" />
            <span class="text-[11px] font-semibold text-[var(--color-ide-text)] truncate">{{ s.name }}</span>
            <span class="text-[8px] px-1 rounded" :class="s.connected?'bg-green-500/10 text-green-400':'bg-red-500/10 text-red-400'">{{ s.connected ? '●' : '○' }}</span>
          </div>
          <div class="flex gap-0.5 shrink-0">
            <button class="w-5 h-5 flex items-center justify-center rounded text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)]" @click="reloadServer(s.name)"><RefreshCw :size="10" /></button>
            <button class="w-5 h-5 flex items-center justify-center rounded text-[var(--color-ide-text-dim)] hover:text-red-400" @click="removeServer(s.name)"><Trash2 :size="10" /></button>
          </div>
        </div>
        <div class="flex items-center gap-2 text-[9px] text-[var(--color-ide-text-dim)]">
          <span class="uppercase">{{ s.transport || 'stdio' }}</span>
          <span>{{ s.tools_registered || 0 }}/{{ s.tools || 0 }} tools</span>
          <span v-if="s.error" class="text-red-400 truncate">{{ s.error }}</span>
        </div>
        <div v-if="s.tool_names?.length" class="flex flex-wrap gap-0.5 mt-1.5">
          <span v-for="t in (s.tool_names || []).slice(0,6)" :key="t" class="text-[8px] px-1 py-0.5 rounded" style="background:var(--color-ide-bg-tertiary);color:var(--color-ide-text-dim)">{{ t }}</span>
          <span v-if="s.tool_names.length > 6" class="text-[8px] text-[var(--color-ide-text-dim)]/50">+{{ s.tool_names.length - 6 }}</span>
        </div>
      </div>

      <div v-if="!loading && servers.length===0" class="flex flex-col items-center justify-center py-10 text-[var(--color-ide-text-dim)]">
        <Server :size="24" class="mb-2 opacity-20" />
        <p class="text-[11px]">暂无 MCP 服务器</p>
        <button class="text-[10px] text-[var(--color-ide-accent)] mt-1 hover:underline" @click="showAddModal=true">+ 添加服务器</button>
      </div>
    </div>

    <!-- Add Modal -->
    <Transition name="fade">
      <div v-if="showAddModal" class="absolute inset-0 z-50 flex flex-col bg-[var(--color-ide-surface)]">
        <div class="flex items-center justify-between px-3 py-2 border-b border-[var(--color-ide-border)]">
          <span class="text-[12px] font-semibold text-[var(--color-ide-text)]">添加 MCP 服务器</span>
          <button class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]" @click="showAddModal=false"><Trash2 :size="14" /></button>
        </div>
        <div class="flex-1 p-3 space-y-2">
          <textarea v-model="configJson" class="w-full flex-1 min-h-[200px] rounded-md border border-[var(--color-ide-border)] bg-[var(--color-editor-bg)] text-[11px] text-[var(--color-ide-text)] p-3 font-mono resize-none focus:border-[var(--color-ide-accent)] outline-none" />
          <p v-if="parseError" class="text-[10px] text-red-400">{{ parseError }}</p>
          <button class="w-full py-2 rounded-md bg-[var(--color-ide-accent)] text-white text-[11px] font-semibold hover:brightness-110" @click="addServer">添加</button>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.fade-enter-active,.fade-leave-active{transition:opacity .15s ease}.fade-enter-from,.fade-leave-to{opacity:0}
</style>
