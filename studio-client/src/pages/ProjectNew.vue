<script setup lang="ts">
/**
 * ProjectNew.vue — AI 全栈项目创建页面
 *
 * 支持两种模式：
 *   1. 手动创建：填写名称/描述/模板
 *   2. AI 生成：自然语言描述 → AI 生成全栈项目
 */
import { onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { createProject, listProjects } from "@/api/studio"
import type { CreateProjectParams } from "@/api/studio"
import { ArrowLeft, Plus, Sparkles, Code2, Blocks } from "lucide-vue-next"

const route = useRoute()
const router = useRouter()

/* ─── 表单状态 ─── */
const name = ref("")
const description = ref("")
const prompt = ref("")
const mode = ref<"manual" | "ai">("manual")
const framework = ref("vue")
const stack = ref("fullstack")
const submitting = ref(false)
const error = ref("")

/* ─── 预定义模板 ─── */
const templates = [
  { id: "saas-landing", name: "SaaS 落地页", icon: "🚀", category: "web" },
  { id: "admin-dashboard", name: "后台管理系统", icon: "📊", category: "web" },
  { id: "blog-platform", name: "博客平台", icon: "📝", category: "web" },
  { id: "ecommerce", name: "电商平台", icon: "🛒", category: "web" },
  { id: "api-service", name: "API 服务", icon: "🔌", category: "backend" },
  { id: "chat-app", name: "聊天应用", icon: "💬", category: "fullstack" },
]
const selectedTemplateId = ref("")

/* ─── 快速提示 ─── */
const quickPrompts = [
  { label: "落地页", text: "一个现代 SaaS 产品落地页，包含 Hero 区、特性展示、价格表、CTA 按钮和联系表单" },
  { label: "后台管理", text: "一个数据仪表盘后台管理系统，包含侧边栏导航、统计卡片、数据表格、折线图和饼图" },
  { label: "博客", text: "一个技术博客站点，包含文章列表、详情页、标签筛选、全文搜索和 RSS 订阅" },
  { label: "电商", text: "一个电商网站，包含商品列表、分类筛选、购物车、结算流程和订单管理" },
]

/* ─── 从模板市场跳转时预填参数 ─── */
onMounted(() => {
  const tid = route.query.template_id as string | undefined
  const tname = route.query.template_name as string | undefined
  if (tid) {
    selectedTemplateId.value = tid
  }
  if (tname) {
    name.value = tname
  }
})

/* ─── 创建项目 ─── */
const handleCreate = async () => {
  error.value = ""

  if (mode === "manual" && !name.value.trim()) {
    error.value = "请输入项目名称"
    return
  }

  if (mode === "ai" && !prompt.value.trim()) {
    error.value = "请输入项目描述"
    return
  }

  submitting.value = true
  try {
    const body: CreateProjectParams = {
      name: name.value.trim() || (mode === "ai" ? prompt.value.trim().slice(0, 40) : "新项目"),
      description: description.value.trim() || (mode === "ai" ? prompt.value.trim() : ""),
      framework: framework.value,
      stack: stack.value,
    }
    if (selectedTemplateId.value) {
      body.template_id = selectedTemplateId.value
    }
    if (mode === "ai") {
      body.prompt = prompt.value.trim()
    }

    const res = await createProject(body)
    const data: any = (res as any).data?.data ?? (res as any).data
    const id = data?.id ?? "new"
    router.push(`/projects/${id}`)
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? e?.message ?? "创建失败，请确保后端已启动"
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="h-full w-full flex flex-col overflow-hidden bg-[var(--color-ide-bg)] text-[var(--color-ide-text)]">
    <!-- Header -->
    <header class="shrink-0 page-header backdrop-blur flex items-center px-6">
      <button
        class="flex items-center gap-1.5 text-sm text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] transition-colors mr-4"
        @click="router.push('/projects')"
      >
        <ArrowLeft class="w-4 h-4" />
        返回列表
      </button>
      <div>
        <h2 class="text-sm font-semibold text-[var(--color-ide-text)]">创建项目</h2>
        <p class="text-[11px] text-[var(--color-ide-text-dim)]">手动配置或通过 AI 生成全栈项目</p>
      </div>
    </header>

    <main class="flex-1 overflow-y-auto p-6">
      <div class="max-w-2xl mx-auto space-y-6">
        <!-- 模式切换 -->
        <div class="flex rounded-lg bg-surface-800 border border-[var(--color-ide-border)] p-1">
          <button
            :class="[
              'flex-1 flex items-center justify-center gap-1.5 rounded-md px-4 py-2.5 text-sm font-medium transition-all',
              mode === 'manual'
                ? 'bg-brand-500/20 text-brand-400'
                : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]',
            ]"
            @click="mode = 'manual'"
          >
            <Blocks class="w-4 h-4" />
            手动创建
          </button>
          <button
            :class="[
              'flex-1 flex items-center justify-center gap-1.5 rounded-md px-4 py-2.5 text-sm font-medium transition-all',
              mode === 'ai'
                ? 'bg-brand-500/20 text-brand-400'
                : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]',
            ]"
            @click="mode = 'ai'"
          >
            <Sparkles class="w-4 h-4" />
            AI 生成
          </button>
        </div>

        <!-- 手动模式 -->
        <form v-if="mode === 'manual'" class="space-y-5" @submit.prevent="handleCreate">
          <!-- 项目名称 -->
          <div>
            <label class="block text-sm font-medium text-[var(--color-ide-text)] mb-1.5">项目名称 <span class="text-red-400">*</span></label>
            <input
              v-model="name"
              type="text"
              class="w-full rounded-lg border border-[var(--color-ide-border)] bg-surface-800 px-4 py-2.5 text-sm text-[var(--color-ide-text)] placeholder-[var(--color-ide-text-dim)] focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/20 transition-all"
              placeholder="例如：my-saas-platform"
            />
          </div>

          <!-- 项目描述 -->
          <div>
            <label class="block text-sm font-medium text-[var(--color-ide-text)] mb-1.5">项目描述</label>
            <textarea
              v-model="description"
              rows="3"
              class="w-full rounded-lg border border-[var(--color-ide-border)] bg-surface-800 px-4 py-2.5 text-sm text-[var(--color-ide-text)] placeholder-[var(--color-ide-text-dim)] focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/20 transition-all resize-none"
              placeholder="简要描述你的项目用途和功能…"
            />
          </div>

          <!-- 技术栈 -->
          <div class="grid grid-cols-2 gap-4">
            <div>
              <label class="block text-sm font-medium text-[var(--color-ide-text)] mb-1.5">前端框架</label>
              <select
                v-model="framework"
                class="w-full rounded-lg border border-[var(--color-ide-border)] bg-surface-800 px-4 py-2.5 text-sm text-[var(--color-ide-text)] focus:border-brand-500/50 focus:outline-none transition-all"
              >
                <option value="vue">Vue 3</option>
                <option value="react">React</option>
                <option value="html">纯 HTML/CSS</option>
              </select>
            </div>
            <div>
              <label class="block text-sm font-medium text-[var(--color-ide-text)] mb-1.5">项目类型</label>
              <select
                v-model="stack"
                class="w-full rounded-lg border border-[var(--color-ide-border)] bg-surface-800 px-4 py-2.5 text-sm text-[var(--color-ide-text)] focus:border-brand-500/50 focus:outline-none transition-all"
              >
                <option value="frontend">纯前端</option>
                <option value="backend">纯后端</option>
                <option value="fullstack">全栈</option>
              </select>
            </div>
          </div>

          <!-- 模板选择 -->
          <div>
            <label class="block text-sm font-medium text-[var(--color-ide-text)] mb-2">
              选择模板 <span class="font-normal text-[var(--color-ide-text-dim)]">（可选）</span>
            </label>
            <div class="grid grid-cols-3 gap-2">
              <button
                v-for="tpl in templates"
                :key="tpl.id"
                type="button"
                :class="[
                  'flex flex-col items-center gap-1 rounded-lg border p-3 transition-all text-center',
                  selectedTemplateId === tpl.id
                    ? 'border-brand-500/50 bg-brand-500/10 text-brand-400'
                    : 'border-[var(--color-ide-border)] bg-surface-800 text-[var(--color-ide-text-dim)] hover:border-[var(--color-ide-border)] hover:text-[var(--color-ide-text)]',
                ]"
                @click="selectedTemplateId = selectedTemplateId === tpl.id ? '' : tpl.id"
              >
                <span class="text-lg">{{ tpl.icon }}</span>
                <span class="text-[11px] font-medium leading-tight">{{ tpl.name }}</span>
              </button>
            </div>
          </div>

          <!-- 错误提示 -->
          <div v-if="error" class="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-400">
            {{ error }}
          </div>

          <!-- 提交 -->
          <button
            type="submit"
            :disabled="submitting"
            class="w-full flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-brand-500 to-purple-500 hover:shadow-lg hover:shadow-brand-500/20 disabled:opacity-50 disabled:cursor-not-allowed px-5 py-2.5 text-sm font-medium text-white transition-all"
          >
            <Plus class="w-4 h-4" />
            {{ submitting ? "创建中…" : "创建项目" }}
          </button>
        </form>

        <!-- AI 生成模式 -->
        <form v-else class="space-y-5" @submit.prevent="handleCreate">
          <div>
            <label class="block text-sm font-medium text-[var(--color-ide-text)] mb-1.5">
              <Sparkles class="w-3.5 h-3.5 inline mr-1 text-brand-400" />
              用自然语言描述你的项目
            </label>
            <textarea
              v-model="prompt"
              rows="6"
              class="w-full rounded-lg border border-[var(--color-ide-border)] bg-surface-800 px-4 py-2.5 text-sm text-[var(--color-ide-text)] placeholder-[var(--color-ide-text-dim)] focus:border-brand-500/50 focus:outline-none focus:ring-1 focus:ring-brand-500/20 transition-all resize-none"
              placeholder="描述得越具体，生成效果越好。例如：一个带用户注册登录的任务管理工具，支持创建/编辑/删除任务、拖拽排序、设置优先级和截止日期，前端用 Vue 3 + TypeScript，后端用 FastAPI + SQLite…"
            />
          </div>

          <!-- 快速提示 -->
          <div>
            <label class="block text-sm font-medium text-[var(--color-ide-text-dim)] mb-2">快速填充</label>
            <div class="flex flex-wrap gap-2">
              <button
                v-for="qp in quickPrompts"
                :key="qp.label"
                type="button"
                class="rounded-lg border border-[var(--color-ide-border)] bg-surface-800 px-3 py-1.5 text-xs text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:border-brand-500/30 transition-colors"
                @click="prompt = qp.text"
              >
                {{ qp.label }}
              </button>
            </div>
          </div>

          <!-- 错误提示 -->
          <div v-if="error" class="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-400">
            {{ error }}
          </div>

          <!-- 提交 -->
          <button
            type="submit"
            :disabled="submitting || !prompt.trim()"
            class="w-full flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-brand-500 to-purple-500 hover:shadow-lg hover:shadow-brand-500/20 disabled:opacity-50 disabled:cursor-not-allowed px-5 py-2.5 text-sm font-medium text-white transition-all"
          >
            <Sparkles class="w-4 h-4" />
            {{ submitting ? "AI 生成中…" : "开始 AI 生成" }}
          </button>
        </form>
      </div>
    </main>
  </div>
</template>
