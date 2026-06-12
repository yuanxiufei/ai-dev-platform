<script setup lang="ts">
import { Settings } from '@/components/icons'
</script>

<template>
  <header class="flex h-14 shrink-0 items-center justify-between border-b border-white/10 bg-surface-900 px-6">
    <div class="flex items-center gap-3">
      <div class="flex items-center gap-2 rounded-lg bg-white/5 px-3 py-1.5 text-sm text-gray-400">
        <div class="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
        <span>后端已连接</span>
      </div>
    </div>

    <div class="flex items-center gap-3">
      <button class="rounded-lg p-2 hover:bg-white/10 transition-colors text-gray-400 hover:text-white">
        <Settings class="w-5 h-5" />
      </button>
      <div class="flex items-center gap-2 rounded-full bg-brand-500/15 px-3 py-1.5">
        <div class="w-6 h-6 rounded-full bg-brand-500 flex items-center justify-center text-xs font-bold">
          A
        </div>
        <span class="text-sm text-brand-400 font-medium">管理员</span>
      </div>
    </div>
  </header>
</template>
