<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { listAgentTools, type AgentToolSummary } from '@/api/agent'
import { Wrench, Search, Loader2, Tag, Zap } from 'lucide-vue-next'

const tools = ref<AgentToolSummary[]>([])
const loading = ref(true)
const searchText = ref('')
const selectedCategory = ref<string | null>(null)

onMounted(async () => {
  try {
    const res = await listAgentTools()
    tools.value = res.data.tools ?? []
  } catch {
    // 后端未启动
  } finally {
    loading.value = false
  }
})

const categories = computed(() => {
  const cats = new Set(tools.value.map((t) => t.category))
  return Array.from(cats)
})

const filteredTools = computed(() => {
  let list = tools.value
  if (searchText.value) {
    const q = searchText.value.toLowerCase()
    list = list.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.tags.some((tag) => tag.toLowerCase().includes(q)),
    )
  }
  if (selectedCategory.value) {
    list = list.filter((t) => t.category === selectedCategory.value)
  }
  return list
})

const categoryLabel: Record<string, string> = {
  builtin: '内置工具',
  mcp: 'MCP 工具',
  knowledge_base: '知识库',
  web: '网络工具',
  file: '文件操作',
  search: '搜索',
}
</script>

<template>
  <div class="h-full w-full flex flex-col overflow-hidden bg-[var(--color-ide-bg)] text-[var(--color-ide-text)]">
    <!-- Header -->
    <header class="shrink-0 h-14 border-b border-white/8 bg-surface-900/50 backdrop-blur flex items-center px-6">
      <div class="flex items-center gap-3">
        <Wrench class="w-5 h-5 text-brand-400" />
        <h2 class="text-sm font-semibold text-gray-200">工具集</h2>
        <span class="text-xs text-gray-600">{{ tools.length }} 个工具</span>
      </div>
    </header>

    <div class="flex-1 overflow-y-auto p-6 space-y-6">
      <!-- 搜索与筛选 -->
      <div class="flex gap-3 flex-wrap">
        <div class="flex-1 min-w-[200px] relative">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            v-model="searchText"
            placeholder="搜索工具..."
            class="w-full rounded-xl bg-surface-800 border border-white/10 pl-10 pr-4 py-2.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500/50 transition-colors"
          />
        </div>
        <button
          v-for="cat in categories"
          :key="cat"
          :class="[
            'rounded-lg px-3 py-2 text-xs font-medium transition-all',
            selectedCategory === cat
              ? 'bg-brand-500/20 text-brand-400 border border-brand-500/30'
              : 'bg-white/5 text-gray-400 border border-white/8 hover:text-gray-200 hover:bg-white/8',
          ]"
          @click="selectedCategory = selectedCategory === cat ? null : cat"
        >
          {{ categoryLabel[cat] || cat }}
        </button>
        <button
          v-if="selectedCategory"
          class="rounded-lg px-3 py-2 text-xs text-gray-500 hover:text-gray-300 transition-colors"
          @click="selectedCategory = null"
        >
          清除筛选
        </button>
      </div>

      <!-- 加载 -->
      <div v-if="loading" class="py-20 text-center text-gray-500">
        <Loader2 class="w-6 h-6 animate-spin mx-auto mb-2 text-brand-400" />
        加载工具列表...
      </div>

      <!-- 空状态 -->
      <div v-else-if="!filteredTools.length" class="py-20 text-center">
        <Wrench class="w-10 h-10 text-gray-600 mx-auto mb-3" />
        <p v-if="searchText || selectedCategory" class="text-gray-400 text-sm">未找到匹配的工具</p>
        <p v-else class="text-gray-400 text-sm">暂无可用的工具</p>
      </div>

      <!-- 工具卡片网格 -->
      <div v-else class="grid gap-3 grid-cols-1 md:grid-cols-2">
        <div
          v-for="tool in filteredTools"
          :key="tool.name"
          class="rounded-xl border border-white/8 bg-surface-800 p-4 hover:border-white/15 transition-all duration-200 group"
        >
          <div class="flex items-start gap-3">
            <div class="w-9 h-9 rounded-lg bg-brand-500/10 flex items-center justify-center shrink-0">
              <Zap class="w-4 h-4 text-brand-400" />
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2 mb-1">
                <h4 class="text-sm font-semibold text-gray-200 truncate">{{ tool.name }}</h4>
                <span class="text-[10px] text-brand-400 bg-brand-500/10 rounded-md px-1.5 py-0.5 font-mono">
                  v{{ tool.version }}
                </span>
              </div>
              <p class="text-xs text-gray-500 mb-2 line-clamp-2">{{ tool.description }}</p>
              <div class="flex items-center gap-1.5 flex-wrap">
                <span class="text-[10px] text-gray-500 bg-white/5 rounded-md px-1.5 py-0.5">
                  {{ categoryLabel[tool.category] || tool.category }}
                </span>
                <span
                  v-for="tag in tool.tags"
                  :key="tag"
                  class="text-[10px] text-gray-600 bg-white/5 rounded-md px-1.5 py-0.5"
                >
                  {{ tag }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
