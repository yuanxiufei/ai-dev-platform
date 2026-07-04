<script setup lang="ts">
/**
 * ProjectNew.vue — AI 全栈项目创建页面
 *
 * 设计原则：标题居中、宽松间距、大触控目标、呼吸感
 */
import { onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { createProject } from "@/api/studio"
import type { CreateProjectParams } from "@/api/studio"
import {
  ArrowLeft,
  Plus,
  Sparkles,
  Blocks,
  Globe,
  Server,
  LayoutDashboard,
  Layers,
  Wand2,
  FileText,
  MessageCircle,
  ShoppingCart,
} from "lucide-vue-next"

const route = useRoute()
const router = useRouter()

/* ─── 表单状态 ─── */
const name = ref("")
const description = ref("")
const prompt = ref("")
const mode = ref<"manual" | "ai">("ai")
const framework = ref("vue")
const stack = ref("fullstack")
const submitting = ref(false)
const error = ref("")

/* ─── 预定义模板 ─── */
const templates = [
  { id: "saas-landing", name: "SaaS 落地页", icon: Globe },
  { id: "admin-dashboard", name: "后台管理系统", icon: LayoutDashboard },
  { id: "blog-platform", name: "博客平台", icon: FileText },
  { id: "ecommerce", name: "电商平台", icon: ShoppingCart },
  { id: "api-service", name: "API 服务", icon: Server },
  { id: "chat-app", name: "聊天应用", icon: MessageCircle },
]
const selectedTemplateId = ref("")

/* ─── 快速提示 ─── */
const quickPrompts = [
  { label: "落地页", text: "一个现代 SaaS 产品落地页，包含 Hero 区、特性展示、价格表和 CTA 按钮" },
  { label: "后台管理", text: "一个数据仪表盘系统，包含侧边栏导航、统计卡片和数据表格" },
  { label: "博客", text: "一个技术博客站点，包含文章列表、详情页、标签筛选和全文搜索" },
  { label: "电商", text: "一个电商网站，包含商品列表、分类筛选、购物车和结算流程" },
]

onMounted(() => {
  const tid = route.query.template_id as string | undefined
  const tname = route.query.template_name as string | undefined
  if (tid) selectedTemplateId.value = tid
  if (tname) name.value = tname
})

const handleCreate = async () => {
  error.value = ""
  if (mode.value === "manual" && !name.value.trim()) {
    error.value = "请输入项目名称"
    return
  }
  if (mode.value === "ai" && !prompt.value.trim()) {
    error.value = "请输入项目描述"
    return
  }

  submitting.value = true
  try {
    const body: CreateProjectParams = {
      name: name.value.trim() || (mode.value === "ai" ? prompt.value.trim().slice(0, 40) : "新项目"),
      description: description.value.trim() || (mode.value === "ai" ? prompt.value.trim() : ""),
      framework: framework.value,
      stack: stack.value,
    }
    if (selectedTemplateId.value) body.template_id = selectedTemplateId.value
    if (mode.value === "ai") body.prompt = prompt.value.trim()

    const res = await createProject(body)
    const data: any = (res as any).data?.data ?? (res as any).data
    router.push(`/projects/${data?.id ?? "new"}`)
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? e?.message ?? "创建失败，请确保后端已启动"
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="h-full w-full flex flex-col overflow-hidden bg-[var(--color-ide-bg)] text-[var(--color-ide-text)]">
    <!-- ═══ Header：标题+副标题水平垂直居中 ═══ -->
    <header class="shrink-0 flex items-center px-6"
      style="height: 60px; border-bottom: 1px solid var(--color-ide-border); background: var(--color-ide-bg);">
      <!-- 左侧返回按钮固定 -->
      <button
        class="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface)] transition-all"
        @click="router.push('/projects')"
      >
        <ArrowLeft class="w-4 h-4" />
        返回
      </button>
      <!-- 中间标题区：绝对居中 -->
      <div class="absolute left-1/2 top-0 -translate-x-1/2 flex flex-col items-center justify-center h-[60px]">
        <span class="text-[16px] font-semibold tracking-tight" style="color: var(--color-ide-text);">
          创建项目
        </span>
        <span class="text-[11.5px] mt-0.5 tracking-wide" style="color: var(--color-ide-text-dim); opacity: 0.65;">
          手动配置或通过 AI 智能生成全栈应用
        </span>
      </div>
      <!-- 右侧占位保持对称 -->
      <div class="ml-auto w-[52px]" />
    </header>

    <!-- ═══ 居中内容区：充分利用高度留白 ═══ -->
    <main class="flex-1 overflow-y-auto">
      <div class="w-ful m-10 px-8 py-12 flex flex-col" style="min-height: calc(100% - 60px);">

        <!-- 错误提示 -->
        <div v-if="error"
          class="mb-6 flex items-center gap-2.5 rounded-xl px-4 py-3 text-[13px]"
          style="background: var(--proj-error-bg); border: 1px solid var(--proj-error-border); color: var(--color-ide-error);">
          <svg class="w-4 h-4 shrink-0" viewBox="0 0 16 16" fill="currentColor"><path d="M8 1a7 7 0 100 14A7 7 0 008 1zm0 3a.75.75 0 01.75.75v4.5a.75.75 0 01-1.5 0v-4.5A.75.75 0 08 4zm0 8a1 1 0 100-2 1 1 0 000 2z"/></svg>
          {{ error }}
        </div>

        <!-- ═══ 模式切换：加大尺寸 ═══ -->
        <div class="grid grid-cols-2 rounded-2xl p-1.5 mb-8"
          style="background: var(--color-ide-surface); border: 1px solid var(--color-ide-border);">
          <button
            :class="['flex items-center justify-center gap-2 rounded-xl py-3 text-[14px] font-medium transition-all',
              mode === 'manual' ? 'text-white shadow-md' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]']"
            :style="mode === 'manual'
              ? { background: 'var(--proj-create-btn-bg)', boxShadow: '0 2px 12px rgba(0,122,204,.35)' }
              : {}"
            @click="mode = 'manual'"
          >
            <Blocks class="w-4 h-4" />
            手动创建
          </button>
          <button
            :class="['flex items-center justify-center gap-2 rounded-xl py-3 text-[14px] font-medium transition-all',
              mode === 'ai' ? 'text-white shadow-md' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]']"
            :style="mode === 'ai'
              ? { background: 'linear-gradient(135deg,#7C3AED,#5B21B6)', boxShadow: '0 2px 12px rgba(124,58,237,.35)' }
              : {}"
            @click="mode = 'ai'"
          >
            <Sparkles class="w-4 h-4" />
            AI 生成
          </button>
        </div>

        <!-- ═══ AI 生成模式 ═══ -->
        <form v-if="mode === 'ai'" class="space-y-6" @submit.prevent="handleCreate">
          <!-- 描述输入：加大行高和内边距 -->
          <div>
            <label class="block text-[13px] font-medium mb-3" style="color: var(--color-ide-text-dim);">
              用自然语言描述你想做的项目
            </label>
            <textarea
              v-model="prompt"
              rows="5"
              class="w-full rounded-2xl px-5 py-4 text-[14px] leading-relaxed placeholder-[var(--color-ide-text-dim)]/45 resize-none transition-all"
              style="background: var(--color-ide-surface); border: 1.5px solid var(--color-ide-border); color: var(--color-ide-text);"
              placeholder="例如：一个带用户登录的任务管理工具，支持拖拽排序、设置优先级，前端 Vue 3 + 后端 FastAPI…"
              @focus="(e:FocusEvent)=>{(e.target as HTMLElement).style.borderColor='rgba(124,58,237,.55)'}"
              @blur="(e:FocusEvent)=>{(e.target as HTMLElement).style.borderColor='var(--color-ide-border)'}"
            />
            <div class="flex justify-between mt-2.5 text-[11.5px]" style="color: var(--color-ide-text-dim); opacity: 0.55;">
              <span>描述越详细，生成效果越好</span>
              <span>{{ prompt.length }} 字</span>
            </div>
          </div>

          <!-- 快速填充：药丸标签加大 -->
          <div>
            <p class="text-[11.5px] mb-2.5" style="color: var(--color-ide-text-dim); opacity: 0.6;">快速填充</p>
            <div class="flex flex-wrap gap-2.5">
              <button
                v-for="qp in quickPrompts" :key="qp.label"
                type="button"
                class="rounded-full px-4 py-2 text-[12.5px] font-medium transition-all"
                style="border: 1.5px solid var(--color-ide-border); background: var(--color-ide-surface); color: var(--color-ide-text-dim);"
                @click="prompt = qp.text"
                @mouseenter="(e:MouseEvent)=>{const el=e.currentTarget as HTMLElement;el.borderColor='rgba(124,58,237,.5)';el.color='var(--color-ide-text)';el.background='rgba(124,58,237,.06)'}"
                @mouseleave="(e:MouseEvent)=>{const el=e.currentTarget as HTMLElement;el.borderColor='var(--color-ide-border)';el.color='var(--color-ide-text-dim)';el.background='var(--color-ide-surface)'}"
              >
                {{ qp.label }}
              </button>
            </div>
          </div>

          <!-- 技术栈（收起） -->
          <details class="group">
            <summary class="cursor-pointer text-[12px] hover:text-[var(--color-ide-text)] select-none list-none flex items-center gap-1.5 transition-colors py-1"
              style="color: var(--color-ide-text-dim);">
              <svg class="w-3.5 h-3.5 transition-transform group-open:rotate-90" viewBox="0 0 16 16" fill="currentColor"><path d="M4 2l8 6-8 6V2z"/></svg>
              技术偏好（可选）
            </summary>
            <div class="mt-3 grid grid-cols-2 gap-3">
              <select v-model="framework"
                class="appearance-none rounded-xl px-4 py-3 text-[13px] cursor-pointer transition-all"
                style="background: var(--color-ide-surface); border: 1.5px solid var(--color-ide-border); color: var(--color-ide-text);">
                <option value="vue">Vue 3</option><option value="react">React</option><option value="html">HTML / CSS</option>
              </select>
              <select v-model="stack"
                class="appearance-none rounded-xl px-4 py-3 text-[13px] cursor-pointer transition-all"
                style="background: var(--color-ide-surface); border: 1.5px solid var(--color-ide-border); color: var(--color-ide-text);">
                <option value="fullstack">全栈</option><option value="frontend">纯前端</option><option value="backend">纯后端</option>
              </select>
            </div>
          </details>

          <!-- 主按钮：加高加宽内边距 -->
          <button
            type="submit"
            :disabled="submitting || !prompt.trim()"
            class="w-full rounded-2xl py-4 text-[15px] font-bold text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed mt-2"
            style="background: linear-gradient(135deg, #7C3AED, #5B21B6); box-shadow: 0 6px 24px -4px rgba(124,58,237,.45);"
          >
            <template v-if="!submitting">
              <Sparkles class="inline w-5 h-5 mr-2 -mt-0.5" />
              开始生成
            </template>
            <span v-else>AI 生成中…</span>
          </button>

          <!-- 底部留白 -->
          <div class="h-4" />
        </form>

        <!-- ═══ 手动创建模式 ═══ -->
        <form v-else class="space-y-7" @submit.prevent="handleCreate">
          <!-- 名称 -->
          <div>
            <label class="block text-[13px] font-medium mb-2.5 text-center" style="color: var(--color-ide-text-dim);">
              项目名称
            </label>
            <input v-model="name" type="text"
              class="w-full rounded-2xl px-5 py-3.5 text-[14px] placeholder-[var(--color-ide-text-dim)]/45 resize-none transition-all text-center"
              style="background: var(--color-ide-surface); border: 1.5px solid var(--color-ide-border); color: var(--color-ide-text);"
              placeholder="例如 my-saas-platform"
              @focus="(e:FocusEvent)=>{(e.target as HTMLElement).style.borderColor='#007ACC99'}"
              @blur="(e:FocusEvent)=>{(e.target as HTMLElement).style.borderColor='var(--color-ide-border)'}"
            />
          </div>

          <!-- 描述 -->
          <div>
            <label class="block text-[13px] font-medium mb-2.5 text-center" style="color: var(--color-ide-text-dim);">
              项目描述 <span style="opacity: 0.45;">可选</span>
            </label>
            <textarea v-model="description" rows="3"
              class="w-full rounded-2xl px-5 py-3.5 text-[14px] leading-relaxed placeholder-[var(--color-ide-text-dim)]/45 resize-none transition-all text-center"
              style="background: var(--color-ide-surface); border: 1.5px solid var(--color-ide-border); color: var(--color-ide-text);"
              placeholder="简要说明项目的用途与定位…" />
          </div>

          <!-- 技术 + 类型 一行：加大 -->
          <div class="grid grid-cols-2 gap-3">
            <select v-model="framework"
              class="appearance-none rounded-2xl px-4 py-3.5 text-[13.5px] cursor-pointer transition-all text-center"
              style="background: var(--color-ide-surface); border: 1.5px solid var(--color-ide-border); color: var(--color-ide-text);">
              <option value="vue">Vue 3</option><option value="react">React</option><option value="html">HTML / CSS</option>
            </select>
            <select v-model="stack"
              class="appearance-none rounded-2xl px-4 py-3.5 text-[13.5px] cursor-pointer transition-all text-center"
              style="background: var(--color-ide-surface); border: 1.5px solid var(--color-ide-border); color: var(--color-ide-text);">
              <option value="fullstack">全栈</option><option value="frontend">纯前端</option><option value="backend">纯后端</option>
            </select>
          </div>

          <!-- 模板选择：加大卡片 -->
          <div>
            <label class="block text-[13px] font-medium mb-4 text-center" style="color: var(--color-ide-text-dim);">
              选择模板 <span style="opacity: 0.45;">可选</span>
            </label>
            <div class="grid grid-cols-3 gap-4">
              <button
                v-for="tpl in templates" :key="tpl.id"
                type="button"
                :class="['group relative flex flex-col items-center rounded-2xl py-5 px-3 transition-all', selectedTemplateId===tpl.id?'ring-2':'']"
                :style="selectedTemplateId===tpl.id
                  ? { background:'rgba(0,122,204,.09)', borderColor:'transparent', boxShadow:'0 4px 16px rgba(0,122,204,.15)' }
                  : { background:'var(--color-ide-surface)', border:'1.5px solid var(--color-ide-border)' }"
                @click="selectedTemplateId=selectedTemplateId===tpl.id?'':tpl.id"
              >
                <div
                  class="rounded-xl flex items-center justify-center transition-all mb-3"
                  style="width: 52px; height: 52px;"
                  :style="{
                    background: selectedTemplateId===tpl.id ? 'rgba(0,122,204,.15)' : 'var(--color-ide-bg)',
                    color: selectedTemplateId===tpl.id ? '#007ACC' : 'var(--color-ide-text-dim)'
                  }"
                >
                  <component :is="tpl.icon" class="w-6 h-6" />
                </div>
                <span class="text-[12.5px] leading-snug text-center font-medium w-full"
                  :style="{color:selectedTemplateId===tpl.id?'var(--color-ide-text)':'var(--color-ide-text-dim)'}">{{ tpl.name }}</span>
              </button>
            </div>
          </div>

          <!-- 间距加大 -->
          <div class="h-2" />

          <!-- 主按钮：加高加宽内边距 -->
          <button
            type="submit" :disabled="submitting"
            class="w-full rounded-2xl py-4 text-[15px] font-bold text-white transition-all disabled:opacity-40 disabled:cursor-not-allowed mt-2"
            style="background: linear-gradient(135deg, #007ACC, #0066B3); box-shadow: 0 6px 24px -4px rgba(0,122,204,.45);">
            <Plus class="inline w-5 h-5 mr-2 -mt-0.5" />
            创建项目
          </button>

          <!-- 底部留白 -->
          <div class="h-4" />
        </form>

      </div>
    </main>
  </div>
</template>
