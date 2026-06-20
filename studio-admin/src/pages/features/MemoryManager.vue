<template>
  <div class="p-6 max-w-7xl mx-auto">
    <header class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-white">长期记忆</h1>
        <p class="text-gray-400 mt-1 text-sm">借鉴 Open WebUI Memory — 向量化跨对话记忆，Agent 可检索</p>
      </div>
      <button @click="openCreate" class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-500 text-white hover:bg-brand-600 transition-colors text-sm font-medium">
        <Plus class="w-4 h-4" /> 添加记忆
      </button>
    </header>

    <!-- 统计卡片 -->
    <div v-if="stats" class="grid grid-cols-2 md:grid-cols-6 gap-3 mb-6">
      <div class="p-3 rounded-xl bg-gray-800/50 border border-gray-700/50 text-center">
        <span class="block text-xs text-gray-500">总记忆数</span>
        <span class="text-lg font-bold text-white mt-0.5">{{ stats.total_memories }}</span>
      </div>
      <div class="p-3 rounded-xl bg-gray-800/50 border border-gray-700/50 text-center">
        <span class="block text-xs text-gray-500">总访问次数</span>
        <span class="text-lg font-bold text-white mt-0.5">{{ stats.total_accesses }}</span>
      </div>
      <div v-for="(count, domain) in stats.by_domain" :key="domain" class="p-3 rounded-xl bg-gray-800/50 border border-gray-700/50 text-center">
        <span class="block text-xs text-gray-500">{{ domain }}</span>
        <span class="text-lg font-bold text-white mt-0.5">{{ count }}</span>
      </div>
    </div>

    <!-- 语义搜索 -->
    <div class="p-4 rounded-xl bg-gray-800/50 border border-gray-700/50 mb-6">
      <div class="flex items-center gap-2">
        <Search class="w-4 h-4 text-gray-500" />
        <input v-model="searchQuery" @keyup.enter="searchMemories" class="flex-1 bg-transparent text-sm text-white placeholder-gray-500 outline-none" placeholder="语义搜索记忆..." />
        <button @click="searchMemories" class="px-3 py-1.5 rounded-lg bg-brand-500 text-white text-sm hover:bg-brand-600">搜索</button>
      </div>
      <div v-if="searchResults.length" class="mt-3 space-y-2">
        <div v-for="r in searchResults" :key="r.id" class="p-3 rounded-lg bg-gray-900/50 border border-gray-700/30">
          <div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs rounded-full bg-brand-500/15 text-brand-400">{{ r.domain }}</span>
            <span class="text-sm text-green-400">{{ (r.similarity * 100).toFixed(0) }}%</span>
            <span class="text-xs text-gray-500">重要性 {{ r.importance }}</span>
          </div>
          <div class="text-sm text-white mt-1 font-medium">{{ r.key }}</div>
          <div class="text-xs text-gray-400 mt-0.5">{{ r.value.slice(0, 200) }}{{ r.value.length > 200 ? '...' : '' }}</div>
        </div>
      </div>
    </div>

    <!-- 记忆列表 -->
    <div class="flex gap-2 mb-4">
      <button v-for="d in domains" :key="d" @click="filterDomain = d; page = 1; fetchMemories()"
        :class="['px-3 py-1 rounded-lg text-sm transition-colors', filterDomain === d ? 'bg-brand-500/15 text-brand-400' : 'text-gray-400 hover:text-white hover:bg-gray-700/50']">
        {{ d === '' ? '全部' : d }}
      </button>
    </div>

    <div v-if="loading" class="text-center py-16 text-gray-500">加载中...</div>
    <div v-else-if="!memories.length" class="flex flex-col items-center justify-center py-20">
      <Database class="w-12 h-12 text-gray-600" />
      <p class="text-gray-500 mt-3">暂无记忆</p>
    </div>
    <div v-else class="space-y-2 mb-6">
      <div v-for="m in memories" :key="m.id" class="p-4 rounded-xl bg-gray-800/50 border border-gray-700/50 hover:border-gray-600/50">
        <div class="text-sm font-semibold text-white">{{ m.key }}</div>
        <div class="text-sm text-gray-400 mt-1">{{ m.value }}</div>
        <div class="flex items-center gap-3 mt-2">
          <span class="px-2 py-0.5 text-xs rounded-full bg-brand-500/15 text-brand-400">{{ m.domain }}</span>
          <span class="text-xs text-gray-500">重要性: {{ m.importance }}</span>
          <span class="text-xs text-gray-500">访问: {{ m.access_count }} 次</span>
          <div class="ml-auto flex gap-1">
            <button @click="editMemory(m)" class="p-1 rounded text-gray-500 hover:text-white hover:bg-gray-700/50" title="编辑"><Pencil class="w-3.5 h-3.5" /></button>
            <button @click="deleteMemory(m.id)" class="p-1 rounded text-gray-500 hover:text-red-400 hover:bg-red-500/10" title="删除"><Trash2 class="w-3.5 h-3.5" /></button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="total > size" class="flex items-center justify-center gap-3">
      <button :disabled="page <= 1" @click="page--; fetchMemories()" class="px-3 py-1 rounded bg-gray-800 text-gray-400 text-sm hover:bg-gray-700 disabled:opacity-30">&laquo;</button>
      <span class="text-sm text-gray-400">{{ page }} / {{ Math.ceil(total / size) }}</span>
      <button :disabled="page >= Math.ceil(total / size)" @click="page++; fetchMemories()" class="px-3 py-1 rounded bg-gray-800 text-gray-400 text-sm hover:bg-gray-700 disabled:opacity-30">&raquo;</button>
    </div>

    <!-- 创建/编辑弹窗 -->
    <Teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" @click.self="showModal = false">
        <div class="w-full max-w-md bg-gray-900 rounded-2xl border border-gray-700/50 p-6">
          <h2 class="text-lg font-bold text-white mb-4">{{ editingId ? '编辑记忆' : '添加记忆' }}</h2>
          <div class="space-y-3">
            <label class="block text-sm text-gray-400">
              Key（简短摘要）
              <input v-model="form.key" class="w-full mt-1 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-500" placeholder="如：用户喜欢 TypeScript" />
            </label>
            <label class="block text-sm text-gray-400">
              Value（完整内容）
              <textarea v-model="form.value" rows="4" class="w-full mt-1 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-500 resize-none" placeholder="记忆的详细内容..."></textarea>
            </label>
            <label class="block text-sm text-gray-400">
              Domain
              <select v-model="form.domain" class="w-full mt-1 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white outline-none">
                <option value="general">general</option>
                <option value="personal">personal</option>
                <option value="project">project</option>
                <option value="code">code</option>
              </select>
            </label>
            <label class="block text-sm text-gray-400">
              重要性 ({{ form.importance }})
              <input v-model.number="form.importance" type="range" min="0" max="1" step="0.1" class="w-full mt-1 accent-brand-500" />
            </label>
          </div>
          <div class="flex justify-end gap-3 mt-6">
            <button @click="showModal = false" class="px-4 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700/50 text-sm">取消</button>
            <button @click="saveMemory" class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-500 text-white hover:bg-brand-600 transition-colors text-sm font-medium" :disabled="!form.key || !form.value">
              {{ editingId ? '保存' : '添加' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus, Search, Database, Pencil, Trash2 } from 'lucide-vue-next'
import { memoryApi, type MemoryEntry, type MemoryStats } from '@/api/model-features'

const memories = ref<MemoryEntry[]>([]); const loading = ref(true)
const page = ref(1); const size = ref(20); const total = ref(0)
const searchQuery = ref(''); const searchResults = ref<any[]>([])
const filterDomain = ref(''); const domains = ref(['', 'general', 'personal', 'project', 'code'])
const stats = ref<MemoryStats | null>(null)

async function fetchMemories() { loading.value = true; try { const res = await memoryApi.list({ page: page.value, size: size.value, domain: filterDomain.value || undefined }); memories.value = res.data.data; total.value = res.data.total } finally { loading.value = false } }
async function searchMemories() { if (!searchQuery.value) return; const res = await memoryApi.search(searchQuery.value, filterDomain.value || undefined); searchResults.value = res.data.results }
async function fetchStats() { const res = await memoryApi.stats(); stats.value = res.data }

const showModal = ref(false); const editingId = ref<string | null>(null)
const form = ref({ key: '', value: '', domain: 'general', importance: 0.5 })

function openCreate() { editingId.value = null; form.value = { key: '', value: '', domain: 'general', importance: 0.5 }; showModal.value = true }
function editMemory(m: MemoryEntry) { editingId.value = m.id; form.value = { key: m.key, value: m.value, domain: m.domain, importance: m.importance }; showModal.value = true }

async function saveMemory() { if (editingId.value) await memoryApi.update(editingId.value, form.value); else await memoryApi.create(form.value); showModal.value = false; await Promise.all([fetchMemories(), fetchStats()]) }
async function deleteMemory(id: string) { if (!confirm('确定删除此记忆？')) return; await memoryApi.delete(id); await Promise.all([fetchMemories(), fetchStats()]) }

onMounted(() => { fetchMemories(); fetchStats() })
</script>
