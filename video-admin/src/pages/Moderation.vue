<script setup lang="ts">
/**
 * Video Moderation — 内容审核队列
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/vue-query'
import { computed, ref } from 'vue'
import {
  CheckCircle, XCircle, Eye, Clock, ShieldAlert,
} from 'lucide-vue-next'

interface ModerationItem {
  id: string
  title: string
  description: string | null
  thumbnail_path: string | null
  duration: number | null
  tags: string[] | null
  owner_id: string
  created_at: string
}

interface QueueResponse {
  data: ModerationItem[]
  total: number
  page: number
  size: number
}

const page = ref(1)
const queryClient = useQueryClient()

const queue = useQuery({
  queryKey: ['moderation-queue', page],
  queryFn: async () => {
    const token = localStorage.getItem('access_token')
    const res = await fetch(`/api/v1/videos/moderation/queue?page=${page.value}&size=20`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return (await res.json()) as QueueResponse
  },
  refetchInterval: 15000,
})

const items = computed(() => queue.data.value?.data || [])
const total = computed(() => queue.data.value?.total || 0)

const approveMutation = useMutation({
  mutationFn: async (id: string) => {
    const token = localStorage.getItem('access_token')
    await fetch(`/api/v1/videos/moderation/${id}/approve`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ reason: 'Approved by admin' }),
    })
  },
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['moderation-queue'] })
  },
})

const rejectMutation = useMutation({
  mutationFn: async ({ id, reason }: { id: string; reason: string }) => {
    const token = localStorage.getItem('access_token')
    await fetch(`/api/v1/videos/moderation/${id}/reject`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ reason }),
    })
  },
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ['moderation-queue'] })
  },
})

const rejectReason = ref('')

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('zh-CN')
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">内容审核</h1>
        <p class="text-sm text-muted-foreground">待审核视频: {{ total }}</p>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="queue.isLoading.value" class="space-y-3">
      <div v-for="i in 5" :key="i" class="flex items-center gap-4 rounded-md border p-4">
        <div class="h-12 w-20 animate-pulse rounded bg-muted" />
        <div class="flex-1 h-5 animate-pulse rounded bg-muted" />
        <div class="h-8 w-24 animate-pulse rounded bg-muted" />
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="queue.isError.value" class="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive flex items-center gap-2">
      <ShieldAlert class="h-4 w-4" />
      加载审核队列失败
    </div>

    <!-- Empty -->
    <div v-else-if="items.length === 0" class="flex flex-col items-center justify-center py-16 text-center">
      <CheckCircle class="h-12 w-12 text-green-500/50" />
      <h3 class="mt-4 text-lg font-semibold">审核队列为空</h3>
      <p class="mt-2 text-sm text-muted-foreground">所有视频已审核完毕</p>
    </div>

    <!-- Queue List -->
    <div v-else class="space-y-3">
      <div v-for="item in items" :key="item.id" class="rounded-lg border p-4 hover:bg-muted/20 transition-colors">
        <div class="flex gap-4">
          <!-- Thumbnail -->
          <div class="w-24 h-36 shrink-0 rounded-md bg-muted flex items-center justify-center overflow-hidden">
            <img v-if="item.thumbnail_path" :src="item.thumbnail_path" :alt="item.title" class="w-full h-full object-cover" />
            <Eye v-else class="h-6 w-6 text-muted-foreground/50" />
          </div>
          <!-- Info -->
          <div class="flex-1 min-w-0">
            <h3 class="font-semibold truncate">{{ item.title }}</h3>
            <p v-if="item.description" class="text-sm text-muted-foreground mt-1 line-clamp-2">{{ item.description }}</p>
            <div class="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
              <span class="flex items-center gap-1"><Clock class="h-3 w-3" />{{ item.duration ? item.duration.toFixed(0) + 's' : '-' }}</span>
              <span>{{ formatDate(item.created_at) }}</span>
            </div>
            <div v-if="item.tags" class="flex gap-1 mt-2">
              <Badge v-for="t in item.tags" :key="t" variant="secondary" class="text-[10px]">{{ t }}</Badge>
            </div>
          </div>
          <!-- Actions -->
          <div class="flex flex-col gap-2 shrink-0">
            <Button
              variant="default"
              size="sm"
              class="gap-1"
              :disabled="approveMutation.isPending.value"
              @click="approveMutation.mutate(item.id)"
            >
              <CheckCircle class="h-4 w-4" /> 批准
            </Button>
            <Button
              variant="destructive"
              size="sm"
              class="gap-1"
              :disabled="rejectMutation.isPending.value"
              @click="rejectReason = ''; rejectMutation.mutate({ id: item.id, reason: rejectReason })"
            >
              <XCircle class="h-4 w-4" /> 驳回
            </Button>
          </div>
        </div>
      </div>
    </div>

    <!-- Pagination -->
    <div v-if="total > 20" class="flex items-center justify-center gap-2 pt-2">
      <Button variant="outline" size="sm" :disabled="page <= 1" @click="page--">上一页</Button>
      <span class="text-sm text-muted-foreground px-3">第 {{ page }} 页 / 共 {{ Math.ceil(total / 20) }} 页</span>
      <Button variant="outline" size="sm" :disabled="page * 20 >= total" @click="page++">下一页</Button>
    </div>
  </div>
</template>
