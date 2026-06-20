<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { MessageCircle, LayoutGrid, BookOpen, Wrench, Store, Swords, Brain, Server, Sparkles, Image, Wand2, Code2, HardDrive, Mic, BarChart3, Webhook, Globe, GitGraph, Braces, Layers, ScrollText, Bot, Link2 } from 'lucide-vue-next'
import { computed } from 'vue'

const route = useRoute()
const appStore = useAppStore()

const navItems = [
  { path: '/chat', name: 'AI 对话', icon: MessageCircle },
  { path: '/projects', name: '我的项目', icon: LayoutGrid },
  { path: '/knowledge', name: '知识库', icon: BookOpen },
  { path: '/tools', name: '工具集', icon: Wrench },
  { path: '/plugins', name: '插件市场', icon: Store },
  { path: '/arena', name: '模型竞技场', icon: Swords },
  { path: '/memory', name: '长期记忆', icon: Brain },
  { path: '/mcp', name: 'MCP 连接', icon: Server },
  { path: '/skills', name: '技能指令', icon: Sparkles },
  { path: '/rules', name: '规则管理', icon: ScrollText },
  { path: '/integrations', name: '集成服务', icon: Link2 },
  { path: '/agents', name: 'Agent 管理', icon: Bot },
  { path: '/image-gen', name: '图像生成', icon: Image },
  { path: '/prompt-templates', name: 'Prompt 模板', icon: Wand2 },
  { path: '/screenshot-to-code', name: '截图转代码', icon: Code2 },
  { path: '/templates', name: '模板市场', icon: Layers },
  { path: '/voice', name: '语音服务', icon: Mic },
  { path: '/analytics', name: '使用分析', icon: BarChart3 },
  { path: '/structured-output', name: '结构化输出', icon: Braces },
  { path: '/webhooks', name: 'Webhook', icon: Webhook },
  { path: '/openapi', name: 'OpenAPI', icon: Globe },
  { path: '/knowledge-graph', name: '知识图谱', icon: GitGraph },
  { path: '/storage', name: '存储设置', icon: HardDrive },
]

const isActive = (path: string) => {
  if (path === '/chat') return route.path === '/chat' || route.path.startsWith('/projects/')
  return route.path.startsWith(path)
}
</script>

<template>
  <aside
    :class="[
      'flex flex-col border-r border-white/8 bg-surface-900/80 backdrop-blur-xl transition-all duration-300 relative z-10',
      appStore.sidebarCollapsed ? 'w-[4.5rem]' : 'w-60',
    ]"
  >
    <!-- Logo -->
    <div class="flex h-16 items-center gap-3 px-4 border-b border-white/8">
      <div
        class="w-9 h-9 rounded-xl bg-gradient-to-br from-brand-400 to-purple-500 flex items-center justify-center shrink-0 shadow-lg shadow-brand-500/20"
      >
        <span class="text-white font-bold text-sm">AI</span>
      </div>
      <span
        :class="[
          'text-base font-bold tracking-wide bg-gradient-to-r from-brand-400 to-purple-400 bg-clip-text text-transparent whitespace-nowrap transition-all duration-300',
          appStore.sidebarCollapsed ? 'opacity-0 w-0' : 'opacity-100',
        ]"
      >
        AI Studio
      </span>
    </div>

    <!-- Nav -->
    <nav class="flex-1 space-y-1 p-3 pt-4">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        :class="[
          'flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium transition-all duration-200 group relative',
          isActive(item.path)
            ? 'bg-gradient-to-r from-brand-500/20 to-purple-500/10 text-brand-400 shadow-sm'
            : 'text-gray-400 hover:bg-white/5 hover:text-gray-200',
        ]"
      >
        <component
          :is="item.icon"
          :class="['w-5 h-5 shrink-0 transition-colors', isActive(item.path) ? 'text-brand-400' : '']"
        />
        <span
          :class="[
            'whitespace-nowrap transition-all duration-300',
            appStore.sidebarCollapsed ? 'opacity-0 w-0' : 'opacity-100',
          ]"
        >
          {{ item.name }}
        </span>
        <!-- 活动指示器 -->
        <div
          v-if="isActive(item.path)"
          class="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 rounded-r-full bg-gradient-to-b from-brand-400 to-purple-500"
        />
      </router-link>
    </nav>

    <!-- 底部折叠按钮 + 版本 -->
    <div class="border-t border-white/8 p-3 space-y-3">
      <button
        class="w-full flex items-center justify-center gap-2 rounded-lg p-2 text-gray-500 hover:text-gray-300 hover:bg-white/5 transition-colors text-xs"
        @click="appStore.toggleSidebar"
      >
        <PanelLeftOpen v-if="appStore.sidebarCollapsed" class="w-4 h-4" />
        <PanelLeftClose v-else class="w-4 h-4" />
      </button>
      <p
        :class="[
          'text-center text-xs text-gray-600 transition-all duration-300',
          appStore.sidebarCollapsed ? 'opacity-0' : 'opacity-100',
        ]"
      >
        v0.2.0
      </p>
    </div>
  </aside>
</template>

<script lang="ts">
import { PanelLeftOpen, PanelLeftClose } from 'lucide-vue-next'
</script>
