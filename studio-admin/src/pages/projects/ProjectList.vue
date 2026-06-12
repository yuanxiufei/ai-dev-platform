<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listProjects, deleteProject } from '@/api/studio'
import type { Project } from '@/types/studio'
import { Plus, Trash2, ExternalLink } from 'lucide-vue-next'
import AppLayout from '@/components/layout/AppLayout.vue'

const router = useRouter()
const projects = ref<Project[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await listProjects()
    projects.value = res.data.data ?? []
  } catch {
    // 后端未启动时显示空列表
  } finally {
    loading.value = false
  }
})

const statusLabel: Record<string, string> = {
  draft: '草稿',
  building: '构建中',
  deploying: '部署中',
  running: '运行中',
  failed: '失败',
}

const statusColor: Record<string, string> = {
  draft: 'bg-gray-500/20 text-gray-400',
  building: 'bg-yellow-500/20 text-yellow-400',
  deploying: 'bg-blue-500/20 text-blue-400',
  running: 'bg-green-500/20 text-green-400',
  failed: 'bg-red-500/20 text-red-400',
}

const handleDelete = async (id: string) => {
  if (!confirm('确定删除该项目？')) return
  await deleteProject(id)
  projects.value = projects.value.filter((p) => p.id !== id)
}

const goCreate = () => {
  router.push('/projects/new')
}
</script>

<template>
  <AppLayout>
    <div class="space-y-6">
      <!-- 标题栏 -->
      <div class="flex items-center justify-between">
        <div>
          <h1 class="text-2xl font-bold tracking-tight">项目管理</h1>
          <p class="text-sm text-gray-500 mt-1">管理你的 AI 项目，创建、构建和部署</p>
        </div>
        <button
          class="flex items-center gap-2 rounded-lg bg-brand-500 hover:bg-brand-600 px-4 py-2.5 text-sm font-medium transition-colors"
          @click="goCreate"
        >
          <Plus class="w-4 h-4" />
          创建项目
        </button>
      </div>

      <!-- 加载 -->
      <div v-if="loading" class="py-20 text-center text-gray-500">
        <div class="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin mx-auto mb-4" />
        加载中…
      </div>

      <!-- 空状态 -->
      <div v-else-if="!projects.length" class="py-20 text-center">
        <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-white/5 flex items-center justify-center">
          <LayoutGridIcon class="w-8 h-8 text-gray-600" />
        </div>
        <p class="text-gray-400 text-lg">还没有项目</p>
        <p class="text-gray-600 text-sm mt-1">创建你的第一个 AI 项目开始吧</p>
        <button
          class="mt-6 inline-flex items-center gap-2 rounded-lg bg-brand-500 hover:bg-brand-600 px-5 py-2.5 text-sm font-medium transition-colors"
          @click="goCreate"
        >
          <Plus class="w-4 h-4" />
          创建项目
        </button>
      </div>

      <!-- 项目卡片网格 -->
      <div v-else class="grid gap-4 grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="project in projects"
          :key="project.id"
          class="group rounded-xl border border-white/10 bg-surface-800 hover:border-brand-500/30 transition-all duration-300 cursor-pointer"
          @click="router.push(`/projects/${project.id}`)"
        >
          <!-- 卡片头 -->
          <div class="flex items-center justify-between p-5 pb-3">
            <h3 class="font-semibold text-gray-100 truncate">{{ project.name }}</h3>
            <span
              :class="['rounded-full px-2.5 py-0.5 text-xs font-medium', statusColor[project.status] || statusColor.draft]"
            >
              {{ statusLabel[project.status] || project.status }}
            </span>
          </div>

          <!-- 描述 -->
          <p class="px-5 text-sm text-gray-500 line-clamp-2 min-h-[2.5rem]">
            {{ project.description || '暂无描述' }}
          </p>

          <!-- 底部操作栏 -->
          <div class="flex items-center justify-between p-5 pt-3 border-t border-white/5 mt-2">
            <span class="text-xs text-gray-600">{{ project.created_at }}</span>
            <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                class="rounded-lg p-1.5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
                @click.stop="router.push(`/projects/${project.id}`)"
              >
                <ExternalLink class="w-3.5 h-3.5" />
              </button>
              <button
                class="rounded-lg p-1.5 hover:bg-red-500/15 text-gray-400 hover:text-red-400 transition-colors"
                @click.stop="handleDelete(project.id)"
              >
                <Trash2 class="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script lang="ts">
import { LayoutGrid } from 'lucide-vue-next'
const LayoutGridIcon = LayoutGrid
</script>
