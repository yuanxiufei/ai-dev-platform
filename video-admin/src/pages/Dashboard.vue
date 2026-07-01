<script setup lang="ts">
/**
 * Dashboard — 视频平台总览首页
 */
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { Film, Eye, BarChart3, TrendingUp } from 'lucide-vue-next'

interface Overview {
  total_videos: number
  public_videos: number
  total_views: number
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
}

const authStore = useAuthStore()
const userName = authStore.userQuery.data.value?.full_name || 'User'

const stats = useQuery({
  queryKey: ['dashboard-stats'],
  queryFn: async () => {
    const token = localStorage.getItem('access_token')
    const res = await fetch('/api/v1/videos/analytics/overview', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) return null
    return (await res.json()) as Overview
  },
  refetchInterval: 60000,
})

const cards = computed(() => {
  const d = stats.data.value
  if (!d) return []
  return [
    { label: '视频总数', value: d.total_videos, icon: Film, color: 'text-blue-500' },
    { label: '总播放量', value: d.total_views, icon: Eye, color: 'text-violet-500' },
    { label: '生成任务', value: d.total_tasks, icon: BarChart3, color: 'text-amber-500' },
    { label: '成功率', value: d.total_tasks > 0 ? `${((d.completed_tasks / d.total_tasks) * 100).toFixed(0)}%` : '-', icon: TrendingUp, color: 'text-green-500' },
  ]
})
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-2xl font-bold tracking-tight">视频平台</h1>
      <p class="text-sm text-muted-foreground">欢迎回来，{{ userName }} 👋</p>
    </div>

    <!-- Stats Cards -->
    <div v-if="stats.isLoading.value" class="grid grid-cols-4 gap-4">
      <div v-for="i in 4" :key="i" class="rounded-xl border bg-card p-5">
        <div class="h-4 w-16 animate-pulse rounded bg-muted mb-3" />
        <div class="h-8 w-12 animate-pulse rounded bg-muted" />
      </div>
    </div>

    <div v-else class="grid grid-cols-4 gap-4">
      <div v-for="card in cards" :key="card.label" class="rounded-xl border bg-card p-5 hover:shadow-sm transition-shadow">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm text-muted-foreground">{{ card.label }}</span>
          <component :is="card.icon" class="h-5 w-5" :class="card.color" />
        </div>
        <p class="text-3xl font-bold tracking-tight">{{ card.value?.toLocaleString() ?? '-' }}</p>
      </div>
    </div>

    <!-- Quick Links -->
    <div class="grid grid-cols-3 gap-4">
      <router-link to="/videos" class="rounded-xl border bg-card p-5 hover:bg-accent/30 transition-colors group">
        <Film class="h-8 w-8 text-blue-500 mb-3" />
        <h3 class="font-semibold group-hover:underline">视频管理</h3>
        <p class="text-sm text-muted-foreground mt-1">管理视频资产、编辑元数据</p>
      </router-link>
      <router-link to="/analytics" class="rounded-xl border bg-card p-5 hover:bg-accent/30 transition-colors group">
        <BarChart3 class="h-8 w-8 text-violet-500 mb-3" />
        <h3 class="font-semibold group-hover:underline">数据分析</h3>
        <p class="text-sm text-muted-foreground mt-1">查看平台数据和趋势</p>
      </router-link>
      <router-link to="/moderation" class="rounded-xl border bg-card p-5 hover:bg-accent/30 transition-colors group">
        <TrendingUp class="h-8 w-8 text-amber-500 mb-3" />
        <h3 class="font-semibold group-hover:underline">内容审核</h3>
        <p class="text-sm text-muted-foreground mt-1">审核用户提交的视频</p>
      </router-link>
    </div>
  </div>
</template>
