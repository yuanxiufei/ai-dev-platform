<script setup lang="ts">
import { RouterLink, useRoute } from 'vue-router'
import { Film, GalleryHorizontalEnd } from 'lucide-vue-next'
import { computed } from 'vue'

const route = useRoute()

const navItems = [
  { to: '/', label: '生成', icon: Film },
  { to: '/gallery', label: '作品', icon: GalleryHorizontalEnd },
]

function isActive(path: string) {
  return route.path === path
}
</script>

<template>
  <header class="sticky top-0 z-50 backdrop-blur-xl bg-gray-950/60 border-b border-white/5">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <RouterLink to="/" class="flex items-center gap-2.5 group">
        <div
          class="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500 flex items-center justify-center shadow-lg shadow-violet-500/20 group-hover:shadow-violet-500/40 transition-shadow"
        >
          <Film class="w-5 h-5 text-white" />
        </div>
        <span
          class="font-bold text-lg bg-gradient-to-r from-white to-white/60 bg-clip-text text-transparent"
        >
          AI 视频工坊
        </span>
      </RouterLink>

      <nav class="flex items-center gap-1 bg-white/5 rounded-xl p-1">
        <RouterLink
          v-for="{ to, label, icon } in navItems"
          :key="to"
          :to="to"
          class="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
          :class="
            isActive(to)
              ? 'bg-violet-500/20 text-violet-300 shadow-sm'
              : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
          "
        >
          <component :is="icon" class="w-4 h-4" />
          <span class="hidden sm:inline">{{ label }}</span>
        </RouterLink>
      </nav>
    </div>
  </header>
</template>
