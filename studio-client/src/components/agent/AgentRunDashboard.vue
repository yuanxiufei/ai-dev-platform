<script setup lang="ts">
/**
 * AgentRunDashboard.vue — Agent 实时执行仪表盘
 *
 * 参考项目：Open Interpreter (streaming output), Cline (execution trace), Roo Code (tool panel)
 *
 * 功能：
 *   - 轮次级详情：每轮的工具调用、推理步骤、最终输出
 *   - 实时执行轨迹：开始时间、耗时、令牌消耗
 *   - 工具执行状态：成功/失败/审批中
 *   - 性能指标：总延迟、每轮耗时、模型信息
 */
import {
  Brain,
  CheckCircle2,
  Clock,
  Cpu,
  Loader2,
  Timer,
  Wrench,
  XCircle,
  Zap,
} from "lucide-vue-next"
import { computed, ref } from "vue"
import type { ChatMessage, ToolCallRecord } from "@/types/studio"

const props = defineProps<{
  /** 所有消息 */
  messages: ChatMessage[]
  /** 是否正在执行 */
  isStreaming?: boolean
  /** 当前轮次 */
  currentTurn?: number
  /** 最大轮次 */
  maxTurns?: number
  /** 总延迟 (ms) */
  totalLatencyMs?: number
  /** 使用的模型 */
  modelUsed?: string
}>()

// ── 轮次分组 ──
interface TurnDetail {
  turn: number
  toolCalls: ToolCallRecord[]
  reasoningSteps: { content: string; status: string }[]
  finalOutput: string
  startTime?: string
  latencyMs?: number
}

const turns = computed<TurnDetail[]>(() => {
  const result: TurnDetail[] = []
  let currentTurnNum = 0

  for (const msg of props.messages) {
    if (msg.role === "user") {
      currentTurnNum++
      result.push({
        turn: currentTurnNum,
        toolCalls: [],
        reasoningSteps: [],
        finalOutput: "",
      })
    } else if (msg.role === "assistant" && result.length > 0) {
      const current = result[result.length - 1]
      if (msg.tool_calls?.length) {
        current.toolCalls.push(...msg.tool_calls)
      }
      if (msg.reasoning_steps?.length) {
        current.reasoningSteps.push(
          ...msg.reasoning_steps.map(s => ({
            content: s.content,
            status: s.status,
          }))
        )
      }
      if (msg.content) {
        current.finalOutput = msg.content
      }
      if (msg.metadata?.latency_ms) {
        current.latencyMs = msg.metadata.latency_ms as number
      }
    }
  }

  return result
})

// ── 统计 ──
const stats = computed(() => {
  const allToolCalls = turns.value.flatMap(t => t.toolCalls)
  const successful = allToolCalls.filter(t => t.success === true).length
  const failed = allToolCalls.filter(t => t.success === false).length
  const pending = allToolCalls.filter(t => t.success === undefined).length
  return {
    totalTurns: turns.value.length,
    totalToolCalls: allToolCalls.length,
    successful,
    failed,
    pending,
  }
})

// ── 选中轮次 ──
const selectedTurn = ref<number | null>(null)

function toggleTurn(turn: number) {
  selectedTurn.value = selectedTurn.value === turn ? null : turn
}
</script>

<template>
  <div class="run-dashboard rounded-xl border border-[var(--color-ide-border)] bg-white/[0.01] overflow-hidden">
    <!-- 头部概览 -->
    <div class="grid grid-cols-4 divide-x divide-white/[0.04] border-b border-white/[0.04]">
      <!-- 轮次 -->
      <div class="flex flex-col items-center justify-center py-3 px-2">
        <span class="text-[10px] text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-1">轮次</span>
        <span class="text-lg font-bold text-white tabular-nums">
          <span v-if="currentTurn">{{ currentTurn }}</span>
          <span v-else>0</span>
        </span>
        <span class="text-[10px] text-[var(--color-ide-text-dim)]">/ {{ maxTurns || '?' }}</span>
      </div>

      <!-- 工具调用 -->
      <div class="flex flex-col items-center justify-center py-3 px-2">
        <span class="text-[10px] text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-1">工具</span>
        <span class="text-lg font-bold tabular-nums" :class="stats.failed > 0 ? 'text-amber-400' : 'text-emerald-400'">
          {{ stats.successful }}
        </span>
        <span class="text-[10px] text-[var(--color-ide-text-dim)]">
          <span v-if="stats.failed > 0" class="text-red-400">{{ stats.failed }} 失败</span>
          <span v-else>{{ stats.totalToolCalls }} 次调用</span>
        </span>
      </div>

      <!-- 延迟 -->
      <div class="flex flex-col items-center justify-center py-3 px-2">
        <span class="text-[10px] text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-1">延迟</span>
        <span class="text-lg font-bold text-white tabular-nums">
          {{ totalLatencyMs ? (totalLatencyMs / 1000).toFixed(1) : '--' }}
        </span>
        <span class="text-[10px] text-[var(--color-ide-text-dim)]">{{ totalLatencyMs ? totalLatencyMs + 'ms' : '等待中' }}</span>
      </div>

      <!-- 模型 -->
      <div class="flex flex-col items-center justify-center py-3 px-2">
        <span class="text-[10px] text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-1">模型</span>
        <div class="flex items-center gap-1">
          <Cpu class="w-3.5 h-3.5 text-brand-400" />
          <span class="text-xs font-mono text-[var(--color-ide-text)] truncate max-w-[80px]">
            {{ modelUsed || '--' }}
          </span>
        </div>
        <span class="text-[10px] text-[var(--color-ide-text-dim)]">Agent Runtime</span>
      </div>
    </div>

    <!-- 实时进度条 -->
    <div v-if="isStreaming" class="px-4 py-2 bg-brand-500/[0.03] border-b border-white/[0.04]">
      <div class="flex items-center gap-2 text-[10px] text-brand-400 mb-1">
        <Loader2 class="w-3 h-3 animate-spin" />
        第 {{ currentTurn || 1 }} 轮执行中...
      </div>
      <div class="h-1 rounded-full bg-[var(--color-ide-surface-hover)] overflow-hidden">
        <div
          class="h-full rounded-full bg-gradient-to-r from-brand-500 to-purple-500 animate-pulse transition-all duration-500"
          :style="{ width: `${((currentTurn || 1) / (maxTurns || 3)) * 100}%` }"
        />
      </div>
    </div>

    <!-- 轮次详情列表 -->
    <div class="max-h-80 overflow-y-auto custom-scroll">
      <div v-if="turns.length === 0" class="flex flex-col items-center justify-center py-12 text-gray-700">
        <Zap class="w-8 h-8 mb-2 opacity-20" />
        <p class="text-xs">等待 Agent 开始执行...</p>
        <p class="text-[10px] text-gray-700 mt-1">发送消息触发 Agent 运行</p>
      </div>

      <div
        v-for="turn in turns"
        :key="turn.turn"
        class="border-b border-white/[0.03] last:border-0"
      >
        <!-- 轮次头部 -->
        <button
          @click="toggleTurn(turn.turn)"
          class="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-white/[0.02] transition-colors cursor-pointer"
        >
          <div
            class="w-6 h-6 rounded-md flex items-center justify-center text-[11px] font-bold shrink-0"
            :class="turn.finalOutput ? 'bg-emerald-500/15 text-emerald-400' : 'bg-white/[0.03] text-[var(--color-ide-text-dim)]'"
          >
            {{ turn.turn }}
          </div>

          <div class="flex-1 min-w-0 text-left">
            <div class="flex items-center gap-2">
              <span class="text-xs font-medium text-[var(--color-ide-text)] truncate">
                {{ turn.toolCalls.length > 0
                  ? `${turn.toolCalls.length} 次工具调用`
                  : turn.finalOutput
                    ? turn.finalOutput.slice(0, 60)
                    : '处理中...' }}
              </span>
            </div>
            <div class="flex items-center gap-2 mt-0.5">
              <div class="flex items-center gap-1">
                <Wrench class="w-2.5 h-2.5 text-[var(--color-ide-text-dim)]" />
                <span class="text-[10px] text-[var(--color-ide-text-dim)]">{{ turn.toolCalls.length }} tools</span>
              </div>
              <div v-if="turn.latencyMs" class="flex items-center gap-1">
                <Timer class="w-2.5 h-2.5 text-[var(--color-ide-text-dim)]" />
                <span class="text-[10px] text-[var(--color-ide-text-dim)]">{{ turn.latencyMs }}ms</span>
              </div>
            </div>
          </div>

          <span class="text-[var(--color-ide-text-dim)] text-xs transition-transform duration-200" :class="{ 'rotate-180': selectedTurn === turn.turn }">▾</span>
        </button>

        <!-- 轮次详情展开 -->
        <div v-if="selectedTurn === turn.turn" class="px-4 pb-3 space-y-2 border-t border-white/[0.03]">
          <!-- 推理步骤 -->
          <div v-if="turn.reasoningSteps.length > 0" class="pt-2">
            <p class="text-[10px] font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-1">推理过程</p>
            <div class="space-y-1">
              <div
                v-for="(step, si) in turn.reasoningSteps"
                :key="si"
                class="flex items-start gap-1.5 text-[10px] text-[var(--color-ide-text-dim)]"
              >
                <Brain class="w-3 h-3 text-brand-500/50 mt-0.5 shrink-0" />
                <span class="leading-relaxed">{{ step.content.slice(0, 120) }}{{ step.content.length > 120 ? '...' : '' }}</span>
              </div>
            </div>
          </div>

          <!-- 工具调用 -->
          <div v-if="turn.toolCalls.length > 0">
            <p class="text-[10px] font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-1">工具调用</p>
            <div class="space-y-1">
              <div
                v-for="tc in turn.toolCalls"
                :key="tc.id"
                class="flex items-center gap-2 px-2 py-1.5 rounded-md text-[11px]"
                :class="tc.success === true ? 'bg-emerald-500/[0.04]' : tc.success === false ? 'bg-red-500/[0.04]' : 'bg-white/[0.02]'"
              >
                <component
                  :is="tc.success === true ? CheckCircle2 : tc.success === false ? XCircle : Loader2"
                  :class="[
                    'w-3.5 h-3.5 shrink-0',
                    tc.success === true ? 'text-emerald-400' :
                    tc.success === false ? 'text-red-400' :
                    'text-brand-400 animate-spin'
                  ]"
                />
                <span class="font-mono text-[var(--color-ide-text)] truncate flex-1">{{ tc.name }}</span>
                <span v-if="tc.result" class="text-[10px] text-[var(--color-ide-text-dim)] truncate max-w-[100px]">
                  {{ typeof tc.result === 'string' ? tc.result.slice(0, 40) : JSON.stringify(tc.result).slice(0, 40) }}
                </span>
                <span v-if="tc.security_level" class="text-[9px] px-1 rounded" :class="
                  tc.security_level === 'UNSAFE' ? 'bg-red-500/10 text-red-400' :
                  tc.security_level === 'SYSTEM' ? 'bg-amber-500/10 text-amber-400' :
                  'bg-gray-500/10 text-[var(--color-ide-text-dim)]'
                ">{{ tc.security_level }}</span>
              </div>
            </div>
          </div>

          <!-- 最终输出摘要 -->
          <div v-if="turn.finalOutput" class="pt-1">
            <p class="text-[10px] font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-1">输出</p>
            <p class="text-xs text-[var(--color-ide-text-dim)] leading-relaxed line-clamp-3">
              {{ turn.finalOutput.slice(0, 200) }}{{ turn.finalOutput.length > 200 ? '...' : '' }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scroll::-webkit-scrollbar { width: 3px; }
.custom-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,.06); border-radius: 9999px; }

.line-clamp-3 {
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
