<script setup lang="ts">
import { onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import { structuredOutputApi } from "@/api/model-features"
import type { Template } from "@/types/studio"
import { ExternalLink, LayoutGrid, Play, Search } from "lucide-vue-next"

const router = useRouter()
const templates = ref<Template[]>([])
const filtered = ref<Template[]>([])
const loading = ref(true)
const searchText = ref("")

onMounted(async () => {
  try {
    const res = await structuredOutputApi.listTemplates()
    templates.value = res.data.data ?? []
    filtered.value = [...templates.value]
  } catch {
    /* ignore */
  } finally {
    loading.value = false
  }
})

function filter() {
  const q = searchText.value.toLowerCase()
  filtered.value = templates.value.filter(
    (t) =>
      t.name.toLowerCase().includes(q) ||
      t.description?.toLowerCase().includes(q) ||
      t.category?.toLowerCase().includes(q),
  )
}

function handleUse(_template: Template) {
  router.push("/projects")
}
</script>

<template>
  <div class="p-6">
    <div class="max-w-5xl mx-auto">
      <header class="mb-8">
        <h1 class="text-3xl font-bold text-white">模板市场</h1>
        <p class="text-gray-400 mt-2">浏览并使用社区模板快速启动你的项目</p>
        <div class="mt-4 relative max-w-md">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input v-model="searchText" @input="filter" class="w-full pl-10 pr-4 py-2.5 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-500/50" placeholder="搜索模板名称、分类..." />
        </div>
      </header>

      <div v-if="loading" class="py-20 text-center text-gray-500">
        <div class="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin mx-auto" />
      </div>

      <div v-else-if="!filtered.length" class="py-20 text-center">
        <LayoutGrid class="w-12 h-12 mx-auto mb-3 text-gray-600" />
        <p class="text-gray-400">{{ searchText ? '无匹配模板' : '暂无可用模板' }}</p>
      </div>

      <div v-else class="grid gap-6 grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
        <div
          v-for="tpl in filtered" :key="tpl.id"
          class="group rounded-2xl border border-gray-800/50 bg-gray-900/50 hover:border-brand-500/30 transition-all duration-300 overflow-hidden"
        >
          <div class="aspect-video bg-gradient-to-br from-brand-500/20 to-purple-500/20 flex items-center justify-center">
            <LayoutGrid class="w-10 h-10 text-brand-400/50" />
          </div>
          <div class="p-5 space-y-3">
            <div class="flex items-start justify-between">
              <div>
                <h3 class="font-semibold text-gray-100">{{ tpl.name }}</h3>
                <span class="text-xs text-gray-500 mt-0.5 block">{{ tpl.category }}</span>
              </div>
              <button class="flex items-center gap-1.5 rounded-xl bg-brand-500/15 hover:bg-brand-500/25 text-brand-400 px-3 py-1.5 text-xs font-medium transition-colors" @click="handleUse(tpl)">
                <Play class="w-3 h-3" /> 使用
              </button>
            </div>
            <p class="text-sm text-gray-500 line-clamp-2">{{ tpl.description }}</p>
            <div class="flex items-center gap-2 pt-1">
              <button class="text-xs text-gray-600 hover:text-gray-400 flex items-center gap-1 transition-colors">
                <ExternalLink class="w-3 h-3" /> 预览
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
