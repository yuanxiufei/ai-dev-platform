<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { getProject } from "@/api/studio"
import type { Project } from "@/types/studio"
import { ArrowLeft, LayoutGrid } from "lucide-vue-next"

const route = useRoute()
const router = useRouter()
const project = ref<Project | null>(null)
const loading = ref(true)

const id = route.params.id as string

const statusLabel: Record<string, string> = {
  draft: "草稿",
  building: "构建中",
  deploying: "部署中",
  running: "运行中",
  failed: "失败",
}

const statusColor: Record<string, string> = {
  draft: "bg-gray-500/20 text-gray-400",
  building: "bg-yellow-500/20 text-yellow-400",
  deploying: "bg-blue-500/20 text-blue-400",
  running: "bg-green-500/20 text-green-400",
  failed: "bg-red-500/20 text-red-400",
}

onMounted(async () => {
  try {
    const res = await getProject(id)
    project.value = res.data
  } catch {
    // 项目不存在或后端未启动
  } finally {
    loading.value = false
  }
})

const goBack = () => {
  router.push("/projects")
}
</script>

<template>
  <div class="h-full w-full overflow-hidden bg-[var(--color-ide-bg)] text-[var(--color-ide-text)]">
    <!-- 顶部导航 -->
    <header class="border-b border-white/10 bg-surface-900/50 backdrop-blur">
      <div class="max-w-7xl mx-auto px-6 py-4 flex items-center gap-4">
        <button
          class="p-2 rounded-lg hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
          @click="goBack"
        >
          <ArrowLeft class="w-5 h-5" />
        </button>
        <div class="flex items-center gap-3 flex-1">
          <div class="w-8 h-8 rounded-lg bg-brand-500 flex items-center justify-center">
            <LayoutGrid class="w-4 h-4 text-white" />
          </div>
          <h1 class="text-lg font-semibold">{{ project?.name || '项目详情' }}</h1>
          <span
            v-if="project"
            :class="['rounded-full px-2.5 py-0.5 text-xs font-medium ml-2', statusColor[project.status] || statusColor.draft]"
          >
            {{ statusLabel[project.status] || project.status }}
          </span>
        </div>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8">
      <!-- 加载 -->
      <div v-if="loading" class="py-20 text-center text-gray-500">
        <div class="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin mx-auto mb-4" />
        加载中…
      </div>

      <!-- 项目不存在 -->
      <div v-else-if="!project" class="py-20 text-center">
        <p class="text-gray-400 text-lg">项目不存在</p>
        <button
          class="mt-4 rounded-lg bg-brand-500 hover:bg-brand-600 px-4 py-2 text-sm font-medium transition-colors"
          @click="goBack"
        >
          返回列表
        </button>
      </div>

      <!-- 项目详情 -->
      <div v-else class="space-y-6">
        <div class="rounded-xl border border-white/10 bg-surface-800 p-6">
          <h2 class="text-xl font-semibold mb-2">{{ project.name }}</h2>
          <p class="text-gray-400">{{ project.description || '暂无描述' }}</p>
          <div class="flex items-center gap-4 mt-4 text-sm text-gray-500">
            <span>创建于 {{ project.created_at }}</span>
            <span v-if="project.updated_at">更新于 {{ project.updated_at }}</span>
          </div>
        </div>

        <!-- 工作区占位 -->
        <div class="rounded-xl border border-white/10 bg-surface-800 p-12 text-center">
          <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-brand-500/10 flex items-center justify-center">
            <LayoutGrid class="w-8 h-8 text-brand-400" />
          </div>
          <p class="text-gray-400 text-lg">AI Studio 工作区</p>
          <p class="text-gray-600 text-sm mt-1">功能开发中，敬请期待</p>
        </div>
      </div>
    </main>
  </div>
</template>
