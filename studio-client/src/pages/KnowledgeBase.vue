<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listKnowledgeBases, ragSearch, type KnowledgeBase, type RAGSearchResult } from '@/api/rag'
import { BookOpen, Search, Database, Loader2, FileText } from 'lucide-vue-next'

const kbs = ref<KnowledgeBase[]>([])
const loading = ref(true)
const searchQuery = ref('')
const searchResults = ref<RAGSearchResult[]>([])
const searching = ref(false)
const selectedKb = ref<string | null>(null)

onMounted(async () => {
  try {
    const res = await listKnowledgeBases()
    kbs.value = res.data.data ?? []
  } catch {
    // 后端未启动
  } finally {
    loading.value = false
  }
})

const handleSearch = async () => {
  if (!searchQuery.value.trim() || searching.value) return
  searching.value = true
  try {
    const kbIds = selectedKb.value ? [selectedKb.value] : undefined
    const res = await ragSearch(searchQuery.value, kbIds, 10)
    searchResults.value = res.data.data ?? []
  } catch {
    searchResults.value = []
  } finally {
    searching.value = false
  }
}

const formatScore = (score: number) => `${(score * 100).toFixed(1)}%`
</script>

<template>
  <div class="h-full max-h-screen flex flex-col">
    <!-- Header -->
    <header class="shrink-0 h-14 border-b border-white/8 bg-surface-900/50 backdrop-blur flex items-center px-6">
      <div class="flex items-center gap-3">
        <BookOpen class="w-5 h-5 text-brand-400" />
        <h2 class="text-sm font-semibold text-gray-200">知识库</h2>
      </div>
    </header>

    <div class="flex-1 overflow-y-auto p-6 space-y-6">
      <!-- 搜索栏 -->
      <div class="flex gap-3">
        <div class="flex-1 relative">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input
            v-model="searchQuery"
            placeholder="搜索知识库内容..."
            class="w-full rounded-xl bg-surface-800 border border-white/10 pl-10 pr-4 py-2.5 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-brand-500/50 transition-colors"
            @keydown.enter="handleSearch"
          />
        </div>
        <select
          v-model="selectedKb"
          class="rounded-xl bg-surface-800 border border-white/10 px-3 py-2.5 text-sm text-gray-300 focus:outline-none focus:border-brand-500/50"
        >
          <option :value="null">全部知识库</option>
          <option v-for="kb in kbs" :key="kb.kb_id" :value="kb.kb_id">{{ kb.name }}</option>
        </select>
        <button
          :disabled="searching || !searchQuery.trim()"
          class="rounded-xl bg-gradient-to-r from-brand-500 to-purple-500 px-5 py-2.5 text-sm font-medium text-white hover:shadow-lg hover:shadow-brand-500/20 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
          @click="handleSearch"
        >
          <Loader2 v-if="searching" class="w-4 h-4 animate-spin" />
          <span v-else>搜索</span>
        </button>
      </div>

      <!-- 知识库列表 -->
      <section>
        <h3 class="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">知识库列表</h3>
        <div v-if="loading" class="py-10 text-center text-gray-500">
          <Loader2 class="w-6 h-6 animate-spin mx-auto mb-2 text-brand-400" />
          加载中...
        </div>
        <div v-else-if="!kbs.length" class="py-10 text-center">
          <Database class="w-10 h-10 text-gray-600 mx-auto mb-3" />
          <p class="text-gray-400 text-sm">暂无知识库</p>
          <p class="text-gray-600 text-xs mt-1">联系管理员创建知识库</p>
        </div>
        <div v-else class="grid gap-3 grid-cols-1 md:grid-cols-2 xl:grid-cols-3">
          <div
            v-for="kb in kbs"
            :key="kb.kb_id"
            :class="[
              'rounded-xl border p-4 transition-all duration-200 cursor-pointer',
              selectedKb === kb.kb_id
                ? 'border-brand-500/40 bg-brand-500/10'
                : 'border-white/8 bg-surface-800 hover:border-white/15',
            ]"
            @click="selectedKb = kb.kb_id"
          >
            <div class="flex items-start gap-3">
              <div class="w-8 h-8 rounded-lg bg-brand-500/10 flex items-center justify-center shrink-0">
                <BookOpen class="w-4 h-4 text-brand-400" />
              </div>
              <div class="min-w-0">
                <h4 class="text-sm font-medium text-gray-200 truncate">{{ kb.name }}</h4>
                <p class="text-xs text-gray-500 mt-0.5 line-clamp-2">{{ kb.description || '暂无描述' }}</p>
                <div class="flex items-center gap-3 mt-2 text-xs text-gray-600">
                  <span>{{ kb.stats?.documents || 0 }} 文档</span>
                  <span>{{ kb.stats?.chunks || 0 }} 片段</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 搜索结果 -->
      <section v-if="searchResults.length">
        <h3 class="text-xs font-medium text-gray-500 uppercase tracking-wider mb-3">
          搜索结果 ({{ searchResults.length }})
        </h3>
        <div class="space-y-3">
          <div
            v-for="(result, idx) in searchResults"
            :key="idx"
            class="rounded-xl border border-white/8 bg-surface-800 p-4 transition-colors hover:border-white/15"
          >
            <div class="flex items-start gap-3">
              <FileText class="w-4 h-4 text-brand-400 mt-0.5 shrink-0" />
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2 mb-1">
                  <span class="text-xs text-brand-400 font-medium">{{ result.kb_name }}</span>
                  <span class="text-xs text-gray-500">{{ formatScore(result.score) }} 相关</span>
                </div>
                <p class="text-sm text-gray-300 whitespace-pre-wrap line-clamp-4">{{ result.content }}</p>
                <p v-if="result.source" class="text-xs text-gray-600 mt-1 truncate">{{ result.source }}</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- 空搜索 -->
      <section
        v-if="!searchResults.length && searchQuery && !searching && !loading"
        class="py-12 text-center"
      >
        <Search class="w-10 h-10 text-gray-600 mx-auto mb-3" />
        <p class="text-gray-400 text-sm">未找到相关内容</p>
        <p class="text-gray-600 text-xs mt-1">尝试更换关键词或知识库</p>
      </section>
    </div>
  </div>
</template>
