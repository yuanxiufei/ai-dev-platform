<template>
  <div class="p-6 max-w-7xl mx-auto">
    <header class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-white">模型预设</h1>
        <p class="text-gray-400 mt-1 text-sm">借鉴 Open WebUI — 将 system_prompt / 工具 / 知识库 / 参数打包为可复用预设</p>
      </div>
      <button @click="openCreate" class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-500 text-white hover:bg-brand-600 transition-colors text-sm font-medium">
        <Plus class="w-4 h-4" /> 创建预设
      </button>
    </header>

    <!-- 搜索 -->
    <div class="flex items-center gap-2 mb-6 px-3 py-2 rounded-lg bg-gray-800/50 border border-gray-700/50">
      <Search class="w-4 h-4 text-gray-500" />
      <input v-model="search" @input="debouncedSearch" placeholder="搜索预设名称..." class="flex-1 bg-transparent text-sm text-white placeholder-gray-500 outline-none" />
    </div>

    <!-- 预设卡片列表 -->
    <div v-if="loading" class="text-center py-16 text-gray-500">加载中...</div>
    <div v-else-if="!presets.length" class="flex flex-col items-center justify-center py-20">
      <Layers class="w-12 h-12 text-gray-600" />
      <p class="text-gray-500 mt-3">暂无预设，创建第一个吧</p>
    </div>
    <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div v-for="p in presets" :key="p.id" class="p-4 rounded-xl bg-gray-800/50 border border-gray-700/50 hover:border-gray-600/50 transition-colors">
        <div class="flex items-start justify-between mb-3">
          <div>
            <h3 class="text-base font-semibold text-white">{{ p.name }}</h3>
            <p class="text-sm text-gray-400 mt-0.5">{{ p.description || '无描述' }}</p>
          </div>
          <div class="flex gap-1.5 shrink-0">
            <span v-if="p.is_public" class="px-2 py-0.5 text-xs rounded-full bg-green-500/15 text-green-400">公开</span>
            <span class="px-2 py-0.5 text-xs rounded-full bg-brand-500/15 text-brand-400">{{ p.model_name || '自动' }}</span>
          </div>
        </div>

        <div class="grid grid-cols-4 gap-2 mb-3">
          <div class="text-center"><span class="block text-xs text-gray-500">温度</span><span class="text-sm text-gray-300">{{ p.temperature ?? '默认' }}</span></div>
          <div class="text-center"><span class="block text-xs text-gray-500">工具</span><span class="text-sm text-gray-300">{{ p.tools?.length || 0 }} 个</span></div>
          <div class="text-center"><span class="block text-xs text-gray-500">知识库</span><span class="text-sm text-gray-300">{{ p.knowledge_bases?.length || 0 }} 个</span></div>
          <div class="text-center"><span class="block text-xs text-gray-500">使用</span><span class="text-sm text-gray-300">{{ p.usage_count }} 次</span></div>
        </div>

        <div v-if="p.system_prompt" class="p-2 rounded-lg bg-gray-900/50 mb-3">
          <span class="text-xs text-gray-500">System Prompt:</span>
          <p class="text-sm text-gray-300 mt-1 line-clamp-2">{{ p.system_prompt }}</p>
        </div>

        <div class="flex gap-2">
          <button @click="applyPreset(p.id)" class="inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-gray-400 hover:text-white hover:bg-gray-700/50 transition-colors"><Play class="w-3.5 h-3.5" /> 应用</button>
          <button @click="openEdit(p)" class="inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-gray-400 hover:text-white hover:bg-gray-700/50 transition-colors"><Pencil class="w-3.5 h-3.5" /> 编辑</button>
          <button @click="deletePreset(p.id)" class="inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"><Trash2 class="w-3.5 h-3.5" /> 删除</button>
        </div>
      </div>
    </div>

    <!-- 分页 -->
    <div v-if="total > size" class="flex items-center justify-center gap-3 mt-6">
      <button :disabled="page <= 1" @click="page--; fetchPresets()" class="px-3 py-1 rounded bg-gray-800 text-gray-400 text-sm hover:bg-gray-700 disabled:opacity-30">&laquo;</button>
      <span class="text-sm text-gray-400">{{ page }} / {{ Math.ceil(total / size) }}</span>
      <button :disabled="page >= Math.ceil(total / size)" @click="page++; fetchPresets()" class="px-3 py-1 rounded bg-gray-800 text-gray-400 text-sm hover:bg-gray-700 disabled:opacity-30">&raquo;</button>
    </div>

    <!-- 创建/编辑弹窗 -->
    <Teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" @click.self="showModal = false">
        <div class="w-full max-w-lg bg-gray-900 rounded-2xl border border-gray-700/50 p-6 max-h-[85vh] overflow-y-auto">
          <h2 class="text-lg font-bold text-white mb-4">{{ editingId ? '编辑预设' : '创建预设' }}</h2>
          <div class="space-y-3">
            <label class="block text-sm text-gray-400">
              名称 *
              <input v-model="form.name" class="w-full mt-1 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-500" placeholder="如：代码生成专家" />
            </label>
            <label class="block text-sm text-gray-400">
              描述
              <input v-model="form.description" class="w-full mt-1 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-500" placeholder="简短描述此预设的用途" />
            </label>
            <label class="block text-sm text-gray-400">
              绑定模型
              <input v-model="form.model_name" class="w-full mt-1 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-500" placeholder="留空则自动选择最佳模型" />
            </label>
            <label class="block text-sm text-gray-400">
              Temperature ({{ form.temperature ?? '默认' }})
              <input v-model.number="form.temperature" type="range" min="0" max="2" step="0.1" class="w-full mt-1 accent-brand-500" />
            </label>
            <label class="block text-sm text-gray-400">
              Max Tokens
              <input v-model.number="form.max_tokens" type="number" class="w-full mt-1 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-500" placeholder="留空使用默认" />
            </label>
            <label class="block text-sm text-gray-400">
              System Prompt（支持动态变量 <code v-pre>{{ USER_NAME }}</code>）
              <textarea v-model="form.system_prompt" rows="5" class="w-full mt-1 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-500 resize-none"
                :placeholder="'你是专业的...\n当前用户: {{ USER_NAME }}\n日期: {{ CURRENT_DATE }}'"
              ></textarea>
            </label>
            <label class="block text-sm text-gray-400">
              绑定工具（逗号分隔）
              <input v-model="toolsText" class="w-full mt-1 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-500" placeholder="web_search, codebase_search" />
            </label>
            <label class="flex items-center gap-2 text-sm text-gray-400">
              <input v-model="form.force_tools" type="checkbox" class="accent-brand-500" />
              强制绑定工具（不允许 LLM 选择不调用）
            </label>
            <label class="flex items-center gap-2 text-sm text-gray-400">
              <input v-model="form.is_public" type="checkbox" class="accent-brand-500" />
              公开预设
            </label>
          </div>
          <div class="flex justify-end gap-3 mt-6">
            <button @click="showModal = false" class="px-4 py-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-700/50 text-sm">取消</button>
            <button @click="savePreset" class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-500 text-white hover:bg-brand-600 transition-colors text-sm font-medium" :disabled="!form.name">
              {{ editingId ? '保存' : '创建' }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Plus, Search, Layers, Play, Pencil, Trash2 } from 'lucide-vue-next'
import { presetApi, type ModelPreset } from '@/api/model-features'

const presets = ref<ModelPreset[]>([])
const loading = ref(true)
const page = ref(1); const size = ref(20); const total = ref(0); const search = ref('')

let searchTimer: ReturnType<typeof setTimeout> | null = null
function debouncedSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { page.value = 1; fetchPresets() }, 300)
}

async function fetchPresets() {
  loading.value = true
  try {
    const res = await presetApi.list({ page: page.value, size: size.value, search: search.value || undefined })
    presets.value = res.data.data; total.value = res.data.total
  } finally { loading.value = false }
}

const showModal = ref(false)
const editingId = ref<string | null>(null)
const form = ref({ name: '', description: '', model_name: '', system_prompt: '', temperature: null as number | null, max_tokens: null as number | null, tools: [] as string[], force_tools: false, is_public: false })
const toolsText = ref('')

function openCreate() {
  editingId.value = null
  form.value = { name: '', description: '', model_name: '', system_prompt: '', temperature: null, max_tokens: null, tools: [], force_tools: false, is_public: false }
  toolsText.value = ''; showModal.value = true
}

function openEdit(p: ModelPreset) {
  editingId.value = p.id
  form.value = { name: p.name, description: p.description || '', model_name: p.model_name || '', system_prompt: p.system_prompt || '', temperature: p.temperature, max_tokens: p.max_tokens, tools: p.tools || [], force_tools: p.force_tools, is_public: p.is_public }
  toolsText.value = (p.tools || []).join(', '); showModal.value = true
}

async function savePreset() {
  const data = { ...form.value, tools: toolsText.value ? toolsText.value.split(',').map(t => t.trim()).filter(Boolean) : [] }
  if (editingId.value) await presetApi.update(editingId.value, data)
  else await presetApi.create(data)
  showModal.value = false; await fetchPresets()
}

async function applyPreset(id: string) { await presetApi.apply(id); await fetchPresets() }
async function deletePreset(id: string) { if (!confirm('确定删除此预设？')) return; await presetApi.delete(id); await fetchPresets() }

onMounted(fetchPresets)
</script>

<style>
.line-clamp-2 { overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
</style>
