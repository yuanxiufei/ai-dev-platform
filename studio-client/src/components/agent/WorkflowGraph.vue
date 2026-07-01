<script setup lang="ts">
/**
 * WorkflowGraph.vue — Agent 编排管线可视化
 *
 * 参考项目：LangGraph (StateGraph 可视化), AutoGen (Agent 角色图)
 *
 * 功能：
 *   1. DAG 图展示 Planner → Coder → Reviewer 流水线
 *   2. 节点状态动画（pending → in_progress → completed → error）
 *   3. 节点间连线 + 数据流标注
 *   4. 每个节点显示：Agent名、工具调用数、输出摘要
 *   5. 整体进度条 + 耗时统计
 */
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  Code2,
  Eye,
  Loader2,
  MessageSquare,
  Search,
  XCircle,
  Zap,
} from "lucide-vue-next"
import { computed, ref } from "vue"
import type { PipelineStage, ToolCallRecord } from "@/types/studio"

const props = defineProps<{
  stages: PipelineStage[]
  isRunning?: boolean
  totalTurns?: number
  currentTurn?: number
  totalLatencyMs?: number
}>()

const emit = defineEmits<{
  (e: "stageClick", stage: PipelineStage): void
}>()

// ═══════════════════ 节点样式映射 ═══════════════════
const AGENT_STYLES: Record<string, {
  icon: typeof Code2
  color: string
  bg: string
  label: string
}> = {
  Planner: { icon: Search, color: "#f59e0b", bg: "rgba(245,158,11,0.08)", label: "Planner" },
  Coder:   { icon: Code2,  color: "#6366f1", bg: "rgba(99,102,241,0.08)",  label: "Coder" },
  Reviewer:{ icon: Eye,    color: "#a78bfa", bg: "rgba(167,139,250,0.08)", label: "Reviewer" },
  Tester:  { icon: Zap,    color: "#22d3ee", bg: "rgba(34,211,238,0.08)",  label: "Tester" },
  Default: { icon: MessageSquare, color: "#8b8b8b", bg: "rgba(139,139,139,0.08)", label: "Agent" },
}

function agentStyle(name: string) {
  return AGENT_STYLES[name] || AGENT_STYLES.Default
}

// ═══════════════════ 统计 ═══════════════════
const stats = computed(() => {
  const total = props.stages.length
  const completed = props.stages.filter(s => s.status === "completed").length
  const inProgress = props.stages.filter(s => s.status === "in_progress").length
  const errors = props.stages.filter(s => s.status === "error").length
  const progress = total > 0 ? Math.round(((completed + errors) / total) * 100) : 0
  return { total, completed, inProgress, errors, progress }
})

// 格式化耗时
function formatLatency(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

// 阶段耗时
function stageDuration(stage: PipelineStage): string {
  if (!stage.tool_calls?.length) return ""
  const total = stage.tool_calls.reduce((sum, t) => sum + (t.latency_ms || 0), 0)
  return formatLatency(total)
}
</script>

<template>
  <div v-if="stages.length > 0" class="workflow-graph rounded-xl border border-[var(--color-ide-border)] bg-white/[0.01] overflow-hidden">
    <!-- 头部进度 -->
    <div class="px-4 py-3 border-b border-white/[0.04] bg-white/[0.02]">
      <div class="flex items-center gap-3 mb-2">
        <Zap class="w-4 h-4 text-brand-400" />
        <span class="text-sm font-semibold text-[var(--color-ide-text)]">Agent 流水线</span>
        <span v-if="totalLatencyMs" class="flex items-center gap-1 text-[11px] text-[var(--color-ide-text-dim)] ml-auto">
          <Clock class="w-3 h-3" />
          {{ formatLatency(totalLatencyMs) }}
        </span>
      </div>

      <!-- 进度条 -->
      <div class="flex items-center gap-2">
        <div class="flex-1 h-1.5 rounded-full bg-[var(--color-ide-surface-hover)] overflow-hidden">
          <div
            :class="[
              'h-full rounded-full transition-all duration-500 ease-out',
              stats.errors > 0 ? 'bg-red-500/50' : 'bg-gradient-to-r from-brand-400 to-purple-500'
            ]"
            :style="{ width: `${stats.progress}%` }"
          />
        </div>
        <span class="text-[10px] text-[var(--color-ide-text-dim)] font-mono">{{ stats.completed }}/{{ stats.total }}</span>
      </div>
    </div>

    <!-- 流程图 (水平 DAG) -->
    <div class="p-4">
      <div class="flex items-start gap-2 flex-wrap">
        <template v-for="(stage, idx) in stages" :key="stage.id">
          <!-- 节点 -->
          <div
            @click="emit('stageClick', stage)"
            :class="[
              'flex-shrink-0 relative rounded-xl border p-3 min-w-[140px] cursor-pointer transition-all duration-300 group',
              stage.status === 'in_progress' ? `${agentStyle(stage.agent_name).bg} border-brand-500/20 shadow-lg shadow-brand-500/5` :
              stage.status === 'completed' ? 'bg-emerald-500/[0.03] border-emerald-500/10' :
              stage.status === 'error' ? 'bg-red-500/[0.03] border-red-500/10' :
              'bg-white/[0.01] border-white/[0.05]'
            ]"
          >
            <!-- 状态角标 -->
            <div class="absolute -top-2 -right-2 w-5 h-5 rounded-full flex items-center justify-center"
              :class="stage.status === 'completed' ? 'bg-emerald-500/20' :
                      stage.status === 'in_progress' ? 'bg-brand-500/20' :
                      stage.status === 'error' ? 'bg-red-500/20' : 'bg-[var(--color-ide-surface)]'"
            >
              <CheckCircle2
                v-if="stage.status === 'completed'"
                class="w-3 h-3 text-emerald-400"
              />
              <Loader2
                v-else-if="stage.status === 'in_progress'"
                class="w-3 h-3 text-brand-400 animate-spin"
              />
              <XCircle
                v-else-if="stage.status === 'error'"
                class="w-3 h-3 text-red-400"
              />
              <Clock v-else class="w-3 h-3 text-[var(--color-ide-text-dim)]" />
            </div>

            <!-- Agent 头像 -->
            <div class="flex items-center gap-2 mb-2">
              <div
                class="w-8 h-8 rounded-lg flex items-center justify-center"
                :style="{ background: agentStyle(stage.agent_name).bg }"
              >
                <component
                  :is="agentStyle(stage.agent_name).icon"
                  class="w-4 h-4"
                  :style="{ color: agentStyle(stage.agent_name).color }"
                />
              </div>
              <div>
                <p class="text-xs font-semibold" :style="{ color: agentStyle(stage.agent_name).color }">
                  {{ agentStyle(stage.agent_name).label }}
                </p>
                <p class="text-[10px] text-[var(--color-ide-text-dim)]">{{ stage.agent_name }}</p>
              </div>
            </div>

            <!-- 工具调用统计 -->
            <div v-if="stage.tool_calls?.length" class="flex items-center gap-1 text-[10px] text-[var(--color-ide-text-dim)]">
              <Wrench class="w-3 h-3" />
              {{ stage.tool_calls.length }} 工具调用
            </div>

            <!-- 耗时 -->
            <div v-if="stageDuration(stage)" class="mt-1 text-[10px] text-[var(--color-ide-text-dim)]">
              <Clock class="w-3 h-3 inline mr-0.5" />
              {{ stageDuration(stage) }}
            </div>

            <!-- 摘要 -->
            <p
              v-if="stage.summary"
              class="mt-1.5 text-[10px] text-[var(--color-ide-text-dim)] leading-relaxed line-clamp-2 group-hover:text-[var(--color-ide-text-dim)] transition-colors"
            >
              {{ stage.summary }}
            </p>

            <!-- 错误提示 -->
            <p
              v-if="stage.status === 'error'"
              class="mt-1 text-[10px] text-red-400"
            >
              阶段执行失败
            </p>
          </div>

          <!-- 箭头连接线 (在节点间) -->
          <div
            v-if="idx < stages.length - 1"
            class="flex items-center self-center flex-shrink-0"
          >
            <div class="flex items-center" :style="{ color: '#4b5563' }">
              <ArrowRight class="w-5 h-5" />
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 环形流程简化视图 (移动端) -->
    <div class="md:hidden p-3 border-t border-white/[0.04]">
      <div class="grid grid-cols-3 gap-1.5">
        <div
          v-for="stage in stages"
          :key="stage.id"
          @click="emit('stageClick', stage)"
          :class="[
            'flex flex-col items-center gap-1 p-2 rounded-lg text-center cursor-pointer transition-colors',
            stage.status === 'in_progress' ? agentStyle(stage.agent_name).bg :
            stage.status === 'completed' ? 'bg-emerald-500/[0.03]' :
            stage.status === 'error' ? 'bg-red-500/[0.03]' : 'bg-white/[0.01]'
          ]"
        >
          <component
            :is="stage.status === 'in_progress' ? Loader2 : CheckCircle2"
            :class="[
              'w-3.5 h-3.5',
              stage.status === 'in_progress' ? 'animate-spin text-brand-400' :
              stage.status === 'completed' ? 'text-emerald-400' :
              stage.status === 'error' ? 'text-red-400' : 'text-[var(--color-ide-text-dim)]'
            ]"
          />
          <span class="text-[10px] font-medium text-[var(--color-ide-text)]">{{ agentStyle(stage.agent_name).label }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
