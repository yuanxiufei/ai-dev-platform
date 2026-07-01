<script setup lang="ts">
/**
 * Video Analytics — 数据概览仪表板
 */
import { useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'
import {
  Film, Eye, TrendingUp, CheckCircle, XCircle, BarChart3,
} from 'lucide-vue-next'

interface AnalyticsOverview {
  total_videos: number
  public_videos: number
  total_views: number
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
  today_videos: number
  today_views: number
  avg_duration: number | null
}

const overview = useQuery({
  queryKey: ['video-analytics-overview'],
  queryFn: async () => {
    const token = localStorage.getItem('access_token')
    const res = await fetch('/api/v1/videos/analytics/overview', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return (await res.json()) as AnalyticsOverview
  },
  refetchInterval: 30000,
})

const data = computed(() => overview.data.value)

const cards = computed(() => {
  if (!data.value) return []
  return [
    { label: '视频总数', value: data.value.total_videos, icon: Film, color: 'text-blue-500' },
    { label: '总播放量', value: data.value.total_views, icon: Eye, color: 'text-violet-500' },
    { label: '公开视频', value: data.value.public_videos, icon: TrendingUp, color: 'text-green-500' },
    { label: '生成任务', value: data.value.total_tasks, icon: BarChart3, color: 'text-amber-500' },
    { label: '成功任务', value: data.value.completed_tasks, icon: CheckCircle, color: 'text-emerald-500' },
    { label: '失败任务', value: data.value.failed_tasks, icon: XCircle, color: 'text-red-500' },
    { label: '今日新增', value: data.value.today_videos, icon: Film, color: 'text-cyan-500' },
    { label: '今日播放', value: data.value.today_views, icon: Eye, color: 'text-pink-500' },
  ]
})
</script>

<template>
  <div class="space-y-6">
    <div>
      <h1 class="text-2xl font-bold tracking-tight">数据分析</h1>
      <p class="text-sm text-muted-foreground">视频平台数据概览（每30秒自动刷新）</p>
    </div>

    <!-- Loading -->
    <div v-if="overview.isLoading.value" class="grid grid-cols-4 gap-4">
      <div v-for="i in 8" :key="i" class="rounded-xl border bg-card p-5">
        <div class="h-4 w-20 animate-pulse rounded bg-muted mb-3" />
        <div class="h-8 w-16 animate-pulse rounded bg-muted" />
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="overview.isError.value" class="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
      加载分析数据失败
    </div>

    <!-- Cards Grid -->
    <div v-else class="grid grid-cols-4 gap-4">
      <div v-for="card in cards" :key="card.label" class="rounded-xl border bg-card p-5 hover:shadow-sm transition-shadow">
        <div class="flex items-center justify-between mb-2">
          <span class="text-sm text-muted-foreground">{{ card.label }}</span>
          <component :is="card.icon" class="h-5 w-5" :class="card.color" />
        </div>
        <p class="text-3xl font-bold tracking-tight">{{ card.value?.toLocaleString() ?? '-' }}</p>
      </div>
    </div>

    <!-- Quick Stats Summary -->
    <div v-if="data" class="grid grid-cols-3 gap-4">
      <Card>
        <CardHeader class="pb-2">
          <CardTitle class="text-sm font-medium text-muted-foreground">任务成功率</CardTitle>
        </CardHeader>
        <CardContent>
          <p class="text-2xl font-bold">
            {{ data.total_tasks > 0 ? ((data.completed_tasks / data.total_tasks) * 100).toFixed(1) : 0 }}%
          </p>
          <p class="text-xs text-muted-foreground mt-1">{{ data.completed_tasks }} / {{ data.total_tasks }} 成功</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader class="pb-2">
          <CardTitle class="text-sm font-medium text-muted-foreground">公开率</CardTitle>
        </CardHeader>
        <CardContent>
          <p class="text-2xl font-bold">
            {{ data.total_videos > 0 ? ((data.public_videos / data.total_videos) * 100).toFixed(1) : 0 }}%
          </p>
          <p class="text-xs text-muted-foreground mt-1">{{ data.public_videos }} / {{ data.total_videos }} 公开</p>
        </CardContent>
      </Card>
      <Card>
        <CardHeader class="pb-2">
          <CardTitle class="text-sm font-medium text-muted-foreground">平均时长</CardTitle>
        </CardHeader>
        <CardContent>
          <p class="text-2xl font-bold">{{ data.avg_duration ? data.avg_duration.toFixed(0) + 's' : '-' }}</p>
          <p class="text-xs text-muted-foreground mt-1">所有视频平均</p>
        </CardContent>
      </Card>
    </div>
  </div>
</template>
