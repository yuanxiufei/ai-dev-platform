<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { promptTemplateApi, type PromptTemplateData, type TemplateVariableDef } from '@/api/model-features'
import { RefreshCw, Plus, Search, Trash2, Zap, Copy } from '@/components/icons'

const templates = ref<PromptTemplateData[]>([])
const categories = ref<{ name: string; count: number }[]>([])
const selectedCategory = ref('')
const searchQuery = ref('')
const loading = ref(false)
const showModal = ref(false)
const showResolve = ref(false)
const resolvedResult = ref('')
const editingId = ref<string | null>(null)

const form = reactive({
  command: '', title: '', prompt: '', icon: '',
  category: 'general', description: '',
  variables: {} as Record<string, TemplateVariableDef>,
})
const newVarName = ref('')
const newVarType = ref('string')
const newVarDesc = ref('')
const resolveValues = ref<Record<string, string | number | boolean>>({})

const filtered = computed(() => {
  let list = templates.value
  if (selectedCategory.value) list = list.filter(t => t.category === selectedCategory.value)
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(t => t.command.toLowerCase().includes(q) || t.title.toLowerCase().includes(q))
  }
  return list
})

async function loadTemplates() {
  loading.value = true
  try {
    const [tRes, cRes] = await Promise.all([promptTemplateApi.list(), promptTemplateApi.categories()])
    templates.value = tRes.templates
    categories.value = cRes.categories
  } finally { loading.value = false }
}

function openCreate() { editingId.value = null; resetForm(); showModal.value = true }
function openEdit(tpl: PromptTemplateData) {
  editingId.value = tpl.id
  form.command = tpl.command; form.title = tpl.title; form.prompt = tpl.prompt
  form.icon = tpl.icon; form.category = tpl.category; form.description = tpl.description
  form.variables = { ...tpl.variables }
  showModal.value = true
}

function addVariable() {
  const name = newVarName.value.trim()
  if (!name || form.variables[name]) return
  form.variables[name] = {
    type: newVarType.value,
    default: '',
    description: newVarDesc.value,
    required: false,
    options: [],
  }
  newVarName.value = ''; newVarDesc.value = ''
}

function removeVariable(name: string) { delete form.variables[name] }

async function saveTemplate() {
  if (!form.command || !form.title || !form.prompt) return
  if (editingId.value) {
    await promptTemplateApi.update(editingId.value, { ...form })
  } else {
    await promptTemplateApi.create({ ...form })
  }
  showModal.value = false; resetForm(); loadTemplates()
}

async function deleteTemplate(id: string) {
  if (!confirm('删除此模板？')) return
  await promptTemplateApi.delete(id)
  await loadTemplates()
}

async function resolveTemplate(tpl: PromptTemplateData) {
  resolveValues.value = {}
  for (const name of Object.keys(tpl.variables)) {
    resolveValues.value[name] = String(tpl.variables[name].default || '')
  }
  editingId.value = tpl.id
  showResolve.value = true
}

async function doResolve() {
  const res = await promptTemplateApi.resolve(editingId.value!, resolveValues.value)
  resolvedResult.value = res.resolved_prompt
}

function resetForm() {
  form.command = ''; form.title = ''; form.prompt = ''; form.icon = ''
  form.category = 'general'; form.description = ''; form.variables = {}
}

onMounted(loadTemplates)
</script>

<template>
  <div class="p-6">
    <header class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-white">Prompt 模板</h1>
        <p class="text-sm text-gray-400 mt-1">斜杠命令模板 — 带类型化变量，一键填充 Prompt</p>
      </div>
      <button @click="openCreate" class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 transition text-white text-sm font-medium">
        <Plus class="w-4 h-4" /> 创建模板
      </button>
    </header>

    <!-- Filters -->
    <div class="flex items-center gap-3 mb-4">
      <div class="relative flex-1 max-w-xs">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
        <input v-model="searchQuery" placeholder="搜索命令..." class="w-full pl-9 pr-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-500" />
      </div>
      <select v-model="selectedCategory" class="px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white">
        <option value="">全部</option>
        <option v-for="c in categories" :key="c.name" :value="c.name">{{ c.name }} ({{ c.count }})</option>
      </select>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-12"><RefreshCw class="w-6 h-6 animate-spin text-gray-500" /></div>
    <div v-else-if="filtered.length === 0" class="text-center py-12 text-gray-500">暂无模板</div>
    <div v-else class="grid gap-3">
      <div v-for="tpl in filtered" :key="tpl.id" class="flex items-start gap-4 p-4 rounded-xl bg-surface-800 border border-white/5 hover:border-brand-500/30 transition group">
        <div class="text-xl shrink-0 w-10 h-10 flex items-center justify-center rounded-lg bg-brand-500/10">{{ tpl.icon || '📝' }}</div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <code class="text-sm font-mono text-brand-400">{{ tpl.command }}</code>
            <span class="text-sm font-medium text-white">{{ tpl.title }}</span>
            <span class="text-xs px-1.5 py-0.5 rounded bg-surface-700 text-gray-400">{{ tpl.category }}</span>
          </div>
          <p class="text-sm text-gray-400 mb-1.5 line-clamp-2">{{ tpl.description || tpl.prompt.substring(0, 100) }}</p>
          <div class="flex items-center gap-1 flex-wrap">
            <span v-for="(v, k) in tpl.variables" :key="k" class="text-[11px] px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-400 font-mono">
              &#123;&#123;{{ k }}&#125;&#125;
            </span>
          </div>
        </div>
        <div class="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition">
          <button @click="resolveTemplate(tpl)" title="填充变量" class="p-1.5 rounded-lg hover:bg-green-500/20 transition">
            <Zap class="w-4 h-4 text-green-400" />
          </button>
          <button @click="openEdit(tpl)" title="编辑" class="p-1.5 rounded-lg hover:bg-surface-700 transition text-gray-400 text-sm">✏️</button>
          <button @click="deleteTemplate(tpl.id)" class="p-1.5 rounded-lg hover:bg-red-500/20 transition">
            <Trash2 class="w-4 h-4 text-red-400" />
          </button>
        </div>
      </div>
    </div>

    <!-- Create/Edit Modal -->
    <Teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="showModal = false">
        <div class="bg-surface-900 rounded-xl border border-white/10 w-[680px] max-h-[85vh] flex flex-col">
          <div class="flex items-center justify-between p-4 border-b border-white/10">
            <h3 class="font-medium text-white">{{ editingId ? '编辑模板' : '创建模板' }}</h3>
            <button @click="showModal = false" class="text-gray-400">✕</button>
          </div>
          <div class="flex-1 overflow-auto p-4 space-y-3">
            <div class="grid grid-cols-3 gap-3">
              <div class="col-span-2">
                <label class="block text-xs text-gray-400 mb-1">命令 *</label>
                <input v-model="form.command" placeholder="/gen-api" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm font-mono text-brand-400" />
              </div>
              <div>
                <label class="block text-xs text-gray-400 mb-1">图标 (emoji)</label>
                <input v-model="form.icon" placeholder="⚡" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm" />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-xs text-gray-400 mb-1">标题 *</label>
                <input v-model="form.title" placeholder="生成 API 端点" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white" />
              </div>
              <div>
                <label class="block text-xs text-gray-400 mb-1">分类</label>
                <input v-model="form.category" placeholder="studio" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white" />
              </div>
            </div>
            <div>
              <label class="block text-xs text-gray-400 mb-1">描述</label>
              <input v-model="form.description" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white" />
            </div>
            <div>
              <label class="block text-xs text-gray-400 mb-1">Prompt 模板 *（使用 {<!-- -->{ variable }<!-- -->} 标记变量）</label>
              <textarea v-model="form.prompt" rows="4" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white font-mono resize-none" />
            </div>
            <!-- Variables -->
            <div>
              <label class="block text-xs text-gray-400 mb-1">变量</label>
              <div class="flex gap-2 mb-2">
                <input v-model="newVarName" placeholder="变量名" class="flex-1 px-3 py-1.5 bg-surface-800 border border-white/10 rounded-lg text-sm text-white" />
                <select v-model="newVarType" class="px-3 py-1.5 bg-surface-800 border border-white/10 rounded-lg text-sm text-white">
                  <option value="string">string</option>
                  <option value="number">number</option>
                  <option value="boolean">boolean</option>
                  <option value="select">select</option>
                </select>
                <input v-model="newVarDesc" placeholder="描述" class="flex-1 px-3 py-1.5 bg-surface-800 border border-white/10 rounded-lg text-sm text-white" />
                <button @click="addVariable" class="px-3 py-1.5 rounded-lg bg-brand-500 text-white text-sm">添加</button>
              </div>
              <div class="flex flex-wrap gap-1.5">
                <span v-for="(v, k) in form.variables" :key="k" class="flex items-center gap-1 text-xs px-2 py-1 rounded bg-surface-700 text-gray-300">
                  {{ k }} ({{ v.type }}) <button @click="removeVariable(k)" class="text-red-400 hover:text-red-300">✕</button>
                </span>
              </div>
            </div>
          </div>
          <div class="flex gap-2 justify-end p-4 border-t border-white/10">
            <button @click="showModal = false" class="px-4 py-2 rounded-lg bg-surface-800 hover:bg-surface-700 text-sm">取消</button>
            <button @click="saveTemplate" class="px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium">保存</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Resolve Modal -->
    <Teleport to="body">
      <div v-if="showResolve" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="showResolve = false; resolvedResult = ''">
        <div class="bg-surface-900 rounded-xl border border-white/10 w-[560px] max-h-[80vh] flex flex-col">
          <div class="flex items-center justify-between p-4 border-b border-white/10">
            <h3 class="font-medium text-white">填充变量</h3>
            <button @click="showResolve = false; resolvedResult = ''" class="text-gray-400">✕</button>
          </div>
          <div class="p-4 space-y-3 overflow-auto">
            <div v-for="(v, k) in editingId ? templates.find(t => t.id === editingId)?.variables || {} : {}" :key="k" class="mb-2">
              <label class="block text-xs text-gray-400 mb-1">{{ k }} <span class="text-gray-600">({{ v.type }})</span></label>
              <input v-model="resolveValues[k]" :placeholder="String(v.default || '')" class="w-full px-3 py-1.5 bg-surface-800 border border-white/10 rounded-lg text-sm text-white" />
            </div>
            <button @click="doResolve" class="w-full px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium">填充解析</button>
            <div v-if="resolvedResult" class="relative">
              <pre class="p-3 bg-surface-800 rounded-lg text-sm text-gray-300 whitespace-pre-wrap font-mono">{{ resolvedResult }}</pre>
              <button @click="navigator.clipboard.writeText(resolvedResult)" class="absolute top-2 right-2 p-1.5 rounded-lg bg-surface-700 hover:bg-surface-600 transition" title="复制"><Copy class="w-4 h-4 text-gray-400" /></button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
