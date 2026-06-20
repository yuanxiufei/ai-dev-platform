<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { skillsApi, type SkillInfo, type SkillCreate } from '@/api/skills'
import {
  Search, RefreshCw, Plus, Eye, Zap, FileText, Sparkles, X, Trash2, Edit3,
  Layers, Code2, Beaker, BookOpen, Shield, Wrench, Bot,
} from 'lucide-vue-next'
import ToggleSwitch from '@/components/ToggleSwitch.vue'

const skills = ref<SkillInfo[]>([])
const categories = ref<{ name: string; count: number }[]>([])
const selectedCategory = ref('')
const searchQuery = ref('')
const loading = ref(false)
const showPreview = ref('')
const previewName = ref('')
const showSystemPrompt = ref('')
const appliedSkills = ref<Set<string>>(new Set())
const editingSkill = ref<string | null>(null)
const toast = ref('')

const form = reactive({
  name: '', description: '', category: 'general', content: '', tags: [] as string[],
  author: '', version: '1.0',
})
const tagInput = ref('')

function showToast(msg: string) { toast.value = msg; setTimeout(() => { toast.value = '' }, 3000) }

const categoryMeta: Record<string, any> = {
  general: Layers, 'code-review': Search, testing: Beaker,
  documentation: BookOpen, security: Shield, deployment: Bot, devops: Wrench, 'code-generation': Code2,
}

const filtered = computed(() => {
  let list = skills.value
  if (selectedCategory.value) list = list.filter(s => s.category === selectedCategory.value)
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(s => s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q))
  }
  return list
})

const grouped = computed(() => {
  const map: Record<string, SkillInfo[]> = {}
  for (const s of filtered.value) {
    const cat = s.category || '未分类'
    if (!map[cat]) map[cat] = []
    map[cat].push(s)
  }
  return Object.entries(map).sort()
})

async function loadSkills() {
  loading.value = true
  try {
    const [sRes, cRes] = await Promise.all([skillsApi.list(), skillsApi.categories()])
    skills.value = (sRes.data.skills || sRes.data || []) as SkillInfo[]
    const cats = cRes?.data?.categories || []
    categories.value = cats.map((c: unknown) => typeof c === 'string' ? { name: c, count: 0 } : c as any)
  } finally { loading.value = false }
}

async function reloadFromDisk() { await skillsApi.load(); await loadSkills(); showToast('技能已刷新') }
async function toggleSkill(name: string) { await skillsApi.toggle(name); await loadSkills() }

async function applySkills(names: string[]) {
  try {
    const res = await skillsApi.apply(names)
    showSystemPrompt.value = res.data.system_prompt
    names.forEach(n => { appliedSkills.value.add(n) })
  } catch { /* */ }
}

async function createSkill() {
  if (!form.name || !form.content) return
  const payload: SkillCreate = {
    name: form.name, description: form.description, category: form.category,
    content: form.content, tags: form.tags, author: form.author, version: form.version,
  }
  try {
    if (editingSkill.value) {
      await skillsApi.update(editingSkill.value, payload)
      showToast('技能已更新')
    } else {
      await skillsApi.create(payload)
      showToast('技能已创建')
    }
    editingSkill.value = null
    resetForm()
    await loadSkills()
  } catch (e: any) { showToast(e?.response?.data?.detail || '操作失败') }
}

async function deleteSkill(name: string) {
  if (!confirm(`确定删除技能 "${name}"？`)) return
  try {
    await skillsApi.delete(name)
    showToast('技能已删除')
    await loadSkills()
  } catch (e: any) { showToast(e?.response?.data?.detail || '删除失败') }
}

function editSkill(skill: SkillInfo) {
  editingSkill.value = skill.name
  form.name = skill.name
  form.description = skill.description
  form.category = skill.category
  form.content = skill.content
  form.tags = [...(skill.tags || [])]
  form.author = skill.author || ''
  form.version = skill.version || '1.0'
  // scroll to form
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function addTag() { const t = tagInput.value.trim(); if (t && !form.tags.includes(t)) { form.tags.push(t); tagInput.value = '' } }
function removeTag(t: string) { const i = form.tags.indexOf(t); if (i !== -1) form.tags.splice(i, 1) }
function resetForm() { form.name = ''; form.description = ''; form.category = 'general'; form.content = ''; form.tags = []; form.author = ''; form.version = '1.0'; tagInput.value = '' }

onMounted(loadSkills)

const enabledCount = computed(() => skills.value.filter(s => s.enabled).length)
const isEditing = computed(() => !!editingSkill.value)
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
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-yellow-500/20 to-orange-500/10 border border-yellow-500/20 flex items-center justify-center">
            <Sparkles class="w-5 h-5 text-yellow-400" />
          </div>
          技能指令
        </h1>
        <p class="text-sm text-gray-500 mt-1.5 ml-[3.25rem]">为 AI 助手激活技能 — 按特定方式处理代码审查、测试生成、部署等任务</p>
      </div>
      <div class="flex gap-2">
        <button @click="reloadFromDisk" class="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-sm text-gray-400 hover:text-white transition-colors">
          <RefreshCw class="w-4 h-4" /> 刷新
        </button>
        <button @click="editingSkill = null; resetForm(); showPreview = ''" class="flex items-center gap-1.5 px-4 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium transition-colors shadow-lg shadow-brand-500/15">
          <Plus class="w-4 h-4" /> 创建技能
        </button>
      </div>
    </div>

    <div class="flex-1 flex overflow-hidden">
      <div class="w-52 shrink-0 border-r border-white/5 p-4 space-y-1 overflow-y-auto">
        <p class="text-[11px] font-medium text-gray-500 uppercase tracking-wider px-2 mb-3">分类</p>
        <button @click="selectedCategory = ''" :class="['w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all duration-200 text-left', selectedCategory === '' ? 'bg-brand-500/10 text-brand-400 font-medium' : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]']">
          <Layers class="w-4 h-4 shrink-0" /> 全部 <span class="ml-auto text-xs text-gray-600">{{ skills.length }}</span>
        </button>
        <button v-for="c in categories" :key="c.name" @click="selectedCategory = c.name"
          :class="['w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all duration-200 text-left', selectedCategory === c.name ? 'bg-brand-500/10 text-brand-400 font-medium' : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]']">
          <component :is="categoryMeta[c.name] || Layers" class="w-4 h-4 shrink-0" />
          {{ c.name }} <span class="ml-auto text-xs text-gray-600">{{ c.count }}</span>
        </button>
        <div class="mt-6 px-2">
          <div class="flex items-center gap-1.5 text-xs text-gray-600">
            <div class="w-1.5 h-1.5 rounded-full bg-green-400" />
            <span>{{ enabledCount }} 已启用</span>
          </div>
        </div>
      </div>

      <div class="flex-1 overflow-y-auto p-6">
        <!-- Edit/Create Form -->
        <div v-if="isEditing || (!isEditing && showPreview === '' && filtered.length > 0)" class="mb-6 rounded-2xl border border-yellow-500/15 bg-white/[0.02] p-5 space-y-4">
          <div class="flex items-center gap-2 mb-2">
            <component :is="isEditing ? Edit3 : Plus" class="w-4 h-4 text-yellow-400" />
            <h3 class="text-sm font-semibold text-white">{{ isEditing ? '编辑技能' : '创建技能 (在下方填写)' }}</h3>
            <button v-if="isEditing" @click="editingSkill = null; resetForm()" class="ml-auto text-xs text-gray-500 hover:text-white transition-colors">取消编辑</button>
          </div>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1">名称 <span class="text-red-400">*</span></label>
              <input v-model="form.name" :disabled="isEditing" placeholder="如: code-reviewer" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-yellow-500/40 transition-all disabled:opacity-50" />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1">分类</label>
              <input v-model="form.category" placeholder="general" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-yellow-500/40 transition-all" />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1">标签</label>
              <div class="flex gap-1">
                <input v-model="tagInput" @keyup.enter="addTag" placeholder="回车添加" class="flex-1 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-yellow-500/40 transition-all" />
                <button @click="addTag" class="px-3 py-1.5 rounded-lg bg-white/[0.04] text-sm text-gray-400 hover:text-white transition-colors">+</button>
              </div>
              <div v-if="form.tags.length" class="flex flex-wrap gap-1 mt-1.5">
                <span v-for="t in form.tags" :key="t" class="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-yellow-500/10 text-yellow-400">{{ t }}<button @click="removeTag(t)" class="hover:text-red-400"><X class="w-3 h-3" /></button></span>
              </div>
            </div>
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-400 mb-1">描述</label>
            <input v-model="form.description" placeholder="简要说明用途" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-yellow-500/40 transition-all" />
          </div>
          <div>
            <label class="block text-xs font-medium text-gray-400 mb-1">Markdown 指令 <span class="text-red-400">*</span></label>
            <textarea v-model="form.content" rows="6" placeholder="# 技能指令内容&#10;&#10;你是一个专业的代码审查员，请遵循以下规则：&#10;1. 检查代码安全性&#10;2. 分析性能瓶颈" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white font-mono placeholder-gray-600 focus:outline-none focus:border-yellow-500/40 transition-all resize-none"></textarea>
          </div>
          <div class="flex gap-3 justify-end">
            <button v-if="isEditing" @click="editingSkill = null; resetForm()" class="px-4 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-sm text-gray-400 hover:text-white transition-colors">取消</button>
            <button @click="createSkill()" :disabled="!form.name || !form.content" class="px-5 py-2.5 rounded-xl bg-yellow-500 hover:bg-yellow-600 disabled:opacity-40 disabled:cursor-not-allowed text-black text-sm font-medium transition-colors">{{ isEditing ? '保存修改' : '创建技能' }}</button>
          </div>
        </div>

        <!-- Search -->
        <div class="relative max-w-lg mb-6">
          <Search class="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-600" />
          <input v-model="searchQuery" placeholder="搜索技能名称或描述..." class="w-full bg-white/[0.03] border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-500/40 focus:bg-white/[0.05] transition-all" />
        </div>

        <!-- Applied banner -->
        <div v-if="appliedSkills.size > 0" class="mb-4 px-4 py-2.5 rounded-xl bg-brand-500/10 border border-brand-500/15 flex items-center gap-2">
          <Zap class="w-4 h-4 text-brand-400 shrink-0" />
          <span class="text-sm text-brand-300">已激活 {{ appliedSkills.size }} 个技能</span>
          <button @click="showSystemPrompt = ''; appliedSkills.clear()" class="ml-auto text-xs text-gray-400 hover:text-white transition-colors">清除</button>
        </div>

        <!-- Loading -->
        <div v-if="loading" class="flex items-center justify-center py-24">
          <RefreshCw class="w-8 h-8 text-gray-500 animate-spin" />
        </div>

        <!-- Empty -->
        <div v-else-if="filtered.length === 0" class="flex flex-col items-center justify-center py-24 text-gray-600">
          <Sparkles class="w-12 h-12 mb-4 opacity-30" />
          <p class="text-sm">暂无技能</p>
          <p class="text-xs mt-1 opacity-70">创建一个技能来定制 AI 的行为</p>
        </div>

        <!-- Grouped list -->
        <div v-else class="space-y-8">
          <section v-for="[cat, items] in grouped" :key="cat">
            <h2 class="flex items-center gap-2 text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">
              <component :is="categoryMeta[cat] || Layers" class="w-3.5 h-3.5" /> {{ cat }}
              <span class="text-[10px] text-gray-600 font-normal lowercase">{{ items.length }} 项</span>
            </h2>
            <div class="space-y-2">
              <div v-for="skill in items" :key="skill.name"
                class="flex items-start gap-4 p-4 rounded-xl bg-white/[0.02] border border-white/5 hover:border-white/15 transition-all duration-200 group">
                <div class="pt-1 shrink-0">
                  <ToggleSwitch :model-value="skill.enabled" size="sm" @update:model-value="toggleSkill(skill.name)" />
                </div>
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-1">
                    <h3 class="text-sm font-medium text-white truncate">{{ skill.name }}</h3>
                    <span class="text-[10px] px-1.5 py-0.5 rounded bg-brand-500/10 text-brand-400 font-medium shrink-0">{{ skill.category }}</span>
                    <span class="text-[10px] text-gray-600 shrink-0">v{{ skill.version }} · {{ skill.usage_count || 0 }} 次</span>
                  </div>
                  <p class="text-xs text-gray-500 mb-2 line-clamp-2">{{ skill.description || '无描述' }}</p>
                  <div class="flex items-center gap-1.5">
                    <span v-for="tag in (skill.tags || [])" :key="tag" class="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.03] border border-white/5 text-gray-500">{{ tag }}</span>
                  </div>
                </div>
                <div class="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                  <button @click="showPreview = skill.content; previewName = skill.name; showSystemPrompt = ''" title="查看指令" class="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 transition-colors"><FileText class="w-4 h-4" /></button>
                  <button @click="applySkills([skill.name])" title="应用" class="p-1.5 rounded-lg hover:bg-brand-500/15 text-brand-400 transition-colors"><Zap class="w-4 h-4" /></button>
                  <button @click="editSkill(skill)" title="编辑" class="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 transition-colors"><Edit3 class="w-4 h-4" /></button>
                  <button @click="deleteSkill(skill.name)" title="删除" class="p-1.5 rounded-lg hover:bg-red-500/10 text-red-400 transition-colors"><Trash2 class="w-4 h-4" /></button>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>

    <!-- Preview modal -->
    <Teleport to="body">
      <div v-if="showPreview || showSystemPrompt" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" @click.self="showPreview = ''; showSystemPrompt = ''">
        <div class="bg-surface-900 rounded-2xl border border-white/10 w-[680px] max-h-[80vh] flex flex-col shadow-2xl">
          <div class="flex items-center justify-between p-5 border-b border-white/8">
            <h3 class="font-semibold text-white">{{ showSystemPrompt ? 'System Prompt 预览' : `技能: ${previewName}` }}</h3>
            <button @click="showPreview = ''; showSystemPrompt = ''" class="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 transition-colors"><X class="w-4 h-4" /></button>
          </div>
          <pre class="flex-1 overflow-auto p-5 text-sm text-gray-300 whitespace-pre-wrap font-mono leading-relaxed">{{ showSystemPrompt || showPreview }}</pre>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.toast-enter-active, .toast-leave-active { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(-12px) translateX(-50%); }
</style>
