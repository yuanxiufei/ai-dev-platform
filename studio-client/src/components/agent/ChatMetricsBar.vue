<script setup lang="ts">
/**
 * ChatMetricsBar.vue — RooCode TaskHeader 风格实时指标展示
 *
 * 参考 Roo Code TaskHeader.tsx 的 stat rows 模式：
 *   - ContextWindowProgress → 分段进度条
 *   - Token 用量 (↑输入 / ↓输出)
 *   - 成本估算 ($)
 *   - 耗时显示
 *   - 缓存命中
 *
 * 数据结构参考 RooCode 的 TaskHeader: table > tr > th + td 布局
 */
import { computed } from "vue"

const props = defineProps<{
  /** 输入 Token 数 */
  tokensIn?: number
  /** 输出 Token 数 */
  tokensOut?: number
  /** 总 Token 数 */
  tokensTotal?: number
  /** 上下文窗口大小 (模型支持的最大 Token) */
  contextWindow?: number
  /** 估算成本 (USD) */
  costUsd?: number
  /** 总耗时 (ms) */
  durationMs?: number
  /** 运行轮次 */
  turns?: number
  /** 最大轮次 */
  maxTurns?: number
  /** 工具调用成功数 */
  toolCallsSuccess?: number
  /** 工具调用总数 */
  toolCallsTotal?: number
  /** 当前阶段文本 */
  stageText?: string
}>()

// ── 格式化数字 (参考 RooCode formatLargeNumber) ──
const fmtNum = (n?: number): string => {
  if (n == null) return ""
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

// ── 格式化耗时 ──
const fmtDuration = computed(() => {
  if (props.durationMs == null) return ""
  const s = props.durationMs / 1000
  if (s < 60) return `${s.toFixed(1)}s`
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}m ${sec}s`
})

// ── 上下文使用百分比 ──
const contextPercent = computed(() => {
  if (!props.contextWindow || !props.tokensTotal) return 0
  return Math.min(100, (props.tokensTotal / props.contextWindow) * 100)
})

// ── 上下文用量颜色 (参考 RooCode ContextWindowProgress) ──
const contextColor = computed(() => {
  if (contextPercent.value > 90) return "bg-red-500"
  if (contextPercent.value > 70) return "bg-amber-500"
  if (contextPercent.value > 50) return "bg-yellow-500"
  return "bg-emerald-500"
})

// ── 工具成功率 ──
const toolSuccessRate = computed(() => {
  if (!props.toolCallsTotal || props.toolCallsTotal === 0) return null
  if (!props.toolCallsSuccess) return 0
  return Math.round((props.toolCallsSuccess / props.toolCallsTotal) * 100)
})
</script>

<template>
  <div
    v-if="tokensTotal || tokensIn || costUsd || durationMs || turns != null"
    class="metrics-bar px-3 py-2 bg-white/[0.02] border-b border-[var(--color-ide-border)] flex items-center gap-4 text-xs overflow-x-auto"
  >
    <!-- ── 上下文窗口进度条 (RooCode ContextWindowProgress) ── -->
    <div
      v-if="contextWindow && tokensTotal"
      class="flex items-center gap-1.5 shrink-0"
      :title="`${fmtNum(tokensTotal)} / ${fmtNum(contextWindow)} tokens`"
    >
      <span class="text-white/30">上下文</span>
      <div class="w-20 h-1.5 bg-white/10 rounded-full overflow-hidden">
        <div
          class="h-full rounded-full transition-all duration-500"
          :class="contextColor"
          :style="{ width: contextPercent + '%' }"
        />
      </div>
      <span class="text-[var(--color-ide-text)] tabular-nums">{{ fmtNum(tokensTotal) }}</span>
    </div>

    <!-- ── Token 用量 (↑ 输入 / ↓ 输出) ── -->
    <div v-if="tokensIn || tokensOut" class="flex items-center gap-2 shrink-0">
      <span class="text-white/30">Token</span>
      <span v-if="tokensIn" class="text-blue-400 tabular-nums">↑ {{ fmtNum(tokensIn) }}</span>
      <span v-if="tokensOut" class="text-emerald-400 tabular-nums">↓ {{ fmtNum(tokensOut) }}</span>
    </div>

    <!-- ── API 成本 ── -->
    <div v-if="costUsd != null" class="flex items-center gap-1 shrink-0">
      <span class="text-white/30">成本</span>
      <span class="text-amber-400 tabular-nums">${{ costUsd.toFixed(4) }}</span>
    </div>

    <!-- ── 耗时 ── -->
    <div v-if="fmtDuration" class="flex items-center gap-1 shrink-0">
      <span class="text-white/30">耗时</span>
      <span class="text-[var(--color-ide-text)] tabular-nums">{{ fmtDuration }}</span>
    </div>

    <!-- ── 轮次 ── -->
    <div v-if="turns != null" class="flex items-center gap-1 shrink-0">
      <span class="text-white/30">轮次</span>
      <span class="text-[var(--color-ide-text)] tabular-nums">{{ turns }}{{ maxTurns ? ` / ${maxTurns}` : "" }}</span>
    </div>

    <!-- ── 工具成功率 ── -->
    <div v-if="toolSuccessRate !== null" class="flex items-center gap-1 shrink-0">
      <span class="text-white/30">工具</span>
      <span
        class="tabular-nums"
        :class="toolSuccessRate >= 90 ? 'text-emerald-400' : toolSuccessRate >= 50 ? 'text-amber-400' : 'text-red-400'"
      >
        {{ toolSuccessRate }}%
      </span>
      <span class="text-white/30">({{ toolCallsSuccess }}/{{ toolCallsTotal }})</span>
    </div>

    <!-- Spacer -->
    <div class="flex-1" />

    <!-- ── 当前阶段 ── -->
    <span v-if="stageText" class="text-white/30 italic shrink-0">{{ stageText }}</span>
  </div>
</template>
