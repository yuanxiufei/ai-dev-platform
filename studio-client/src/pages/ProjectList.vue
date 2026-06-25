<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { deleteProject, listProjects } from "@/api/studio"
import type { Project } from "@/types/studio"

const router = useRouter()
const projects = ref<Project[]>([])
const loading = ref(true)
const searchText = ref("")

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

const _filteredProjects = computed(() => {
  if (!searchText.value) return projects.value
  const q = searchText.value.toLowerCase()
  return projects.value.filter(
    (p) =>
      p.name.toLowerCase().includes(q) ||
      p.description?.toLowerCase().includes(q),
  )
})

const _statusLabel: Record<string, string> = {
  draft: "草稿",
  building: "构建中",
  deploying: "部署中",
  running: "运行中",
  failed: "失败",
}

const _statusColor: Record<string, string> = {
  draft: "bg-gray-500/15 text-gray-400",
  building: "bg-yellow-500/15 text-yellow-400",
  deploying: "bg-blue-500/15 text-blue-400",
  running: "bg-green-500/15 text-green-400",
  failed: "bg-red-500/15 text-red-400",
}

const _handleDelete = async (id: string) => {
  if (!confirm("确定删除该项目？")) return
  await deleteProject(id)
  projects.value = projects.value.filter((p) => p.id !== id)
}

const _goCreate = () => {
  router.push("/projects/new")
}

const _goDetail = (id: string) => {
  router.push(`/projects/${id}`)
}
</script>

<script lang="ts">
import { computed } from 'vue'
</script>

<template>
  <div class="h-full w-full flex flex-col overflow-hidden bg-[var(--color-ide-bg)] text-[var(--color-ide-text)]">
    <!-- Header -->
    <header class="shrink-0 h-14 border-b border-white/8 bg-surface-900/50 backdrop-blur flex items-center justify-between px-6">
      <div class="flex items-center gap-3">
        <LayoutGrid class="w-5 h-5 text-brand-400" />
        <h2 class="text-sm font-semibold text-gray-200">我的项目</h2>
        <span class="text-xs text-gray-600">{{ projects.length }} 个</span>
      </div>
      <div class="flex items-center gap-3">
        <div class="relative">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-500" />
          <input
            v-model="searchText"
            placeholder="搜索项目..."
            class="w-48 rounded-lg bg-white/5 border border-white/8 pl-8 pr-3 py-1.5 text-xs text-gray-300 placeholder-gray-500 focus:outline-none focus:border-brand-500/30 transition-colors"
          />
        </div>
        <button
          class="flex items-center gap-2 rounded-lg bg-gradient-to-r from-brand-500 to-purple-500 hover:shadow-lg hover:shadow-brand-500/15 px-3.5 py-1.5 text-xs font-medium text-white transition-all"
          @click="goCreate"
        >
          <Plus class="w-3.5 h-3.5" />
          创建项目
        </button>
      </div>
    </header>

    <main class="flex-1 overflow-y-auto p-6">
      <!-- 加载 -->
      <div v-if="loading" class="py-20 text-center text-gray-500">
        <div class="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin mx-auto mb-4" />
        加载中...
      </div>

      <!-- 空状态 -->
      <div v-else-if="!projects.length" class="py-20 text-center">
        <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-gradient-to-br from-brand-500/10 to-purple-500/10 flex items-center justify-center">
          <LayoutGrid class="w-8 h-8 text-brand-400/60" />
        </div>
        <p class="text-gray-400 text-lg font-medium">还没有项目</p>
        <p class="text-gray-600 text-sm mt-1">创建你的第一个 AI 项目开始吧</p>
        <button
          class="mt-6 inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-brand-500 to-purple-500 hover:shadow-lg hover:shadow-brand-500/20 px-5 py-2.5 text-sm font-medium text-white transition-all"
          @click="goCreate"
        >
          <Plus class="w-4 h-4" />
          创建项目
        </button>
      </div>

      <!-- 搜索无结果 -->
      <div v-else-if="!filteredProjects.length" class="py-20 text-center">
        <Search class="w-10 h-10 text-gray-600 mx-auto mb-3" />
        <p class="text-gray-400 text-sm">未找到匹配的项目</p>
      </div>

      <!-- 项目卡片网格 -->
      <div v-else class="grid gap-4 grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="project in filteredProjects"
          :key="project.id"
          class="group rounded-xl border border-white/8 bg-surface-800 hover:border-brand-500/20 transition-all duration-300 cursor-pointer overflow-hidden"
          @click="goDetail(project.id)"
        >
          <!-- 卡片头 -->
          <div class="flex items-center justify-between p-5 pb-3">
            <h3 class="font-semibold text-gray-100 truncate text-sm">{{ project.name }}</h3>
            <span
              :class="['rounded-full px-2.5 py-0.5 text-[11px] font-medium', statusColor[project.status] || statusColor.draft]"
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
                @click.stop="goDetail(project.id)"
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
    </main>
  </div>
</template>
