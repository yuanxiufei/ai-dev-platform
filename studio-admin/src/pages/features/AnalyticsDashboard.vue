<template>
  <div class="p-6 max-w-7xl mx-auto">
    <header class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-white">模型分析看板</h1>
        <p class="text-gray-400 mt-1 text-sm">借鉴 Open WebUI Dashboard — Token / 延迟 / 成本实时监控</p>
      </div>
      <div class="flex gap-2">
        <button v-for="d in [1, 7, 30, 90]" :key="d" @click="period = d; fetchAll()"
          :class="['px-3 py-1 rounded-lg text-sm transition-colors', period === d ? 'bg-brand-500/15 text-brand-400' : 'text-gray-400 hover:text-white hover:bg-gray-700/50']">
          {{ d === 1 ? '今天' : d === 7 ? '7天' : d === 30 ? '30天' : '90天' }}
        </button>
      </div>
    </header>

    <div v-if="loading" class="text-center py-16 text-gray-500">加载中...</div>
    <template v-else>
      <!-- 总览卡片 -->
      <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
        <div class="p-4 rounded-xl bg-gray-800/50 border border-gray-700/50 text-center">
          <span class="block text-xs text-gray-500 mb-1">总调用次数</span>
          <span class="text-xl font-bold text-white">{{ overview?.total_calls?.toLocaleString() || 0 }}</span>
        </div>
        <div class="p-4 rounded-xl bg-gray-800/50 border border-gray-700/50 text-center">
          <span class="block text-xs text-gray-500 mb-1">成功率</span>
          <span class="text-xl font-bold text-green-400">{{ overview?.success_rate || 0 }}%</span>
        </div>
        <div class="p-4 rounded-xl bg-gray-800/50 border border-gray-700/50 text-center">
          <span class="block text-xs text-gray-500 mb-1">总 Token</span>
          <span class="text-xl font-bold text-brand-400">{{ (overview?.total_tokens || 0)?.toLocaleString() }}</span>
        </div>
        <div class="p-4 rounded-xl bg-gray-800/50 border border-gray-700/50 text-center">
          <span class="block text-xs text-gray-500 mb-1">估算成本</span>
          <span class="text-xl font-bold text-yellow-400">${{ (overview?.estimated_cost_usd || 0)?.toFixed(4) }}</span>
        </div>
        <div class="p-4 rounded-xl bg-gray-800/50 border border-gray-700/50 text-center">
          <span class="block text-xs text-gray-500 mb-1">平均延迟</span>
          <span class="text-xl font-bold text-white">{{ (overview?.avg_latency_ms || 0)?.toFixed(0) }}ms</span>
        </div>
      </div>

      <!-- 按模型统计 -->
      <div class="mb-6 p-5 rounded-xl bg-gray-800/50 border border-gray-700/50">
        <h2 class="text-lg font-bold text-white mb-3">各模型统计</h2>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr>
                <th class="text-left text-gray-500 font-medium py-2 px-3 border-b border-gray-700/50">模型</th>
                <th class="text-left text-gray-500 font-medium py-2 px-3 border-b border-gray-700/50">Provider</th>
                <th class="text-left text-gray-500 font-medium py-2 px-3 border-b border-gray-700/50">调用次数</th>
                <th class="text-left text-gray-500 font-medium py-2 px-3 border-b border-gray-700/50">Token</th>
                <th class="text-left text-gray-500 font-medium py-2 px-3 border-b border-gray-700/50">平均延迟</th>
                <th class="text-left text-gray-500 font-medium py-2 px-3 border-b border-gray-700/50">成本</th>
                <th class="text-left text-gray-500 font-medium py-2 px-3 border-b border-gray-700/50">成功率</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in modelStats" :key="m.model_name">
                <td class="py-2 px-3 text-white font-medium border-b border-gray-700/30">{{ m.model_name }}</td>
                <td class="py-2 px-3 text-gray-400 border-b border-gray-700/30">{{ m.provider }}</td>
                <td class="py-2 px-3 text-gray-400 border-b border-gray-700/30">{{ m.calls }}</td>
                <td class="py-2 px-3 text-gray-400 border-b border-gray-700/30">{{ m.total_tokens?.toLocaleString() }}</td>
                <td class="py-2 px-3 text-gray-400 border-b border-gray-700/30">{{ m.avg_latency_ms?.toFixed(0) }}ms</td>
                <td class="py-2 px-3 text-yellow-400 border-b border-gray-700/30">${{ m.total_cost_usd?.toFixed(4) }}</td>
                <td class="py-2 px-3 border-b border-gray-700/30">
                  <span :class="m.success_rate >= 95 ? 'text-green-400' : 'text-orange-400'">{{ m.success_rate }}%</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 使用趋势 -->
      <div class="p-5 rounded-xl bg-gray-800/50 border border-gray-700/50">
        <div class="flex justify-between items-center mb-3">
          <h2 class="text-lg font-bold text-white">使用趋势</h2>
          <div class="flex gap-2">
            <button v-for="g in ['day', 'hour']" :key="g" @click="granularity = g; fetchTrends()"
              :class="['px-3 py-1 rounded-lg text-sm transition-colors', granularity === g ? 'bg-brand-500/15 text-brand-400' : 'text-gray-400 hover:text-white hover:bg-gray-700/50']">
              {{ g === 'day' ? '按天' : '按小时' }}
            </button>
          </div>
        </div>
        <div v-if="!trends.length" class="text-center py-8 text-gray-500">暂无数据</div>
        <div v-else class="space-y-2">
          <div v-for="t in trends" :key="t.time" class="flex items-center gap-3">
            <div class="w-12 text-xs text-gray-500 shrink-0">{{ formatTime(t.time) }}</div>
            <div class="flex-1 h-5 bg-gray-800 rounded-full overflow-hidden">
              <div class="h-full rounded-full bg-brand-500/60 transition-all duration-300" :style="{ width: barWidth(t.calls) + '%', minWidth: '2px' }"></div>
            </div>
            <div class="w-10 text-xs text-gray-400 text-right shrink-0">{{ t.calls }}</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { analyticsApi, type AnalyticsOverview, type ModelStats, type TrendPoint } from '@/api/model-features'

const period = ref(7); const granularity = ref('day'); const loading = ref(false)
const overview = ref<AnalyticsOverview | null>(null); const modelStats = ref<ModelStats[]>([]); const trends = ref<TrendPoint[]>([])

async function fetchAll() {
  loading.value = true
  try {
    const [ov, byM, tr] = await Promise.all([analyticsApi.overview(period.value), analyticsApi.byModel(period.value), analyticsApi.trends(period.value, granularity.value as 'hour' | 'day')])
    overview.value = ov.data; modelStats.value = byM.data.models || []; trends.value = tr.data.trends || []
  } finally { loading.value = false }
}

function formatTime(t: string) { return granularity.value === 'hour' ? t.slice(11, 16) : t.slice(5, 10) }
function barWidth(calls: number) { const max = Math.max(...trends.value.map(t => t.calls), 1); return (calls / max) * 100 }
async function fetchTrends() { const res = await analyticsApi.trends(period.value, granularity.value as 'hour' | 'day'); trends.value = res.data.trends || [] }
onMounted(fetchAll)
</script>
