<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listTemplates, useTemplate } from '@/api/studio'
import type { Template } from '@/types/studio'
import { ExternalLink, Play } from 'lucide-vue-next'
import AppLayout from '@/components/layout/AppLayout.vue'

const router = useRouter()
const templates = ref<Template[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await listTemplates()
    templates.value = res.data.data ?? []
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
})

const handleUse = async (template: Template) => {
  try {
    const res = await useTemplate(template.id)
    const projectId = res.data.project_id || 'new'
    router.push(`/projects/${projectId}`)
  } catch {
    // ignore
  }
}
</script>

<template>
  <AppLayout>
    <div class="space-y-6">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">模板市场</h1>
        <p class="text-sm text-gray-500 mt-1">选择合适的模板快速启动项目</p>
      </div>

      <div v-if="loading" class="py-20 text-center text-gray-500">
        <div class="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin mx-auto" />
      </div>

      <div v-else-if="!templates.length" class="py-20 text-center">
        <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-white/5 flex items-center justify-center">
          <LayersIcon class="w-8 h-8 text-gray-600" />
        </div>
        <p class="text-gray-400 text-lg">暂无可用模板</p>
      </div>

      <div v-else class="grid gap-4 grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="tpl in templates"
          :key="tpl.id"
          class="group rounded-xl border border-white/10 bg-surface-800 hover:border-brand-500/30 transition-all duration-300 overflow-hidden"
        >
          <!-- 预览图 -->
          <div class="aspect-video bg-gradient-to-br from-brand-500/20 to-purple-500/20 flex items-center justify-center">
            <LayersIcon class="w-10 h-10 text-brand-400/50" />
          </div>

          <div class="p-5 space-y-3">
            <div class="flex items-start justify-between">
              <div>
                <h3 class="font-semibold text-gray-100">{{ tpl.name }}</h3>
                <span class="text-xs text-gray-500 mt-0.5 block">{{ tpl.category }}</span>
              </div>
              <button
                class="flex items-center gap-1.5 rounded-lg bg-brand-500/15 hover:bg-brand-500/25 text-brand-400 px-3 py-1.5 text-xs font-medium transition-colors"
                @click="handleUse(tpl)"
              >
                <Play class="w-3 h-3" />
                使用
              </button>
            </div>

            <p class="text-sm text-gray-500 line-clamp-2">{{ tpl.description }}</p>

            <div class="flex items-center gap-2 pt-1">
              <button class="text-xs text-gray-600 hover:text-gray-400 flex items-center gap-1 transition-colors">
                <ExternalLink class="w-3 h-3" />
                预览
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </AppLayout>
</template>

<script lang="ts">
import { Layers } from 'lucide-vue-next'
const LayersIcon = Layers
</script>
