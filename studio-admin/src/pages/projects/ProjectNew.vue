<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { createProject } from '@/api/studio'
import { listTemplates } from '@/api/studio'
import type { Template } from '@/types/studio'
import { ArrowLeft, Plus, Sparkles } from 'lucide-vue-next'
import AppLayout from '@/components/layout/AppLayout.vue'

const router = useRouter()

/* ─── 表单状态 ─── */
const name = ref('')
const description = ref('')
const selectedTemplateId = ref<string>('')
const prompt = ref('')
const mode = ref<'manual' | 'ai'>('manual')
const submitting = ref(false)
const error = ref('')
const templates = ref<Template[]>([])
const templatesLoading = ref(true)

/* ─── 加载模板 ─── */
onMounted(async () => {
  try {
    const res = await listTemplates()
    templates.value = res.data.data ?? []
  } catch {
    // 后端未启动
  } finally {
    templatesLoading.value = false
  }
})

/* ─── 创建项目 ─── */
const handleCreate = async () => {
  error.value = ''

  if (mode === 'manual' && !name.value.trim()) {
    error.value = '请输入项目名称'
    return
  }

  if (mode === 'ai' && !prompt.value.trim()) {
    error.value = '请输入项目描述'
    return
  }

  submitting.value = true
  try {
    const body: Record<string, unknown> = {
      name: name.value.trim() || 'AI 生成项目',
      description: description.value.trim() || prompt.value.trim(),
    }
    if (selectedTemplateId.value) {
      body.template_id = selectedTemplateId.value
    }
    if (mode === 'ai') {
      body.prompt = prompt.value.trim()
    }

    const res = await createProject(body)
    const id = res.data.data?.id ?? 'new'
    router.push(`/projects/${id}`)
  } catch (e: any) {
    error.value = e.response?.data?.detail ?? '创建失败，请重试'
  } finally {
    submitting.value = false
  }
}

/* ─── 使用 AI 快速生成提示 ─── */
const quickPrompts = [
  { label: '落地页', text: '一个现代 SaaS 产品落地页，包含 Hero、特性展示、价格表、CTA' },
  { label: '后台管理', text: '一个数据仪表盘后台，包含侧边栏、统计卡片、表格、图表' },
  { label: '博客', text: '一个技术博客站点，包含文章列表、详情页、标签筛选、搜索' },
  { label: '电商', text: '一个电商网站，包含商品列表、购物车、结算页' },
]
</script>

<template>
  <AppLayout>
    <div class="space-y-6 max-w-2xl">
      <!-- 返回 -->
      <button
        class="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
        @click="router.back()"
      >
        <ArrowLeft class="w-4 h-4" />
        返回列表
      </button>

      <div>
        <h1 class="text-2xl font-bold tracking-tight">创建项目</h1>
        <p class="text-sm text-gray-500 mt-1">手动创建或通过 AI 生成全栈项目</p>
      </div>

      <!-- 模式切换 -->
      <div class="flex rounded-lg bg-surface-800 border border-white/10 p-1">
        <button
          :class="[
            'flex-1 rounded-md px-4 py-2 text-sm font-medium transition-all',
            mode === 'manual'
              ? 'bg-brand-500/20 text-brand-400'
              : 'text-gray-500 hover:text-gray-300',
          ]"
          @click="mode = 'manual'"
        >
          手动创建
        </button>
        <button
          :class="[
            'flex-1 rounded-md px-4 py-2 text-sm font-medium transition-all flex items-center justify-center gap-1.5',
            mode === 'ai'
              ? 'bg-brand-500/20 text-brand-400'
              : 'text-gray-500 hover:text-gray-300',
          ]"
          @click="mode = 'ai'"
        >
          <Sparkles class="w-3.5 h-3.5" />
          AI 生成
        </button>
      </div>

      <!-- 手动模式表单 -->
      <form v-if="mode === 'manual'" class="space-y-4" @submit.prevent="handleCreate">
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1.5">项目名称 *</label>
          <input
            v-model="name"
            type="text"
            class="w-full rounded-lg border border-white/10 bg-surface-800 px-4 py-2.5 text-sm placeholder-gray-600 focus:border-brand-500/50 focus:outline-none transition-colors"
            placeholder="例如：我的电商平台"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1.5">项目描述</label>
          <textarea
            v-model="description"
            rows="3"
            class="w-full rounded-lg border border-white/10 bg-surface-800 px-4 py-2.5 text-sm placeholder-gray-600 focus:border-brand-500/50 focus:outline-none transition-colors resize-none"
            placeholder="简要描述你的项目…"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1.5">
            选择模板
            <span class="font-normal text-gray-600">（可选）</span>
          </label>
          <div v-if="templatesLoading" class="text-sm text-gray-600 py-2">加载模板中…</div>
          <select
            v-else
            v-model="selectedTemplateId"
            class="w-full rounded-lg border border-white/10 bg-surface-800 px-4 py-2.5 text-sm focus:border-brand-500/50 focus:outline-none transition-colors"
          >
            <option value="">不使用模板</option>
            <option v-for="tpl in templates" :key="tpl.id" :value="tpl.id">
              {{ tpl.name }} — {{ tpl.category }}
            </option>
          </select>
        </div>

        <div v-if="error" class="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-2.5 text-sm text-red-400">
          {{ error }}
        </div>

        <button
          type="submit"
          :disabled="submitting"
          class="flex items-center gap-2 rounded-lg bg-brand-500 hover:bg-brand-600 disabled:opacity-50 px-5 py-2.5 text-sm font-medium transition-colors"
        >
          <Plus class="w-4 h-4" />
          {{ submitting ? '创建中…' : '创建项目' }}
        </button>
      </form>

      <!-- AI 模式表单 -->
      <form v-else class="space-y-4" @submit.prevent="handleCreate">
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-1.5">
            <Sparkles class="w-3.5 h-3.5 inline mr-1 text-brand-400" />
            描述你想要的项目
          </label>
          <textarea
            v-model="prompt"
            rows="5"
            class="w-full rounded-lg border border-white/10 bg-surface-800 px-4 py-2.5 text-sm placeholder-gray-600 focus:border-brand-500/50 focus:outline-none transition-colors resize-none"
            placeholder="例如：一个带用户登录的即时聊天应用，支持群聊和私聊，前端用 Vue 3 实现…"
          />
        </div>

        <!-- 快速提示 -->
        <div>
          <label class="block text-sm font-medium text-gray-500 mb-2">快速填充</label>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="qp in quickPrompts"
              :key="qp.label"
              type="button"
              class="rounded-lg border border-white/10 bg-surface-800 px-3 py-1.5 text-xs text-gray-400 hover:text-gray-200 hover:border-brand-500/30 transition-colors"
              @click="prompt = qp.text"
            >
              {{ qp.label }}
            </button>
          </div>
        </div>

        <div v-if="error" class="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-2.5 text-sm text-red-400">
          {{ error }}
        </div>

        <button
          type="submit"
          :disabled="submitting"
          class="flex items-center gap-2 rounded-lg bg-brand-500 hover:bg-brand-600 disabled:opacity-50 px-5 py-2.5 text-sm font-medium transition-colors"
        >
          <Sparkles class="w-4 h-4" />
          {{ submitting ? '生成中…' : 'AI 生成项目' }}
        </button>
      </form>
    </div>
  </AppLayout>
</template>
