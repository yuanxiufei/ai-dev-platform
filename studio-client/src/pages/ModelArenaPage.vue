<template>
  <div class="arena-page">
    <header class="page-header">
      <div><Swords class="h-5 w-5" /><h2>模型竞技场</h2></div>
      <div class="header-tabs">
        <button :class="['tab', { active: tab === 'compare' }]" @click="tab = 'compare'"><Zap class="h-3.5 w-3.5" /> 对比</button>
        <button :class="['tab', { active: tab === 'rankings' }]" @click="tab = 'rankings'"><Trophy class="h-3.5 w-3.5" /> 排行榜</button>
        <button :class="['tab', { active: tab === 'history' }]" @click="tab = 'history'"><History class="h-3.5 w-3.5" /> 历史</button>
      </div>
    </header>

    <!-- Tab 1: 对比 -->
    <div v-if="tab === 'compare'" class="compare-section">
      <div class="compare-input">
        <textarea v-model="prompt" placeholder="输入测试 Prompt..." rows="4" class="prompt-input"></textarea>
        <div class="model-tags">
          <span v-for="m in availableModels" :key="m" :class="['tag', { selected: selectedModels.includes(m) }]" @click="toggleModel(m)">{{ m }}</span>
          <input v-model="customModel" @keydown.enter.prevent="addCustomModel" placeholder="+ 自定义模型" class="tag-input" />
        </div>
        <button class="btn btn-primary" @click="runCompare" :disabled="!prompt || selectedModels.length < 2 || comparing">
          <Play class="h-4 w-4" /> {{ comparing ? '对比中...' : '开始对比' }}
        </button>
      </div>

      <div v-if="results.length" class="results-grid">
        <div v-for="r in results" :key="r.model" class="result-card">
          <div class="card-header">
            <span class="model-name">{{ r.model }}</span>
            <span class="latency">{{ r.latency_ms }}ms | {{ r.tokens }} tokens</span>
          </div>
          <div class="card-output">{{ r.output }}</div>
          <button class="btn btn-sm btn-ghost" @click="voteWinner(r.model)"><ThumbsUp class="h-3.5 w-3.5" /> 选为最佳</button>
        </div>
      </div>
    </div>

    <!-- Tab 2: 排行榜 -->
    <div v-if="tab === 'rankings'" class="rankings-section">
      <div class="rankings-header">
        <select v-model="rankCategory" class="input-sm">
          <option value="">全部分类</option>
          <option value="coding">编程</option>
          <option value="creative">创意</option>
          <option value="reasoning">推理</option>
        </select>
        <button class="btn btn-sm btn-ghost" @click="loadRankings"><RefreshCw class="h-3.5 w-3.5" /> 刷新</button>
      </div>
      <table class="ranking-table" v-if="rankings.length">
        <thead><tr><th>#</th><th>模型</th><th>ELO</th><th>胜率</th><th>场次</th><th>胜/平/负</th></tr></thead>
        <tbody>
          <tr v-for="(r, i) in rankings" :key="r.model" :class="{ top3: i < 3 }">
            <td><span class="rank-badge" :class="`rank-${i + 1}`">{{ i + 1 }}</span></td>
            <td class="model-cell">{{ r.model }}</td>
            <td class="elo">{{ r.elo }}</td>
            <td>{{ (r.win_rate * 100).toFixed(1) }}%</td>
            <td>{{ r.total_games }}</td>
            <td>{{ r.wins }}/{{ r.draws }}/{{ r.losses }}</td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty-hint">暂无排行数据</div>
    </div>

    <!-- Tab 3: 历史 -->
    <div v-if="tab === 'history'" class="history-section">
      <div v-if="historyItems.length" class="history-list">
        <div v-for="item in historyItems" :key="item.id" class="history-card">
          <div class="hc-top">
            <span class="hc-prompt">{{ item.prompt.slice(0, 80) }}{{ item.prompt.length > 80 ? '...' : '' }}</span>
            <span class="hc-date">{{ item.created_at }}</span>
          </div>
          <div class="hc-models">
            <span v-for="m in item.models" :key="m" :class="['hc-model', { winner: m === item.winner }]">{{ m }}{{ m === item.winner ? ' 🏆' : '' }}</span>
          </div>
        </div>
      </div>
      <div v-else class="empty-hint">暂无对战历史</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import { Swords, Zap, Trophy, History, Play, ThumbsUp, RefreshCw } from "lucide-vue-next"
import { arenaCompare, arenaVote, arenaRankings, arenaHistory, ArenaModelResult, EloRanking, ArenaHistoryItem } from "@/api/modelArena"

const tab = ref<"compare" | "rankings" | "history">("compare")
const prompt = ref("")
const availableModels = ["gpt-4", "claude-3-opus", "gemini-pro", "deepseek-v3", "qwen-max", "llama-3-70b"]
const selectedModels = ref<string[]>(["gpt-4", "claude-3-opus"])
const customModel = ref("")
const comparing = ref(false)
const results = ref<ArenaModelResult[]>([])
const rankCategory = ref("")
const rankings = ref<EloRanking[]>([])
const historyItems = ref<ArenaHistoryItem[]>([])

function toggleModel(m: string) {
  const i = selectedModels.value.indexOf(m)
  if (i >= 0) selectedModels.value.splice(i, 1)
  else if (selectedModels.value.length < 5) selectedModels.value.push(m)
}
function addCustomModel() {
  const m = customModel.value.trim()
  if (m && !selectedModels.value.includes(m)) selectedModels.value.push(m)
  customModel.value = ""
}

async function runCompare() {
  comparing.value = true
  results.value = []
  try {
    const resp = await arenaCompare({ prompt: prompt.value, models: selectedModels.value, category: rankCategory.value || undefined })
    results.value = resp.data.results
  } catch (e: unknown) { console.error(e) }
  finally { comparing.value = false }
}

async function voteWinner(model: string) {
  try {
    await arenaVote({ comparison_id: "", winner: model })
    alert("投票成功！")
  } catch (e: unknown) { console.error(e) }
}

async function loadRankings() {
  try {
    const resp = await arenaRankings(rankCategory.value || undefined)
    rankings.value = resp.data.rankings
  } catch (e: unknown) { console.error(e) }
}

async function loadHistory() {
  try {
    const resp = await arenaHistory({ category: rankCategory.value || undefined })
    historyItems.value = resp.data.data || []
  } catch (e: unknown) { console.error(e) }
}

onMounted(() => { loadRankings(); loadHistory() })
</script>

<style scoped>
.arena-page { padding: 20px; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; }
.page-header > div { display: flex; align-items: center; gap: 8px; }
.page-header h2 { font-size: 18px; margin: 0; }
.header-tabs { display: flex; gap: 4px; background: var(--color-ide-surface); border-radius: 8px; padding: 3px; }
.tab { display: inline-flex; align-items: center; gap: 4px; padding: 6px 14px; border: none; border-radius: 6px; font-size: 13px; cursor: pointer; background: transparent; color: var(--color-ide-text-secondary); }
.tab.active { background: var(--color-ide-accent); color: #fff; }

.compare-input { display: flex; flex-direction: column; gap: 12px; margin-bottom: 20px; }
.prompt-input { width: 100%; box-sizing: border-box; border: 1px solid var(--color-ide-border); border-radius: 8px; padding: 10px 14px; font-size: 14px; background: var(--color-ide-bg); color: var(--color-ide-text); resize: vertical; outline: none; }
.prompt-input:focus { border-color: var(--color-ide-accent); }
.model-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.tag { padding: 4px 10px; border-radius: 99px; font-size: 12px; border: 1px solid var(--color-ide-border); cursor: pointer; color: var(--color-ide-text-secondary); }
.tag.selected { background: var(--color-ide-accent); color: #fff; border-color: var(--color-ide-accent); }
.tag-input { border: 1px dashed var(--color-ide-border); border-radius: 99px; padding: 4px 10px; font-size: 12px; background: transparent; color: var(--color-ide-text); outline: none; width: 120px; }

.results-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 16px; }
.result-card { background: var(--color-ide-bg); border: 1px solid var(--color-ide-border); border-radius: 10px; padding: 14px; }
.card-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
.model-name { font-weight: 600; font-size: 14px; }
.latency { font-size: 12px; color: var(--color-ide-text-secondary); }
.card-output { font-size: 13px; line-height: 1.6; white-space: pre-wrap; max-height: 200px; overflow-y: auto; margin-bottom: 8px; }

.rankings-header { display: flex; gap: 8px; margin-bottom: 16px; }
.ranking-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.ranking-table th { text-align: left; padding: 8px 12px; border-bottom: 2px solid var(--color-ide-border); color: var(--color-ide-text-secondary); font-weight: 500; }
.ranking-table td { padding: 10px 12px; border-bottom: 1px solid var(--color-ide-border); }
.rank-badge { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 6px; font-size: 12px; font-weight: 700; }
.rank-1 { background: #fbbf24; color: #000; }
.rank-2 { background: #94a3b8; color: #fff; }
.rank-3 { background: #d97706; color: #fff; }
.elo { font-weight: 700; font-variant-numeric: tabular-nums; }
.tr.top3 { background: rgba(251, 191, 36, .04); }
.model-cell { font-weight: 500; }

.history-list { display: flex; flex-direction: column; gap: 8px; }
.history-card { padding: 12px; border: 1px solid var(--color-ide-border); border-radius: 8px; background: var(--color-ide-bg); }
.hc-top { display: flex; justify-content: space-between; margin-bottom: 6px; }
.hc-prompt { font-size: 13px; }
.hc-date { font-size: 11px; color: var(--color-ide-text-secondary); }
.hc-models { display: flex; gap: 8px; }
.hc-model { font-size: 12px; padding: 2px 8px; border-radius: 4px; background: var(--color-ide-surface); }
.hc-model.winner { background: #fbbf24; color: #000; font-weight: 600; }

.input-sm { font-size: 12px; padding: 4px 8px; border: 1px solid var(--color-ide-border); border-radius: 6px; background: var(--color-ide-surface); color: var(--color-ide-text); }
.empty-hint { text-align: center; padding: 40px; color: var(--color-ide-text-secondary); }

.btn { display: inline-flex; align-items: center; gap: 4px; border: none; cursor: pointer; border-radius: 8px; font-size: 13px; padding: 8px 14px; }
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.btn-ghost { background: transparent; color: var(--color-ide-text-secondary); }
.btn-ghost:hover { background: var(--color-ide-surface); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
</style>
