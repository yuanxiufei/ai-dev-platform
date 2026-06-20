<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { analyticsApi, type AnalyticsOverview, type ModelStats, type TrendPoint } from '@/api/model-features'
import { BarChart3, TrendingUp, Zap, DollarSign, Clock } from 'lucide-vue-next'

const period = ref(7); const loading = ref(false)
const overview = ref<AnalyticsOverview | null>(null)
const modelStats = ref<ModelStats[]>([])
const trends = ref<TrendPoint[]>([])

async function fetchAll() {
  loading.value = true
  try {
    const [ov, byM, tr] = await Promise.all([
      analyticsApi.overview(period.value),
      analyticsApi.byModel(period.value),
      analyticsApi.trends(period.value, 'day'),
    ])
    overview.value = ov.data; modelStats.value = byM.data.models || []; trends.value = tr.data.trends || []
  } finally { loading.value = false }
}

function barWidth(calls: number) { const max = Math.max(...trends.value.map(t => t.calls), 1); return (calls / max) * 100 }

onMounted(fetchAll)
</script>

<template>
  <div class="p-6 max-w-5xl mx-auto space-y-6">
    <header class="flex items-center justify-between">
      <div>
        <h1 class="text-3xl font-bold text-white">使用分析</h1>
        <p class="text-gray-400 mt-2">Token · 延迟 · 成本实时监控</p>
      </div>
      <div class="flex gap-2">
        <button v-for="d in [1, 7, 30]" :key="d" @click="period = d; fetchAll()"
          :class="['px-3 py-1.5 rounded-xl text-sm transition-colors', period === d ? 'bg-brand-500/15 text-brand-400' : 'text-gray-400 hover:text-white hover:bg-gray-800']">{{ d === 1 ? '今天' : d === 7 ? '7天' : '30天' }}</button>
      </div>
    </header>

    <div v-if="loading" class="text-center py-16 text-gray-500">加载中...</div>
    <template v-else>
      <div class="grid grid-cols-2 md:grid-cols-5 gap-4">
        <div class="p-4 rounded-2xl bg-gray-900/50 border border-gray-800/50 text-center">
          <Zap class="w-4 h-4 text-brand-400 mx-auto mb-2" />
          <span class="text-2xl font-bold text-white block">{{ overview?.total_calls?.toLocaleString() || 0 }}</span>
          <span class="text-xs text-gray-500">总调用</span>
        </div>
        <div class="p-4 rounded-2xl bg-gray-900/50 border border-gray-800/50 text-center">
          <TrendingUp class="w-4 h-4 text-green-400 mx-auto mb-2" />
          <span class="text-2xl font-bold text-green-400 block">{{ overview?.success_rate || 0 }}%</span>
          <span class="text-xs text-gray-500">成功率</span>
        </div>
        <div class="p-4 rounded-2xl bg-gray-900/50 border border-gray-800/50 text-center">
          <BarChart3 class="w-4 h-4 text-brand-400 mx-auto mb-2" />
          <span class="text-2xl font-bold text-brand-400 block">{{ (overview?.total_tokens || 0)?.toLocaleString() }}</span>
          <span class="text-xs text-gray-500">总 Token</span>
        </div>
        <div class="p-4 rounded-2xl bg-gray-900/50 border border-gray-800/50 text-center">
          <DollarSign class="w-4 h-4 text-yellow-400 mx-auto mb-2" />
          <span class="text-2xl font-bold text-yellow-400 block">${{ (overview?.estimated_cost_usd || 0)?.toFixed(4) }}</span>
          <span class="text-xs text-gray-500">估算成本</span>
        </div>
        <div class="p-4 rounded-2xl bg-gray-900/50 border border-gray-800/50 text-center">
          <Clock class="w-4 h-4 text-purple-400 mx-auto mb-2" />
          <span class="text-2xl font-bold text-white block">{{ (overview?.avg_latency_ms || 0)?.toFixed(0) }}ms</span>
          <span class="text-xs text-gray-500">平均延迟</span>
        </div>
      </div>

      <div v-if="modelStats.length" class="bg-gray-900/50 rounded-2xl p-6 border border-gray-800/50">
        <h2 class="font-semibold text-white mb-4">各模型统计</h2>
        <div class="overflow-x-auto">
          <table class="w-full text-sm">
            <thead>
              <tr class="border-b border-gray-800">
                <th class="text-left text-gray-500 font-medium py-2 px-3">模型</th>
                <th class="text-left text-gray-500 font-medium py-2 px-3">调用</th>
                <th class="text-left text-gray-500 font-medium py-2 px-3">Token</th>
                <th class="text-left text-gray-500 font-medium py-2 px-3">延迟</th>
                <th class="text-left text-gray-500 font-medium py-2 px-3">成本</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="m in modelStats" :key="m.model_name" class="border-b border-gray-800/30">
                <td class="py-2 px-3 text-white font-medium">{{ m.model_name }}</td>
                <td class="py-2 px-3 text-gray-400">{{ m.calls }}</td>
                <td class="py-2 px-3 text-gray-400">{{ m.total_tokens?.toLocaleString() }}</td>
                <td class="py-2 px-3 text-gray-400">{{ m.avg_latency_ms?.toFixed(0) }}ms</td>
                <td class="py-2 px-3 text-yellow-400">${{ m.total_cost_usd?.toFixed(4) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div v-if="trends.length" class="bg-gray-900/50 rounded-2xl p-6 border border-gray-800/50">
        <h2 class="font-semibold text-white mb-4">使用趋势</h2>
        <div class="space-y-2">
          <div v-for="t in trends" :key="t.time" class="flex items-center gap-3">
            <div class="w-16 text-xs text-gray-500 shrink-0">{{ t.time.slice(5, 10) }}</div>
            <div class="flex-1 h-5 bg-gray-800 rounded-full overflow-hidden">
              <div class="h-full rounded-full bg-brand-500/60 transition-all" :style="{ width: barWidth(t.calls) + '%' }" />
            </div>
            <div class="w-10 text-xs text-gray-400 text-right shrink-0">{{ t.calls }}</div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
