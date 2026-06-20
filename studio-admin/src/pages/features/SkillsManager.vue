<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { skillsApi, type SkillInfo } from '@/api/model-features'
import { RefreshCw, Plus, Search, Trash2, Eye, EyeOff, Zap, FileText } from '@/components/icons'

const skills = ref<SkillInfo[]>([])
const categories = ref<{ name: string; count: number }[]>([])
const selectedCategory = ref('')
const searchQuery = ref('')
const loading = ref(false)
const showCreateModal = ref(false)
const showPreview = ref('')
const systemPromptPreview = ref('')

const form = reactive({
  name: '', description: '', category: 'general',
  content: '', author: '', version: '1.0', tags: [] as string[],
})
const tagInput = ref('')

const filtered = computed(() => {
  let list = skills.value
  if (selectedCategory.value) list = list.filter(s => s.category === selectedCategory.value)
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(s => s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q))
  }
  return list
})

async function loadSkills() {
  loading.value = true
  try {
    const [sRes, cRes] = await Promise.all([skillsApi.list(), skillsApi.categories()])
    skills.value = sRes.skills
    categories.value = cRes.categories
  } finally { loading.value = false }
}

async function reloadFromDisk() {
  await skillsApi.load()
  await loadSkills()
}

async function createSkill() {
  if (!form.name || !form.content) return
  await skillsApi.create({
    name: form.name,
    description: form.description,
    category: form.category,
    content: form.content,
    author: form.author,
    version: form.version,
    tags: form.tags,
  })
  showCreateModal.value = false
  resetForm()
  await loadSkills()
}

async function toggleSkill(name: string) {
  await skillsApi.toggle(name)
  await loadSkills()
}

async function deleteSkill(name: string) {
  if (!confirm(`删除技能 "${name}"？`)) return
  await skillsApi.delete(name)
  await loadSkills()
}

async function applySkills(names: string[]) {
  const res = await skillsApi.apply(names)
  systemPromptPreview.value = res.system_prompt
}

function addTag() {
  const t = tagInput.value.trim()
  if (t && !form.tags.includes(t)) { form.tags.push(t); tagInput.value = '' }
}

function removeTag(t: string) { form.tags.splice(form.tags.indexOf(t), 1) }

function resetForm() {
  form.name = ''; form.description = ''; form.category = 'general'
  form.content = ''; form.author = ''; form.version = '1.0'; form.tags = []
  tagInput.value = ''
}

onMounted(loadSkills)
</script>

<template>
  <div class="p-6">
    <header class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-white">Skills 技能管理</h1>
        <p class="text-sm text-gray-400 mt-1">Markdown 技能指令集 — 定义模型完成特定任务的行为方式</p>
      </div>
      <div class="flex gap-2">
        <button @click="reloadFromDisk" class="flex items-center gap-1.5 px-3 py-2 rounded-lg bg-surface-800 hover:bg-surface-700 transition text-sm">
          <RefreshCw class="w-4 h-4" /> 从磁盘加载
        </button>
        <button @click="showCreateModal = true" class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 transition text-white text-sm font-medium">
          <Plus class="w-4 h-4" /> 创建技能
        </button>
      </div>
    </header>

    <!-- Filters -->
    <div class="flex items-center gap-3 mb-4">
      <div class="relative flex-1 max-w-xs">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
        <input v-model="searchQuery" placeholder="搜索技能..." class="w-full pl-9 pr-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white placeholder-gray-500 focus:outline-none focus:border-brand-500" />
      </div>
      <select v-model="selectedCategory" class="px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500">
        <option value="">全部分类</option>
        <option v-for="c in categories" :key="c.name" :value="c.name">{{ c.name }} ({{ c.count }})</option>
      </select>
    </div>

    <!-- Skills Grid -->
    <div v-if="loading" class="flex items-center justify-center py-12">
      <RefreshCw class="w-6 h-6 text-gray-500 animate-spin" />
    </div>
    <div v-else-if="filtered.length === 0" class="text-center py-12 text-gray-500">
      暂无技能 — 创建第一个技能来定义模型行为
    </div>
    <div v-else class="grid gap-3">
      <div v-for="skill in filtered" :key="skill.name"
        class="flex items-start gap-4 p-4 rounded-xl bg-surface-800 border border-white/5 hover:border-brand-500/30 transition group">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <span :class="['w-2 h-2 rounded-full', skill.enabled ? 'bg-green-400' : 'bg-gray-600']" />
            <h3 class="font-medium text-white truncate">{{ skill.name }}</h3>
            <span class="text-xs px-1.5 py-0.5 rounded bg-surface-700 text-gray-400">{{ skill.category }}</span>
            <span class="text-xs text-gray-500">v{{ skill.version }}</span>
            <span class="text-xs text-gray-600 ml-auto">调用 {{ skill.usage_count }} 次</span>
          </div>
          <p class="text-sm text-gray-400 mb-2">{{ skill.description || '无描述' }}</p>
          <div class="flex items-center gap-1.5">
            <span v-for="tag in skill.tags" :key="tag" class="text-[11px] px-1.5 py-0.5 rounded bg-brand-500/10 text-brand-400">{{ tag }}</span>
          </div>
        </div>
        <div class="flex items-center gap-1.5 shrink-0 opacity-0 group-hover:opacity-100 transition">
          <button @click="showPreview = skill.content; systemPromptPreview = ''" title="预览指令" class="p-1.5 rounded-lg hover:bg-surface-700 transition">
            <FileText class="w-4 h-4 text-gray-400" />
          </button>
          <button @click="applySkills([skill.name])" title="生成 System Prompt" class="p-1.5 rounded-lg hover:bg-brand-500/20 transition">
            <Zap class="w-4 h-4 text-brand-400" />
          </button>
          <button @click="toggleSkill(skill.name)" :title="skill.enabled ? '禁用' : '启用'" class="p-1.5 rounded-lg hover:bg-surface-700 transition">
            <Eye v-if="skill.enabled" class="w-4 h-4 text-green-400" />
            <EyeOff v-else class="w-4 h-4 text-gray-600" />
          </button>
          <button @click="deleteSkill(skill.name)" title="删除" class="p-1.5 rounded-lg hover:bg-red-500/20 transition">
            <Trash2 class="w-4 h-4 text-red-400" />
          </button>
        </div>
      </div>
    </div>

    <!-- Preview Modal -->
    <Teleport to="body">
      <div v-if="showPreview || systemPromptPreview" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="showPreview = ''; systemPromptPreview = ''">
        <div class="bg-surface-900 rounded-xl border border-white/10 w-[640px] max-h-[80vh] flex flex-col">
          <div class="flex items-center justify-between p-4 border-b border-white/10">
            <h3 class="font-medium text-white">{{ systemPromptPreview ? 'System Prompt 预览' : '技能内容' }}</h3>
            <button @click="showPreview = ''; systemPromptPreview = ''" class="p-1 rounded-lg hover:bg-surface-700 text-gray-400">✕</button>
          </div>
          <pre class="flex-1 overflow-auto p-4 text-sm text-gray-300 whitespace-pre-wrap font-mono">{{ systemPromptPreview || showPreview }}</pre>
        </div>
      </div>
    </Teleport>

    <!-- Create Modal -->
    <Teleport to="body">
      <div v-if="showCreateModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="showCreateModal = false">
        <div class="bg-surface-900 rounded-xl border border-white/10 w-[640px] max-h-[85vh] flex flex-col">
          <div class="flex items-center justify-between p-4 border-b border-white/10">
            <h3 class="font-medium text-white">创建技能 (Markdown)</h3>
            <button @click="showCreateModal = false; resetForm()" class="p-1 rounded-lg hover:bg-surface-700 text-gray-400">✕</button>
          </div>
          <div class="flex-1 overflow-auto p-4 space-y-3">
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-xs text-gray-400 mb-1">名称 *</label>
                <input v-model="form.name" placeholder="my-skill" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500" />
              </div>
              <div>
                <label class="block text-xs text-gray-400 mb-1">分类</label>
                <input v-model="form.category" placeholder="general" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500" />
              </div>
            </div>
            <div>
              <label class="block text-xs text-gray-400 mb-1">描述</label>
              <input v-model="form.description" placeholder="技能用途描述" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500" />
            </div>
            <div>
              <label class="block text-xs text-gray-400 mb-1">标签</label>
              <div class="flex items-center gap-1 mb-1 flex-wrap">
                <span v-for="t in form.tags" :key="t" class="flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-brand-500/10 text-brand-400">
                  {{ t }} <button @click="removeTag(t)" class="hover:text-red-400">✕</button>
                </span>
              </div>
              <div class="flex gap-1">
                <input v-model="tagInput" @keyup.enter="addTag" placeholder="添加标签" class="flex-1 px-3 py-1.5 bg-surface-800 border border-white/10 rounded-lg text-sm text-white focus:outline-none focus:border-brand-500" />
                <button @click="addTag" class="px-3 py-1.5 rounded-lg bg-surface-800 hover:bg-surface-700 text-sm text-gray-400">添加</button>
              </div>
            </div>
            <div>
              <label class="block text-xs text-gray-400 mb-1">Markdown 指令内容 *</label>
              <textarea v-model="form.content" rows="10"
                placeholder="# Skill 指令内容&#10;&#10;你是一个专业的代码审查员，请遵循以下规则：&#10;1. 检查代码安全性&#10;2. 分析性能瓶颈&#10;3. 提供改进建议"
                class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white font-mono focus:outline-none focus:border-brand-500 resize-none" />
            </div>
          </div>
          <div class="flex gap-2 justify-end p-4 border-t border-white/10">
            <button @click="showCreateModal = false; resetForm()" class="px-4 py-2 rounded-lg bg-surface-800 hover:bg-surface-700 transition text-sm">取消</button>
            <button @click="createSkill" class="px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 transition text-white text-sm font-medium">创建</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
