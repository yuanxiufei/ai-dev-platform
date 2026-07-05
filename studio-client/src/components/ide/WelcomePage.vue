<script setup lang="ts">
/**
 * VSCode Welcome Page — 起始页（对标 Getting Started / Walkthrough）
 *
 * 仅在真正空闲时显示（无打开文件、无活动面板）
 * 布局: 紧凑居中 + 网格快捷操作 + 底部帮助链接
 */
import { FilePlus, FolderOpen, GitBranch, Sparkles, TerminalSquare, Code2, Keyboard, BookOpen, Settings, ArrowRight, ChevronRight, CheckCircle2, Play, ClipboardList, PenTool } from "lucide-vue-next"
import { computed, ref } from "vue"
import { useRouter } from "vue-router"
import { useIDEStore } from "@/stores/useIDEStore"
import { isTauriEnv } from "@/stores/shared"

const store = useIDEStore()
const router = useRouter()

/** VSCode 对标：打开文件夹 — Tauri dialog (目录选择器) / Browser File System Access API */
async function handleOpenFolder(): Promise<void> {
  try {
    if (isTauriEnv()) {
      const { open } = await import('@tauri-apps/plugin-dialog')
      const selected = await open({ directory: true, multiple: false, title: '选择文件夹' })
      if (selected && typeof selected === 'string') {
        store.initFileTree(selected)
        store.addOutputLine(`[信息] 已打开文件夹: ${selected}`)
      }
    } else {
      // Browser: File System Access API (Chrome 86+ / Edge 86+ / Opera 72+)
      if ('showDirectoryPicker' in window) {
        const dirHandle = await (window as any).showDirectoryPicker()
        // Browser 环境下路径不可读，创建虚拟 demo 结构
        store.addOutputLine(`[信息] 已选择文件夹: ${dirHandle.name} (浏览器环境)`)
        store.initFileTree()
      } else {
        store.addOutputLine('[警告] 当前浏览器不支持文件系统访问 API，请使用 Chrome/Edge 86+')
        store.initFileTree()
      }
    }
  } catch (e: any) {
    // 用户取消选择
    if (e?.name !== 'AbortError') {
      console.warn('[WelcomePage] Open folder failed:', e)
    }
  }
}

// ── 快捷操作 ──
interface QuickAction {
  id: string
  label: string
  description: string
  icon: any
  shortcut?: string
  action: () => void
}

const quickActions = computed<QuickAction[]>(() => [
  {
    id: "new-file",
    label: "新建文件",
    description: "Ctrl+N",
    icon: FilePlus,
    action: () => store.createUntitledTab(),
  },
  {
    id: "open-folder",
    label: "打开文件夹",
    description: "Ctrl+K O",
    icon: FolderOpen,
    action: () => handleOpenFolder(),
  },
  {
    id: "clone-repo",
    label: "克隆仓库",
    description: "",
    icon: GitBranch,
    // 🔥 修复: 同时设置 fileTreeVisible=true，确保 Sidebar 可见 (P1)
    action: () => { store.activeActivityItem = "git"; store.layout.fileTreeVisible = true },
  },
  {
    id: "ai-chat",
    label: "AI 对话",
    description: "Ctrl+Shift+I",
    icon: Sparkles,
    action: () => {
      store.rightPanelView = "chat"
      store.layout.rightPanelVisible = true
    },
  },
  {
    id: "terminal",
    label: "终端",
    description: "Ctrl+`",
    icon: TerminalSquare,
    action: () => {
      store.bottomPanelView = "terminal"
      store.layout.bottomPanelVisible = true
    },
  },
])

// ── 帮助链接 ──
const helpLinks = [
  { label: "快捷键", icon: Keyboard, action: () => router.push('/keybindings') },
  { label: "文档", icon: BookOpen, action: () => store.activeActivityItem = 'explorer' },
  { label: "设置", icon: Settings, action: () => router.push('/settings') },
]

// ── Session 42: Walkthrough 向导步骤 ──
interface WalkthroughStep {
  id: string
  title: string
  description: string
  icon: any
  action: () => void
  actionLabel: string
}
const walkthroughSteps = ref<WalkthroughStep[]>([
  {
    id: "open-folder",
    title: "打开项目文件夹",
    description: "导入你的代码库，开始 AI 辅助开发之旅",
    icon: FolderOpen,
    action: () => handleOpenFolder(),
    actionLabel: "打开文件夹",
  },
  {
    id: "explore-ai",
    title: "探索 AI 功能",
    description: "使用 AI 对话、截图转代码、模板市场等强大工具",
    icon: Sparkles,
    action: () => {
      store.rightPanelView = "chat"
      store.layout.rightPanelVisible = true
    },
    actionLabel: "打开 AI 对话",
  },
  {
    id: "customize",
    title: "自定义工作区",
    description: "配置主题、快捷键、编辑器设置，打造你的专属 IDE",
    icon: Settings,
    action: () => router.push('/settings'),
    actionLabel: "打开设置",
  },
])
const completedSteps = ref<Set<string>>(new Set())
function completeStep(id: string) {
  completedSteps.value.add(id)
  const s = walkthroughSteps.value.find(w => w.id === id)
  if (s) s.action()
}
</script>

<template>
  <div class="h-full flex flex-col items-center justify-center overflow-auto px-6 py-10"
    style="background: var(--color-editor-bg);">
    <!-- ═══ 紧凑 Header ═══ -->
    <div class="flex flex-col items-center mb-8">
      <div class="mb-3 w-12 h-12 rounded-xl flex items-center justify-center text-white shadow-md"
        style="background: linear-gradient(135deg, var(--color-ide-accent), #8B5CF6);">
        <Code2 :size="24" />
      </div>
      <h1 class="text-[17px] font-semibold tracking-tight mb-0.5"
        style="color: var(--color-ide-text);">
        CodeBuddy Studio
      </h1>
      <p class="text-[12px]" style="color: var(--color-ide-text-dim); opacity: 0.65;">
        AI 驱动的全栈开发平台
      </p>
    </div>

    <!-- ═══ 快捷操作网格 ═══ -->
    <div class="grid grid-cols-3 gap-2.5 w-full max-w-[380px] mb-8">
      <button
        v-for="action in quickActions"
        :key="action.id"
        class="group flex flex-col items-center gap-1.5 rounded-xl py-4 px-2 transition-all duration-150 border border-transparent"
        style="background: var(--color-ide-surface);"
        @click="action.action()"
        @mouseenter="(e: MouseEvent) => {
          const el = e.currentTarget as HTMLElement
          el.style.background = 'var(--color-ide-surface-hover)'
          el.style.borderColor = 'var(--color-ide-border)'
          el.style.transform = 'translateY(-1px)'
          el.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)'
        }"
        @mouseleave="(e: MouseEvent) => {
          const el = e.currentTarget as HTMLElement
          el.style.background = 'var(--color-ide-surface)'
          el.style.borderColor = 'transparent'
          el.style.transform = 'none'
          el.style.boxShadow = 'none'
        }"
      >
        <!-- Icon 圆盒 -->
        <div class="w-9 h-9 rounded-lg flex items-center justify-center transition-colors"
          style="background: var(--color-ide-surface-active);">
          <component :is="action.icon" :size="18" style="color: var(--color-ide-accent);" />
        </div>
        <span class="text-[12px] font-medium leading-none text-center" style="color: var(--color-ide-text);">
          {{ action.label }}
        </span>
        <span v-if="action.description" class="text-[10px] font-mono leading-none" style="color: var(--color-ide-text-dim); opacity: 0.5;">
          {{ action.description }}
        </span>
        <ArrowRight :size="11" class="opacity-0 group-hover:opacity-50 transition-opacity mt-0.5"
          style="color: var(--color-ide-text-dim);" />
      </button>
    </div>

    <!-- ═══ 底部帮助链接 ═══ -->
    <div class="flex items-center gap-3 pt-4 border-t"
      style="border-color: var(--color-ide-border); opacity: 0.45;">
      <button
        v-for="link in helpLinks"
        :key="link.label"
        class="flex items-center gap-1 text-[11px] px-2 py-1 rounded transition-colors hover:opacity-80 cursor-pointer"
        style="color: var(--color-ide-text-dim);"
        @click="link.action()"
      >
        <component :is="link.icon" :size="12" />
        {{ link.label }}
      </button>
    </div>

    <!-- ═══ Session 42: Getting Started Walkthrough 向导 ═══ -->
    <div class="mt-8 w-full max-w-[480px]">
      <div class="flex items-center gap-2 mb-4">
        <ClipboardList :size="16" style="color: var(--color-ide-accent);" />
        <span class="text-[13px] font-semibold" style="color: var(--color-ide-text);">入门引导</span>
        <span class="text-[11px]" style="color: var(--color-ide-text-dim);">
          {{ completedSteps.size }}/{{ walkthroughSteps.length }}
        </span>
      </div>
      <div class="space-y-2">
        <div
          v-for="step in walkthroughSteps"
          :key="step.id"
          class="flex items-center gap-3 rounded-lg p-3 transition-colors cursor-pointer border"
          :style="{
            background: completedSteps.has(step.id) ? 'var(--color-ide-accent)/5' : 'var(--color-ide-surface)',
            borderColor: completedSteps.has(step.id) ? 'var(--color-ide-accent)/20' : 'var(--color-ide-border)',
          }"
          @click="completeStep(step.id)"
        >
          <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
            :style="{ background: completedSteps.has(step.id) ? 'var(--color-ide-accent)/15' : 'var(--color-ide-surface-active)' }">
            <component :is="step.icon" :size="14" :style="{ color: completedSteps.has(step.id) ? 'var(--color-ide-accent)' : 'var(--color-ide-text-dim)' }" />
          </div>
          <div class="flex-1 min-w-0">
            <div class="text-[12px] font-medium" :style="{ color: completedSteps.has(step.id) ? 'var(--color-ide-text-dim)' : 'var(--color-ide-text)' }">
              {{ step.title }}
            </div>
            <div class="text-[10px] mt-0.5" style="color: var(--color-ide-text-dim);">{{ step.description }}</div>
          </div>
          <span v-if="completedSteps.has(step.id)" style="color: var(--color-ide-success);">
            <CheckCircle2 :size="16" />
          </span>
          <span v-else class="flex items-center gap-1 text-[11px] px-2 py-1 rounded font-medium shrink-0"
            style="background: var(--color-ide-accent); color: #fff;">
            <Play :size="10" /> {{ step.actionLabel }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>
