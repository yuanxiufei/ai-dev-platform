<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getProject, buildProject, deployProject } from '@/api/studio'
import type { Project } from '@/types/studio'
import { ArrowLeft, Play, Rocket } from 'lucide-vue-next'
import AppLayout from '@/components/layout/AppLayout.vue'

const route = useRoute()
const router = useRouter()
const id = route.params.id as string
const project = ref<Project | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await getProject(id)
    project.value = res.data.data ?? null
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
})

const handleBuild = async () => {
  if (!project.value) return
  await buildProject(project.value.id)
  project.value.status = 'building'
}

const handleDeploy = async () => {
  if (!project.value) return
  await deployProject(project.value.id)
  project.value.status = 'deploying'
}
</script>

<template>
  <AppLayout>
    <div v-if="loading" class="py-20 text-center text-gray-500">
      <div class="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin mx-auto" />
    </div>

    <div v-else-if="project" class="space-y-6 max-w-3xl">
      <!-- 返回 -->
      <button
        class="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-300 transition-colors"
        @click="router.back()"
      >
        <ArrowLeft class="w-4 h-4" />
        返回列表
      </button>

      <!-- 标题 -->
      <div>
        <h1 class="text-2xl font-bold tracking-tight">{{ project.name }}</h1>
        <p class="text-sm text-gray-500 mt-2">{{ project.description || '暂无描述' }}</p>
      </div>

      <!-- 操作栏 -->
      <div class="flex items-center gap-3">
        <button
          class="flex items-center gap-2 rounded-lg bg-yellow-500/15 hover:bg-yellow-500/20 text-yellow-400 px-4 py-2.5 text-sm font-medium transition-colors"
          @click="handleBuild"
        >
          <Play class="w-4 h-4" />
          构建
        </button>
        <button
          class="flex items-center gap-2 rounded-lg bg-green-500/15 hover:bg-green-500/20 text-green-400 px-4 py-2.5 text-sm font-medium transition-colors"
          @click="handleDeploy"
        >
          <Rocket class="w-4 h-4" />
          部署
        </button>
      </div>

      <!-- 信息卡片 -->
      <div class="grid grid-cols-2 gap-4">
        <div class="rounded-xl border border-white/10 bg-surface-800 p-5">
          <p class="text-xs text-gray-500 mb-1">项目 ID</p>
          <p class="text-sm font-mono text-gray-300">{{ project.id }}</p>
        </div>
        <div class="rounded-xl border border-white/10 bg-surface-800 p-5">
          <p class="text-xs text-gray-500 mb-1">状态</p>
          <p class="text-sm text-gray-300">{{ project.status }}</p>
        </div>
        <div class="rounded-xl border border-white/10 bg-surface-800 p-5">
          <p class="text-xs text-gray-500 mb-1">创建时间</p>
          <p class="text-sm text-gray-300">{{ project.created_at }}</p>
        </div>
        <div class="rounded-xl border border-white/10 bg-surface-800 p-5">
          <p class="text-xs text-gray-500 mb-1">更新时间</p>
          <p class="text-sm text-gray-300">{{ project.updated_at }}</p>
        </div>
      </div>
    </div>

    <div v-else class="py-20 text-center text-gray-500">
      项目不存在
    </div>
  </AppLayout>
</template>
