<script setup lang="ts">
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { LayoutGrid, Layers, Play } from '@/components/icons'

const route = useRoute()
const appStore = useAppStore()

const navItems = [
  { path: '/projects', name: '项目管理', icon: LayoutGrid },
  { path: '/templates', name: '模板市场', icon: Layers },
  { path: '/deployments', name: '部署管理', icon: Play },
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
    <nav class="flex-1 space-y-1 p-3">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        :class="[
          'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-all duration-200',
          route.path.startsWith(item.path)
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
        v0.1.0
      </span>
    </div>
  </aside>
</template>

<script lang="ts">
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
const ChevronLeftIcon = ChevronLeft
const ChevronRightIcon = ChevronRight
</script>
