<script setup lang="ts">
/**
 * VSCode Welcome Page — 起始页（对标 Getting Started / Walkthrough）
 *
 * 无文件打开时显示，提供快捷操作入口
 * 布局: 左侧 Logo + 快捷操作 | 右侧 最近项目/帮助
 */
import { FilePlus, FolderOpen, History, BookOpen, Settings, Keyboard, GitBranch, TerminalSquare, Code2, Sparkles, CopyPlus, ArrowRight } from "lucide-vue-next"
import { computed, ref } from "vue"
import { useIDEStore } from "@/stores/useIDEStore"

const store = useIDEStore()
const showAllRecents = ref(false)

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
    description: "创建并编辑一个新的文本文件",
    icon: FilePlus,
    shortcut: "Ctrl+N",
    action: () => store.createUntitledTab(),
  },
  {
    id: "open-folder",
    label: "打开文件夹",
    description: "从本地磁盘打开文件夹作为工作区",
    icon: FolderOpen,
    shortcut: "Ctrl+K Ctrl+O",
    action: () => { /* 触发 Tauri 文件对话框 */ },
  },
  {
    id: "clone-repo",
    label: "克隆仓库",
    description: "从 Git 远程仓库克隆代码",
    icon: GitBranch,
    action: () => { store.activeActivityItem = "git" },
  },
  {
    id: "new-project",
    label: "新建项目",
    description: "通过模板快速创建全栈项目",
    icon: CopyPlus,
    action: () => { /* 跳转 Studio 项目管理 */ },
  },
  {
    id: "ai-chat",
    label: "AI 对话",
    description: "使用 AI 助手编写和优化代码",
    icon: Sparkles,
    shortcut: "Ctrl+Shift+I",
    action: () => {
      store.rightPanelView = "chat"
      store.layout.rightPanelVisible = true
    },
  },
  {
    id: "terminal",
    label: "终端",
    description: "打开集成终端执行命令",
    icon: TerminalSquare,
    shortcut: "Ctrl+`",
    action: () => {
      store.rightPanelView = "terminal"
      store.layout.rightPanelVisible = true
    },
  },
])

// ── 帮助链接 ──
const helpLinks = [
  { label: "键盘快捷方式", icon: Keyboard, action: () => {} },
  { label: "文档与指南", icon: BookOpen, action: () => {} },
  { label: "设置", icon: Settings, action: () => {} },
]
</script>

<template>
  <div class="h-full flex flex-col overflow-auto"
    style="background: var(--color-ide-bg);">
    <!-- ═══ Hero Section ═══ -->
    <div class="flex flex-col items-center pt-20 pb-8 px-4">
      <!-- Logo -->
      <div class="mb-6 w-20 h-20 rounded-2xl flex items-center justify-center text-white shadow-lg"
        style="background: linear-gradient(135deg, var(--color-ide-accent), #8B5CF6);">
        <Code2 :size="36" />
      </div>
      <h1 class="text-[22px] font-light tracking-tight mb-1"
        style="color: var(--color-ide-text); letter-spacing: -0.5px;">
        CodeBuddy Studio
      </h1>
      <p class="text-[13px]"
        style="color: var(--color-ide-text-dim);">
        AI 驱动的全栈开发平台
      </p>
    </div>

    <!-- ═══ Quick Actions ═══ -->
    <div class="flex flex-col px-8 gap-1 max-w-lg mx-auto w-full">
      <p class="text-[11px] font-semibold uppercase tracking-wider mb-2"
        style="color: var(--color-ide-text-dim); opacity: 0.6;">
        开始
      </p>

      <button
        v-for="action in quickActions"
        :key="action.id"
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-left group transition-all duration-100 border border-transparent"
        style="background: var(--color-ide-surface);"
        :style="{ '--hover-bg': 'var(--color-ide-surface-hover)' }"
        @click="action.action()"
        @mouseenter="(e: MouseEvent) => {
          (e.currentTarget as HTMLElement).style.background = 'var(--color-ide-surface-hover)'
          ;(e.currentTarget as HTMLElement).style.borderColor = 'var(--color-ide-border)'
        }"
        @mouseleave="(e: MouseEvent) => {
          (e.currentTarget as HTMLElement).style.background = 'var(--color-ide-surface)'
          ;(e.currentTarget as HTMLElement).style.borderColor = 'transparent'
        }"
      >
        <!-- Icon -->
        <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-colors"
          style="background: var(--color-ide-surface-active);">
          <component :is="action.icon" :size="16" style="color: var(--color-ide-accent);" />
        </div>
        <!-- Text -->
        <div class="flex-1 min-w-0">
          <div class="text-[13px] font-medium" style="color: var(--color-ide-text);">
            {{ action.label }}
          </div>
          <div class="text-[11px]" style="color: var(--color-ide-text-dim); opacity: 0.7;">
            {{ action.description }}
          </div>
        </div>
        <!-- Shortcut -->
        <span v-if="action.shortcut" class="text-[10px] px-1.5 py-0.5 rounded font-mono shrink-0"
          style="background: var(--color-ide-surface-active); color: var(--color-ide-text-dim); opacity: 0.6;">
          {{ action.shortcut }}
        </span>
        <ArrowRight :size="14" class="opacity-0 group-hover:opacity-40 transition-opacity shrink-0"
          style="color: var(--color-ide-text-dim);" />
      </button>
    </div>

    <!-- ═══ Bottom: Help Links ═══ -->
    <div class="flex items-center justify-center gap-4 mt-8 pb-12">
      <button
        v-for="link in helpLinks"
        :key="link.label"
        class="flex items-center gap-1.5 text-[11px] px-2 py-1 rounded-md transition-colors hover:underline"
        style="color: var(--color-ide-text-dim);"
        @click="link.action()"
      >
        <component :is="link.icon" :size="14" />
        {{ link.label }}
      </button>
    </div>
  </div>
</template>
