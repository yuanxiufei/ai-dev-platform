<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { listAgentTools, getAgentTool, callAgentTool, type AgentTool, type AgentToolSummary } from '@/api/agent'
import { Wrench, Search, Loader2, Zap, Play, ArrowLeft, Code } from 'lucide-vue-next'

const tools = ref<AgentToolSummary[]>([])
const loading = ref(true)
const searchText = ref('')
const selectedCategory = ref<string | null>(null)

// 工具详情
const selectedTool = ref<AgentTool | null>(null)
const detailLoading = ref(false)
const testArgs = ref<Record<string, string>>({})
const testResult = ref<string | null>(null)
const testError = ref<string | null>(null)
const testing = ref(false)

onMounted(async () => {
  try {
    const res = await listAgentTools()
    tools.value = res.data.tools ?? []
  } catch { /* 后端未启动 */ }
  finally { loading.value = false }
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
      (t) => t.name.toLowerCase().includes(q) || t.description.toLowerCase().includes(q) || t.tags.some((tag) => tag.toLowerCase().includes(q)),
    )
  }
  if (selectedCategory.value) list = list.filter((t) => t.category === selectedCategory.value)
  return list
})

const openDetail = async (name: string) => {
  detailLoading.value = true
  selectedTool.value = null
  testArgs.value = {}
  testResult.value = null
  testError.value = null
  try {
    const res = await getAgentTool(name)
    selectedTool.value = res.data
    // 初始化参数
    for (const p of res.data.parameters) {
      testArgs.value[p.name] = p.default ? String(p.default) : ''
    }
  } catch { /* 获取失败 */ }
  finally { detailLoading.value = false }
}

const handleTest = async () => {
  if (!selectedTool.value || testing.value) return
  testing.value = true
  testResult.value = null
  testError.value = null
  try {
    const args: Record<string, unknown> = {}
    for (const p of selectedTool.value.parameters) {
      if (testArgs.value[p.name]) {
        const val = testArgs.value[p.name]
        // 尝试解析 JSON
        try { args[p.name] = JSON.parse(val) }
        catch { args[p.name] = val }
      }
    }
    const res = await callAgentTool(selectedTool.value.name, args)
    if (res.data.success) {
      testResult.value = res.data.result || '(空结果)'
    } else {
      testError.value = res.data.error || '调用失败'
    }
  } catch (e: unknown) {
    testError.value = (e as Error).message || '测试失败'
  } finally {
    testing.value = false
  }
}

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
  <div class="space-y-6">
    <!-- 页头 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">工具管理</h1>
        <p class="text-sm text-gray-500 mt-1">查看和管理 Agent 可用的所有工具</p>
      </div>
    </div>

    <!-- 搜索与分类筛选 -->
    <div class="flex gap-3 flex-wrap">
      <div class="flex-1 min-w-[200px] relative">
        <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
        <input
          v-model="searchText"
          placeholder="搜索工具名称或描述..."
          class="w-full rounded-lg bg-surface-800 border border-white/10 pl-10 pr-4 py-2.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500/50 transition-colors"
        />
      </div>
      <button
        v-for="cat in categories"
        :key="cat"
        :class="[
          'rounded-lg px-3 py-2 text-xs font-medium transition-all',
          selectedCategory === cat
            ? 'bg-brand-500/20 text-brand-400 border border-brand-500/30'
            : 'bg-surface-800 text-gray-400 border border-white/8 hover:text-gray-200',
        ]"
        @click="selectedCategory = selectedCategory === cat ? null : cat"
      >
        {{ categoryLabel[cat] || cat }}
      </button>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="py-20 text-center text-gray-500">
      <Loader2 class="w-6 h-6 animate-spin mx-auto mb-2 text-brand-400" />
      加载中...
    </div>

    <!-- 列表 + 详情双栏 -->
    <div v-else class="flex gap-6">
      <!-- 左侧：工具列表 -->
      <div :class="['space-y-2', selectedTool ? 'w-80 shrink-0' : 'flex-1']">
        <div v-if="!filteredTools.length" class="py-10 text-center">
          <Wrench class="w-8 h-8 text-gray-600 mx-auto mb-2" />
          <p class="text-gray-500 text-sm">未找到工具</p>
        </div>
        <div
          v-for="tool in filteredTools"
          :key="tool.name"
          :class="[
            'rounded-lg border p-3.5 cursor-pointer transition-all duration-200',
            selectedTool?.name === tool.name
              ? 'border-brand-500/30 bg-brand-500/10'
              : 'border-white/8 bg-surface-800 hover:border-white/15',
          ]"
          @click="openDetail(tool.name)"
        >
          <div class="flex items-center gap-3">
            <div class="w-7 h-7 rounded-md bg-brand-500/10 flex items-center justify-center shrink-0">
              <Zap class="w-3.5 h-3.5 text-brand-400" />
            </div>
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-1.5">
                <span class="text-xs font-semibold text-gray-200 truncate">{{ tool.name }}</span>
                <span class="text-[9px] text-gray-600 font-mono">v{{ tool.version }}</span>
              </div>
              <p class="text-[11px] text-gray-500 truncate mt-0.5">{{ tool.description }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- 右侧：工具详情 -->
      <div v-if="selectedTool" class="flex-1 min-w-0">
        <div v-if="detailLoading" class="py-10 text-center">
          <Loader2 class="w-5 h-5 animate-spin mx-auto text-brand-400" />
        </div>
        <div v-else class="rounded-xl border border-white/10 bg-surface-800 p-6 space-y-5">
          <div class="flex items-center justify-between">
            <div>
              <h3 class="text-lg font-bold text-gray-100">{{ selectedTool.name }}</h3>
              <span class="text-xs text-gray-500">{{ categoryLabel[selectedTool.category] || selectedTool.category }}</span>
            </div>
            <span class="text-[11px] text-gray-600 bg-white/5 rounded-md px-2 py-1 font-mono">v{{ selectedTool.version }}</span>
          </div>

          <p class="text-sm text-gray-400">{{ selectedTool.description }}</p>

          <!-- 标签 -->
          <div class="flex gap-1.5 flex-wrap">
            <span v-for="tag in selectedTool.tags" :key="tag" class="text-[10px] text-gray-500 bg-white/5 rounded-md px-2 py-0.5">
              {{ tag }}
            </span>
          </div>

          <!-- 签名 -->
          <div class="rounded-lg bg-surface-900 p-3 font-mono text-xs text-gray-400">
            {{ selectedTool.signature }}
          </div>

          <!-- 参数列表 -->
          <div>
            <h4 class="text-xs font-semibold text-gray-300 mb-2 uppercase tracking-wider">参数</h4>
            <div class="space-y-2">
              <div v-for="p in selectedTool.parameters" :key="p.name" class="flex items-start gap-2 text-xs">
                <span class="text-brand-400 font-mono shrink-0">{{ p.name }}</span>
                <span class="text-gray-500">: {{ p.type }}</span>
                <span v-if="p.required" class="text-red-400 text-[10px]">required</span>
                <span class="text-gray-600 flex-1">{{ p.description }}</span>
              </div>
            </div>
          </div>

          <!-- 测试区 -->
          <div class="border-t border-white/8 pt-4">
            <h4 class="text-xs font-semibold text-gray-300 mb-3 uppercase tracking-wider">
              <Play class="w-3.5 h-3.5 inline mr-1 text-green-400" />
              测试调用
            </h4>
            <div class="space-y-3">
              <div v-for="p in selectedTool.parameters" :key="p.name">
                <label class="block text-[11px] text-gray-500 mb-1">{{ p.name }} <span class="text-gray-600">({{ p.type }})</span></label>
                <input
                  v-model="testArgs[p.name]"
                  :placeholder="p.description"
                  class="w-full rounded-lg border border-white/10 bg-surface-900 px-3 py-1.5 text-xs placeholder-gray-600 focus:border-brand-500/50 focus:outline-none transition-colors"
                />
              </div>
              <button
                :disabled="testing"
                class="flex items-center gap-2 rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/30 disabled:opacity-50 px-4 py-2 text-xs font-medium transition-colors"
                @click="handleTest"
              >
                <Loader2 v-if="testing" class="w-3.5 h-3.5 animate-spin" />
                <Play v-else class="w-3.5 h-3.5" />
                执行测试
              </button>
              <div v-if="testResult" class="rounded-lg bg-green-500/5 border border-green-500/20 p-3 font-mono text-xs text-green-400 whitespace-pre-wrap max-h-48 overflow-y-auto">
                {{ testResult }}
              </div>
              <div v-if="testError" class="rounded-lg bg-red-500/5 border border-red-500/20 p-3 text-xs text-red-400">
                {{ testError }}
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 未选中提示 -->
      <div v-else class="flex-1 flex items-center justify-center py-20">
        <div class="text-center">
          <Wrench class="w-10 h-10 text-gray-600 mx-auto mb-3" />
          <p class="text-gray-500 text-sm">选择左侧工具查看详情</p>
        </div>
      </div>
    </div>
  </div>
</template>
