<template>
  <div class="p-6 max-w-7xl mx-auto">
    <header class="mb-6">
      <h1 class="text-2xl font-bold text-white">模型竞技场</h1>
      <p class="text-gray-400 mt-1 text-sm">借鉴 Open WebUI Arena — 并排对比 + ELO 排行榜</p>
    </header>

    <!-- 对比面板 -->
    <div class="mb-8 p-5 rounded-xl bg-gray-800/50 border border-gray-700/50">
      <h2 class="text-lg font-bold text-white mb-3">并排对比</h2>
      <div class="space-y-4">
        <div class="flex items-end gap-4">
          <div class="flex-1">
            <label class="block text-sm text-gray-400 mb-1">模型 A</label>
            <select v-model="compareForm.model_a" class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500">
              <option value="openai-gpt4o">GPT-4o</option>
              <option value="openai-o3">o3</option>
              <option value="claude-sonnet">Claude Sonnet 4</option>
              <option value="deepseek-v3">DeepSeek-V3</option>
              <option value="zhipu-glm4">GLM-4 Plus</option>
              <option value="qwen-max">通义千问 Max</option>
            </select>
          </div>
          <span class="text-gray-500 font-bold text-xl pb-2">VS</span>
          <div class="flex-1">
            <label class="block text-sm text-gray-400 mb-1">模型 B</label>
            <select v-model="compareForm.model_b" class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500">
              <option value="claude-sonnet">Claude Sonnet 4</option>
              <option value="openai-gpt4o">GPT-4o</option>
              <option value="deepseek-v3">DeepSeek-V3</option>
              <option value="openai-o3">o3</option>
              <option value="zhipu-glm4">GLM-4 Plus</option>
              <option value="qwen-max">通义千问 Max</option>
            </select>
          </div>
        </div>
        <div class="w-48">
          <label class="block text-sm text-gray-400 mb-1">评测分类</label>
          <select v-model="compareForm.category" class="w-full px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white outline-none focus:border-brand-500">
            <option value="chat">通用对话</option>
            <option value="code">代码生成</option>
            <option value="vision">视觉理解</option>
          </select>
        </div>
        <label class="block text-sm text-gray-400">
          System Prompt（可选）
          <input v-model="compareForm.system_prompt" class="w-full mt-1 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-500" placeholder="设定模型角色..." />
        </label>
        <label class="block text-sm text-gray-400">
          提示词
          <textarea v-model="compareForm.prompt" rows="4" class="w-full mt-1 px-3 py-2 rounded-lg bg-gray-800 border border-gray-700 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-500 resize-none" placeholder="输入你的问题，两个模型将同时生成回答..."></textarea>
        </label>
        <button @click="runCompare" :disabled="comparing || !compareForm.prompt" class="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-brand-500 text-white hover:bg-brand-600 transition-colors text-sm font-medium disabled:opacity-50">
          <Zap v-if="comparing" class="w-4 h-4 animate-spin" />
          <Play v-else class="w-4 h-4" />
          {{ comparing ? '生成中...' : '开始对比' }}
        </button>
      </div>

      <div v-if="result" class="grid grid-cols-2 gap-4 mt-6">
        <div class="p-4 rounded-lg bg-gray-900/50 border border-gray-700/30">
          <div class="flex items-center justify-between mb-3">
            <span class="px-2 py-0.5 text-xs rounded-full font-medium bg-blue-500/15 text-blue-400">{{ result.model_a }}</span>
            <span class="text-xs text-gray-500">{{ result.latency_a_ms?.toFixed(0) }}ms | {{ result.tokens_a }} tokens</span>
          </div>
          <div class="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto">{{ result.response_a }}</div>
        </div>
        <div class="p-4 rounded-lg bg-gray-900/50 border border-gray-700/30">
          <div class="flex items-center justify-between mb-3">
            <span class="px-2 py-0.5 text-xs rounded-full font-medium bg-purple-500/15 text-purple-400">{{ result.model_b }}</span>
            <span class="text-xs text-gray-500">{{ result.latency_b_ms?.toFixed(0) }}ms | {{ result.tokens_b }} tokens</span>
          </div>
          <div class="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap max-h-96 overflow-y-auto">{{ result.response_b }}</div>
        </div>
      </div>

      <div v-if="result && !voted" class="flex items-center gap-4 mt-4 p-3 rounded-lg bg-gray-900/50">
        <span class="text-sm text-gray-400">哪个更好？</span>
        <div class="flex gap-2">
          <button @click="vote('A')" class="px-3 py-1.5 rounded-lg bg-green-500/15 text-green-400 text-sm hover:bg-green-500/25 transition-colors">🏆 A 更好</button>
          <button @click="vote('B')" class="px-3 py-1.5 rounded-lg bg-green-500/15 text-green-400 text-sm hover:bg-green-500/25 transition-colors">🏆 B 更好</button>
          <button @click="vote('tie')" class="px-3 py-1.5 rounded-lg bg-gray-500/15 text-gray-400 text-sm hover:bg-gray-500/25 transition-colors">🤝 平局</button>
        </div>
      </div>
      <div v-if="voted" class="mt-4 text-center text-green-400 text-sm">✅ 投票已记录</div>
    </div>

    <!-- ELO 排行榜 -->
    <div class="p-5 rounded-xl bg-gray-800/50 border border-gray-700/50">
      <h2 class="text-lg font-bold text-white mb-3">ELO 排行榜</h2>
      <div class="flex gap-2 mb-4">
        <button v-for="cat in ['', 'chat', 'code', 'vision']" :key="cat || 'all'" @click="rankCategory = cat; fetchRankings()"
          :class="['px-3 py-1 rounded-lg text-sm transition-colors', rankCategory === cat ? 'bg-brand-500/15 text-brand-400' : 'text-gray-400 hover:text-white hover:bg-gray-700/50']">
          {{ cat || '全部' }}
        </button>
      </div>
      <div v-if="rankingsLoading" class="text-center py-8 text-gray-500">加载中...</div>
      <div v-else-if="!rankings.length" class="text-center py-8 text-gray-500">暂无评测数据，快去对比投票吧！</div>
      <div v-else class="space-y-1">
        <div v-for="(r, i) in rankings" :key="r.model_name" class="flex items-center gap-4 px-3 py-2 rounded-lg hover:bg-gray-700/30 transition-colors">
          <span class="w-7 h-7 flex items-center justify-center rounded-full text-xs font-bold bg-gray-700 text-gray-400" :class="{ 'bg-yellow-500/20 text-yellow-400': i === 0, 'bg-gray-300/20 text-gray-300': i === 1, 'bg-orange-500/20 text-orange-400': i === 2 }">{{ i + 1 }}</span>
          <span class="flex-1 text-sm text-white font-medium">{{ r.model_name }}</span>
          <span class="text-sm font-bold text-brand-400 w-16 text-right">{{ Math.round(r.elo) }}</span>
          <span class="text-xs text-gray-500 w-20 text-right">{{ r.wins }}W {{ r.losses }}L {{ r.ties }}T</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { Play, Zap } from 'lucide-vue-next'
import { arenaApi, type ArenaCompareResult, type EloRankingEntry } from '@/api/model-features'

const compareForm = ref({ prompt: '', model_a: 'openai-gpt4o', model_b: 'claude-sonnet', system_prompt: '', category: 'chat' })
const comparing = ref(false); const result = ref<ArenaCompareResult | null>(null)
const voted = ref(false); const currentComparisonId = ref('')

async function runCompare() {
  comparing.value = true; result.value = null; voted.value = false
  try { const res = await arenaApi.compare(compareForm.value); result.value = res.data; currentComparisonId.value = res.data.comparison_id } finally { comparing.value = false }
}

async function vote(winner: 'A' | 'B' | 'tie') { await arenaApi.vote(currentComparisonId.value, winner); voted.value = true; await fetchRankings() }

const rankings = ref<EloRankingEntry[]>([]); const rankingsLoading = ref(false); const rankCategory = ref('')
async function fetchRankings() { rankingsLoading.value = true; try { const res = await arenaApi.rankings(rankCategory.value || undefined); rankings.value = res.data.rankings } finally { rankingsLoading.value = false } }
onMounted(fetchRankings)
</script>
