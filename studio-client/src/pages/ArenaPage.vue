<template>
  <div class="p-6">
    <div class="max-w-5xl mx-auto">
      <header class="mb-8 text-center">
        <h1 class="text-3xl font-bold text-white">⚔️ 模型竞技场</h1>
        <p class="text-gray-400 mt-2">并排对比两个 AI 模型，投票选出最佳回答</p>
      </header>

      <!-- 对比输入 -->
      <div class="p-6 rounded-2xl bg-gray-900/50 border border-gray-800/50 mb-8">
        <div class="flex flex-col sm:flex-row gap-4 mb-4">
          <div class="flex-1">
            <label class="text-xs text-gray-500 mb-1 block">模型 A</label>
            <select v-model="form.model_a" class="w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500/50">
              <option value="openai-gpt4o">GPT-4o</option>
              <option value="claude-sonnet">Claude Sonnet 4</option>
              <option value="deepseek-v3">DeepSeek-V3</option>
              <option value="openai-o3">o3</option>
              <option value="zhipu-glm4">GLM-4 Plus</option>
            </select>
          </div>
          <div class="flex items-end pb-2">
            <span class="text-2xl font-bold text-gray-600">VS</span>
          </div>
          <div class="flex-1">
            <label class="text-xs text-gray-500 mb-1 block">模型 B</label>
            <select v-model="form.model_b" class="w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500/50">
              <option value="claude-sonnet">Claude Sonnet 4</option>
              <option value="openai-gpt4o">GPT-4o</option>
              <option value="deepseek-v3">DeepSeek-V3</option>
              <option value="openai-o3">o3</option>
              <option value="zhipu-glm4">GLM-4 Plus</option>
            </select>
          </div>
        </div>
        <textarea v-model="form.prompt" rows="4" class="w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-500/50 resize-none mb-4" placeholder="输入你想对比的问题..."></textarea>
        <button @click="runCompare" :disabled="comparing || !form.prompt" class="w-full py-3 rounded-xl bg-gradient-to-r from-brand-500 to-purple-500 text-white font-medium disabled:opacity-50">
          {{ comparing ? '正在生成...' : '开始对比' }}
        </button>
      </div>

      <!-- 对比结果 -->
      <div v-if="result" class="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
        <div class="p-6 rounded-2xl bg-gray-900/50 border border-gray-800/50">
          <div class="flex items-center justify-between mb-4">
            <span class="px-2.5 py-0.5 text-xs rounded-full font-medium bg-blue-500/15 text-blue-400">{{ result.model_a }}</span>
            <span class="text-xs text-gray-500">{{ result.latency_a_ms?.toFixed(0) }}ms</span>
          </div>
          <div class="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto">{{ result.response_a }}</div>
        </div>
        <div class="p-6 rounded-2xl bg-gray-900/50 border border-gray-800/50">
          <div class="flex items-center justify-between mb-4">
            <span class="px-2.5 py-0.5 text-xs rounded-full font-medium bg-purple-500/15 text-purple-400">{{ result.model_b }}</span>
            <span class="text-xs text-gray-500">{{ result.latency_b_ms?.toFixed(0) }}ms</span>
          </div>
          <div class="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto">{{ result.response_b }}</div>
        </div>
      </div>

      <!-- 投票 -->
      <div v-if="result && !voted" class="p-4 rounded-2xl bg-gray-900/50 border border-gray-800/50 text-center mb-8">
        <p class="text-gray-400 mb-4">你认为谁的回答更好？</p>
        <div class="flex justify-center gap-4">
          <button @click="vote('A')" class="px-6 py-3 rounded-xl text-sm font-medium bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-all hover:scale-105">🏆 {{ result.model_a }}</button>
          <button @click="vote('B')" class="px-6 py-3 rounded-xl text-sm font-medium bg-green-500/10 text-green-400 border border-green-500/20 hover:bg-green-500/20 transition-all hover:scale-105">🏆 {{ result.model_b }}</button>
          <button @click="vote('tie')" class="px-6 py-3 rounded-xl text-sm font-medium bg-gray-500/10 text-gray-400 border border-gray-500/20 hover:bg-gray-500/20 transition-all hover:scale-105">🤝 平局</button>
        </div>
      </div>
      <div v-if="voted" class="text-center text-green-400 mb-8">✅ 投票已记录，感谢你的贡献！</div>

      <!-- ELO 排行榜 -->
      <div class="p-6 rounded-2xl bg-gray-900/50 border border-gray-800/50">
        <h2 class="text-lg font-bold text-white mb-4">🏅 ELO 排行榜</h2>
        <div v-if="!rankings.length" class="text-center text-gray-500 py-8">暂无数据</div>
        <div v-else class="space-y-1">
          <div v-for="(r, i) in rankings" :key="r.model_name" class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-800/50">
            <span class="w-7 h-7 flex items-center justify-center rounded-full text-xs font-bold bg-gray-800 text-gray-400" :class="{ 'bg-yellow-500/20 text-yellow-400': i === 0, 'bg-gray-300/20 text-gray-300': i === 1, 'bg-orange-500/20 text-orange-400': i === 2 }">{{ i + 1 }}</span>
            <span class="flex-1 text-sm text-white">{{ r.model_name }}</span>
            <span class="text-sm font-bold text-brand-400">{{ Math.round(r.elo) }}</span>
            <span class="text-xs text-gray-500 w-20 text-right">{{ r.wins }}W / {{ r.losses }}L</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { arenaApi, type ArenaCompareResult, type EloRankingEntry } from '@/api/model-features'

const form = ref({ model_a: 'openai-gpt4o', model_b: 'claude-sonnet', prompt: '' })
const comparing = ref(false)
const result = ref<ArenaCompareResult | null>(null)
const voted = ref(false)
const currentId = ref('')
const rankings = ref<EloRankingEntry[]>([])

async function runCompare() {
  comparing.value = true; result.value = null; voted.value = false
  try {
    const res = await arenaApi.compare({ ...form.value, category: 'chat' })
    result.value = res.data; currentId.value = res.data.comparison_id
  } finally { comparing.value = false }
}

async function vote(winner: 'A' | 'B' | 'tie') {
  await arenaApi.vote(currentId.value, winner)
  voted.value = true; await fetchRankings()
}

async function fetchRankings() {
  const res = await arenaApi.rankings()
  rankings.value = res.data.rankings
}

onMounted(fetchRankings)
</script>
