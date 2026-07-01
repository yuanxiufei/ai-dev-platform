<script setup lang="ts">
/**
 * Video Management — 管理端视频列表 (CRUD + 分页)
 */
import { useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import {
  Plus, Pencil, Trash2, Eye, Film, AlertCircle,
} from 'lucide-vue-next'

interface VideoAsset {
  id: string
  title: string
  description: string | null
  file_path: string
  thumbnail_path: string | null
  duration: number | null
  tags: string[] | null
  view_count: number
  is_public: boolean
  is_approved: boolean
  owner_id: string
  created_at: string
}

interface PaginatedResponse {
  data: VideoAsset[]
  total: number
  page: number
  size: number
}

const auth = useAuthStore()
const page = ref(1)
const filterApproved = ref<string | null>(null)
const filterPublic = ref<string | null>(null)

const query = useQuery({
  queryKey: ['admin-videos', page, filterApproved, filterPublic],
  queryFn: async () => {
    const token = localStorage.getItem('access_token')
    const params = new URLSearchParams({ page: String(page.value), size: '20' })
    if (filterApproved.value !== null) params.set('is_approved', filterApproved.value)
    if (filterPublic.value !== null) params.set('is_public', filterPublic.value)
    const res = await fetch(`/api/v1/videos?${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    return (await res.json()) as PaginatedResponse
  },
})

const videos = computed(() => query.data.value?.data || [])
const total = computed(() => query.data.value?.total || 0)

// Delete handler
const deleteId = ref<string | null>(null)
async function handleDelete(id: string) {
  const token = localStorage.getItem('access_token')
  await fetch(`/api/v1/videos/${id}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  deleteId.value = null
  query.refetch()
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('zh-CN')
}

const columns = [
  { key: 'title', label: '标题' },
  { key: 'duration', label: '时长' },
  { key: 'view_count', label: '播放' },
  { key: 'is_approved', label: '审核' },
  { key: 'is_public', label: '公开' },
  { key: 'created_at', label: '日期' },
]
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">视频管理</h1>
        <p class="text-sm text-muted-foreground">共 {{ total }} 个视频</p>
      </div>
      <div class="flex gap-2">
        <Button variant="outline" size="sm" @click="query.refetch()">刷新</Button>
      </div>
    </div>

    <!-- Filters -->
    <div class="flex gap-3">
      <Select v-model="filterApproved" placeholder="审核状态">
        <option :value="null">全部审核</option>
        <option value="true">已审核</option>
        <option value="false">待审核</option>
      </Select>
      <Select v-model="filterPublic" placeholder="公开状态">
        <option :value="null">全部公开</option>
        <option value="true">公开</option>
        <option value="false">非公开</option>
      </Select>
    </div>

    <!-- Loading -->
    <div v-if="query.isLoading.value" class="space-y-3">
      <div v-for="i in 5" :key="i" class="flex items-center gap-4 rounded-md border p-4">
        <div class="h-4 w-8 animate-pulse rounded bg-muted" />
        <div class="flex-1 h-4 animate-pulse rounded bg-muted" />
        <div class="h-4 w-24 animate-pulse rounded bg-muted" />
      </div>
    </div>

    <!-- Error -->
    <div v-else-if="query.isError.value" class="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive flex items-center gap-2">
      <AlertCircle class="h-4 w-4" />
      加载失败: {{ (query.error.value as any)?.message }}
    </div>

    <!-- Empty -->
    <div v-else-if="videos.length === 0" class="flex flex-col items-center justify-center py-12 text-center">
      <Film class="h-12 w-12 text-muted-foreground/50" />
      <h3 class="mt-4 text-lg font-semibold">暂无视频</h3>
      <p class="mt-2 text-sm text-muted-foreground">还没有创建任何视频资产</p>
    </div>

    <!-- Table -->
    <div v-else class="rounded-md border">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b bg-muted/50">
            <th v-for="col in columns" :key="col.key" class="px-4 py-3 text-left font-medium text-muted-foreground">{{ col.label }}</th>
            <th class="px-4 py-3 text-right font-medium text-muted-foreground">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="v in videos" :key="v.id" class="border-b hover:bg-muted/30 transition-colors">
            <td class="px-4 py-3">
              <div class="font-medium truncate max-w-[200px]">{{ v.title }}</div>
              <div v-if="v.tags" class="flex gap-1 mt-1">
                <Badge v-for="t in v.tags" :key="t" variant="secondary" class="text-[10px]">{{ t }}</Badge>
              </div>
            </td>
            <td class="px-4 py-3 text-muted-foreground">{{ v.duration ? v.duration.toFixed(0) + 's' : '-' }}</td>
            <td class="px-4 py-3">
              <Badge variant="secondary" class="gap-1"><Eye class="h-3 w-3" />{{ v.view_count }}</Badge>
            </td>
            <td class="px-4 py-3">
              <Badge :variant="v.is_approved ? 'default' : 'destructive'">{{ v.is_approved ? '已审核' : '待审核' }}</Badge>
            </td>
            <td class="px-4 py-3">
              <Badge :variant="v.is_public ? 'default' : 'secondary'">{{ v.is_public ? '公开' : '非公开' }}</Badge>
            </td>
            <td class="px-4 py-3 text-muted-foreground text-xs">{{ formatDate(v.created_at) }}</td>
            <td class="px-4 py-3 text-right">
              <div class="flex items-center justify-end gap-1">
                <Button variant="ghost" size="icon" class="h-8 w-8" title="编辑"><Pencil class="h-4 w-4" /></Button>
                <Button variant="ghost" size="icon" class="h-8 w-8 text-destructive hover:text-destructive" title="删除" @click="deleteId = v.id"><Trash2 class="h-4 w-4" /></Button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Pagination -->
    <div v-if="total > 20" class="flex items-center justify-center gap-2 pt-2">
      <Button variant="outline" size="sm" :disabled="page <= 1" @click="page--">上一页</Button>
      <span class="text-sm text-muted-foreground px-3">第 {{ page }} 页 / 共 {{ Math.ceil(total / 20) }} 页</span>
      <Button variant="outline" size="sm" :disabled="page * 20 >= total" @click="page++">下一页</Button>
    </div>

    <!-- Delete Confirm Dialog -->
    <Dialog v-if="deleteId" :open="true" @update:open="deleteId = null">
      <DialogContent class="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>确认删除</DialogTitle>
          <DialogDescription>此操作不可撤销。确定要删除这个视频吗？</DialogDescription>
        </DialogHeader>
        <DialogFooter class="gap-2">
          <Button variant="outline" @click="deleteId = null">取消</Button>
          <Button variant="destructive" @click="handleDelete(deleteId!)">删除</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
