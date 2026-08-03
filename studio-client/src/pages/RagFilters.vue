<template>
  <div class="p-6">
    <div class="max-w-6xl mx-auto">
      <header class="mb-8 text-center">
        <h1 class="text-3xl font-bold text-white">🧹 文本过滤器</h1>
        <p class="text-[var(--color-ide-text-dim)] mt-2">测试和预览 RAG 文本过滤链效果</p>
      </header>

      <!-- 过滤器列表 -->
      <div class="p-4 rounded-2xl bg-gray-900/50 border border-gray-800/50 mb-6">
        <div class="flex items-center justify-between mb-3">
          <h2 class="text-sm font-medium text-white">可用过滤器</h2>
          <div class="flex gap-2">
            <button @click="selectPreset('rag_ingest')" class="text-xs px-2.5 py-1 rounded-lg bg-brand-500/20 text-brand-400 hover:bg-brand-500/30 transition-colors">RAG 摄入</button>
            <button @click="selectPreset('markdown_clean')" class="text-xs px-2.5 py-1 rounded-lg bg-purple-500/20 text-purple-400 hover:bg-purple-500/30 transition-colors">MD 清洗</button>
            <button @click="selectPreset('webpage_clean')" class="text-xs px-2.5 py-1 rounded-lg bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 transition-colors">网页清洗</button>
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <button
            v-for="f in availableFilters"
            :key="f.name"
            @click="toggleFilter(f.name)"
            class="px-3 py-1.5 rounded-lg text-xs transition-all"
            :class="selectedFilters.includes(f.name)
              ? 'bg-brand-500/30 text-brand-300 border border-brand-500/30'
              : 'bg-gray-800 text-[var(--color-ide-text-dim)] border border-gray-700 hover:text-white'"
            :title="f.description"
          >
            {{ f.name }}
          </button>
        </div>
        <p v-if="selectedFilters.length" class="text-xs text-[var(--color-ide-text-dim)] mt-3">
          已选: {{ selectedFilters.join(' → ') }}
        </p>
      </div>

      <!-- 输入+输出面板 -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- 输入区 -->
        <div class="p-4 rounded-2xl bg-gray-900/50 border border-gray-800/50">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-sm font-medium text-white">📝 输入文本</h2>
            <span class="text-xs text-[var(--color-ide-text-dim)]">{{ inputText.length }} 字符</span>
          </div>
          <textarea
            v-model="inputText"
            rows="16"
            class="w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white placeholder-[var(--color-ide-text-dim)] outline-none focus:border-brand-500/50 resize-none font-mono"
            :placeholder="sampleText"
          ></textarea>
          <button
            @click="applyFilters"
            :disabled="filtering || !inputText || !selectedFilters.length"
            class="w-full mt-3 py-3 rounded-xl bg-gradient-to-r from-brand-500 to-purple-500 text-white font-medium disabled:opacity-50 transition-all"
          >
            {{ filtering ? '⏳ 过滤中...' : '🔧 应用过滤器' }}
          </button>
          <button
            @click="previewFilters"
            :disabled="filtering || !inputText || !selectedFilters.length"
            class="w-full mt-2 py-2.5 rounded-xl bg-gray-800 text-sm text-[var(--color-ide-text-dim)] hover:text-white border border-gray-700 transition-colors"
          >
            🔍 逐级预览
          </button>
        </div>

        <!-- 输出区 -->
        <div class="p-4 rounded-2xl bg-gray-900/50 border border-gray-800/50">
          <div class="flex items-center justify-between mb-3">
            <h2 class="text-sm font-medium text-white">✅ 过滤结果</h2>
            <div v-if="filterResult" class="flex gap-3 text-xs text-[var(--color-ide-text-dim)]">
              <span>压缩率: {{ (filterResult.compression_ratio * 100).toFixed(1) }}%</span>
              <span>{{ filterResult.original_length }} → {{ filterResult.filtered_length }}</span>
            </div>
          </div>
          <div v-if="!filterResult" class="flex items-center justify-center h-full min-h-[300px] text-[var(--color-ide-text-dim)]">
            <p class="text-center">
              <span class="text-4xl block mb-3">🔄</span>
              <span class="text-sm">选择过滤器并点击"应用"查看结果</span>
            </p>
          </div>
          <pre v-else class="p-4 rounded-xl bg-gray-800/50 border border-gray-700/30 text-sm text-[var(--color-ide-text)] max-h-[300px] overflow-auto font-mono whitespace-pre-wrap">{{ filterResult.filtered }}</pre>
          <!-- 应用的过滤器标签 -->
          <div v-if="filterResult" class="flex flex-wrap gap-1.5 mt-3">
            <span v-for="name in filterResult.filters_applied" :key="name" class="px-2 py-0.5 rounded-full text-[10px] bg-brand-500/20 text-brand-400">{{ name }}</span>
          </div>
        </div>
      </div>

      <!-- 逐级预览结果 -->
      <div v-if="previewStages.length" class="mt-6 p-4 rounded-2xl bg-gray-900/50 border border-gray-800/50">
        <h2 class="text-sm font-medium text-white mb-3">🔍 逐级预览</h2>
        <div class="space-y-3">
          <div v-for="(stage, i) in previewStages" :key="i" class="p-3 rounded-xl bg-gray-800/50 border border-gray-700/30">
            <div class="flex items-center gap-2 mb-2">
              <span class="w-5 h-5 rounded-md bg-brand-500/20 text-brand-400 text-[10px] flex items-center justify-center font-mono">{{ i + 1 }}</span>
              <span class="text-xs font-medium text-brand-400">{{ stage.filter_name }}</span>
              <span class="text-[10px] text-[var(--color-ide-text-dim)]">-{{ stage.chars_removed }} 字符</span>
            </div>
            <div class="grid grid-cols-1 lg:grid-cols-2 gap-2">
              <div>
                <p class="text-[10px] text-[var(--color-ide-text-dim)] mb-1">Before</p>
                <pre class="p-2 rounded-lg bg-gray-900/50 text-xs text-[var(--color-ide-text-dim)] max-h-24 overflow-auto font-mono whitespace-pre-wrap">{{ truncateText(stage.before, 200) }}</pre>
              </div>
              <div>
                <p class="text-[10px] text-[var(--color-ide-text-dim)] mb-1">After</p>
                <pre class="p-2 rounded-lg bg-gray-900/50 text-xs text-[var(--color-ide-text)] max-h-24 overflow-auto font-mono whitespace-pre-wrap">{{ truncateText(stage.after, 200) }}</pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ragFiltersApi, type FilterInfo, type FilterApplyResponse, type FilterPreviewItem } from '@/api/ragFilters'

const presets: Record<string, string[]> = {
  rag_ingest: ['remove_html', 'remove_boilerplate', 'remove_urls', 'normalize_ws', 'deduplicate_lines'],
  markdown_clean: ['strip_md', 'remove_urls', 'normalize_ws'],
  webpage_clean: ['remove_html', 'remove_boilerplate', 'remove_urls', 'normalize_ws', 'deduplicate_lines', 'truncate'],
}

const availableFilters = ref<FilterInfo[]>([])
const selectedFilters = ref<string[]>([])
const inputText = ref('')
const filterResult = ref<FilterApplyResponse | null>(null)
const previewStages = ref<FilterPreviewItem[]>([])
const filtering = ref(false)

const sampleText = `<html>
<body>
  <h1>项目说明</h1>
  <p>这是一段示例文本，包含 <a href="https://example.com">链接</a> 和    多余空格。</p>
  <div class="cookie-banner">我们使用 Cookie 来改善体验</div>
  <pre><code>console.log("hello world");</code></pre>
  <p>这是一段示例文本，包含重复的句子。</p>
  <p>这是一段示例文本，包含重复的句子。</p>
  <footer>&copy; 2024 Example Corp. All rights reserved.</footer>
</body>
</html>`

// 预设选择
function selectPreset(name: string) {
  selectedFilters.value = [...presets[name]]
}

// 切换过滤器
function toggleFilter(name: string) {
  const idx = selectedFilters.value.indexOf(name)
  if (idx >= 0) {
    selectedFilters.value.splice(idx, 1)
  } else {
    selectedFilters.value.push(name)
  }
}

// 应用过滤
async function applyFilters() {
  if (!inputText.value || !selectedFilters.value.length) return
  filtering.value = true
  previewStages.value = []
  try {
    const res = await ragFiltersApi.applyFilters({
      text: inputText.value,
      filter_names: selectedFilters.value,
    })
    filterResult.value = res.data
  } catch (e) {
    console.error('applyFilters failed:', e)
  } finally {
    filtering.value = false
  }
}

// 逐级预览
async function previewFilters() {
  if (!inputText.value || !selectedFilters.value.length) return
  filtering.value = true
  try {
    const res = await ragFiltersApi.previewFilters({
      text: inputText.value,
      filter_names: selectedFilters.value,
    })
    previewStages.value = res.data.stages || []
  } catch (e) {
    console.error('previewFilters failed:', e)
  } finally {
    filtering.value = false
  }
}

// 工具
function truncateText(text: string, maxLen: number): string {
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}

// 生命周期
onMounted(async () => {
  try {
    const res = await ragFiltersApi.listFilters()
    availableFilters.value = res.data.filters || []
  } catch (e) {
    console.error('listFilters failed:', e)
  }
})
</script>
