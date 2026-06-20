<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { LayoutGrid, Layers, Play, BookOpen, Wrench, Server, Store, Package, BarChart3, Swords, MemoryStick, Sliders, Brain, Image, Mic, Webhook, FileText, Command, ListChecks, Globe, GitGraph, Settings, HardDrive, MessageCircle } from '@/components/icons'

const route = useRoute()
const appStore = useAppStore()

const navItems = [
  { path: '/chat', name: '对话测试台', icon: MessageCircle },
  { path: '/projects', name: '项目管理', icon: LayoutGrid },
  { path: '/templates', name: '模板市场', icon: Layers },
  { path: '/knowledge', name: '知识库', icon: BookOpen },
  { path: '/tools', name: '工具管理', icon: Wrench },
  { path: '/mcp', name: 'MCP 服务器', icon: Server },
  { path: '/plugins', name: '插件市场', icon: Store },
  { path: '/plugins/manage', name: '我的插件', icon: Package },
  { path: '/presets', name: '模型预设', icon: Sliders },
  { path: '/arena', name: '模型竞技场', icon: Swords },
  { path: '/analytics', name: '分析看板', icon: BarChart3 },
  { path: '/memory', name: '长期记忆', icon: MemoryStick },
  { path: '/structured-output', name: '结构化输出', icon: Brain },
  { path: '/image-gen', name: '图像生成', icon: Image },
  { path: '/voice', name: '语音服务', icon: Mic },
  { path: '/webhooks', name: 'Webhook', icon: Webhook },
  { path: '/skills', name: '技能指令', icon: FileText },
  { path: '/prompt-templates', name: 'Prompt 模板', icon: Command },
  { path: '/tasks', name: '任务管理', icon: ListChecks },
  { path: '/openapi', name: 'OpenAPI 发现', icon: Globe },
  { path: '/knowledge-graph', name: '知识图谱', icon: GitGraph },
  { path: '/deployments', name: '部署管理', icon: Play },
  { path: '/screenshot-to-code', name: '截图转代码', icon: LayoutGrid },
  { path: '/system', name: '系统管理', icon: Settings },
  { path: '/storage', name: '存储管理', icon: HardDrive },
]
</script>

<template>
  <aside
    :class="[
      'flex flex-col border-r border-white/10 bg-surface-900 transition-all duration-300',
      appStore.sidebarCollapsed ? 'w-16' : 'w-56',
    ]"
  >
    <!-- Logo -->
    <div class="flex h-14 items-center justify-between border-b border-white/10 px-4">
      <span
        :class="[
          'text-lg font-bold tracking-wide text-brand-400 transition-opacity',
          appStore.sidebarCollapsed ? 'opacity-0 w-0 overflow-hidden' : 'opacity-100',
        ]"
      >
        AI Studio
      </span>
      <button
        class="rounded-lg p-1 hover:bg-white/10 transition-colors"
        @click="appStore.toggleSidebar"
      >
        <ChevronLeftIcon v-if="!appStore.sidebarCollapsed" class="w-4 h-4" />
        <ChevronRightIcon v-else class="w-4 h-4" />
      </button>
    </div>

    <!-- Nav -->
    <nav class="flex-1 space-y-1 p-3 overflow-y-auto">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        :class="[
          'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-all duration-200',
          route.path === item.path || (item.path !== '/' && route.path.startsWith(item.path + '/'))
            ? 'bg-brand-500/15 text-brand-400 font-medium'
            : 'text-gray-400 hover:bg-white/5 hover:text-gray-200',
        ]"
      >
        <component :is="item.icon" class="w-5 h-5 shrink-0" />
        <span
          :class="[
            'whitespace-nowrap transition-opacity',
            appStore.sidebarCollapsed ? 'opacity-0 w-0 overflow-hidden' : 'opacity-100',
          ]"
        >
          {{ item.name }}
        </span>
      </router-link>
    </nav>

    <!-- Footer -->
    <div class="border-t border-white/10 p-4">
      <span
        :class="[
          'text-xs text-gray-500 transition-opacity',
          appStore.sidebarCollapsed ? 'opacity-0' : 'opacity-100',
        ]"
      >
        v0.2.0
      </span>
    </div>
  </aside>
</template>

<script lang="ts">
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
const ChevronLeftIcon = ChevronLeft
const ChevronRightIcon = ChevronRight
</script>
