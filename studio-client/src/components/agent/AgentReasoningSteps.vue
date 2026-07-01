<script setup lang="ts">
/**
 * AgentReasoningSteps.vue — Agent 推理过程可视化 (Cline 增强版)
 *
 * 参考项目：Cline (step-by-step agent output), Roo Code (reasoning steps UI)
 *
 * 新增功能 (Cline 风格):
 *   - 整体进度条 + 进度百分比
 *   - 每步耗时统计 (elapsed_ms)
 *   - 步骤序号 (Step 1/N)
 *   - 文件引用展开 (references)
 *   - 错误详情展开 + 重试按钮
 *   - 流式更新支持 (新步骤实时追加)
 */
import {
  BarChart3,
  BookOpen,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Code2,
  FileCode,
  Loader2,
  RotateCcw,
  Search,
  XCircle,
} from "lucide-vue-next"
import { computed, ref } from "vue"
import type { ReasoningStep } from "@/types/studio"

const props = defineProps<{
  steps: ReasoningStep[]
  /** 是否正在运行 */
  isStreaming?: boolean
}>()

const emit = defineEmits<{
  (e: "stepClick", step: ReasoningStep): void
  /** Cline 风格: 重试失败步骤 */
  (e: "retryStep", step: ReasoningStep): void
}>()

// ── 折叠控制 ──
const collapsed = ref(false)
const showAll = ref(false)
const expandedDetails = ref<Set<string>>(new Set())
const DISPLAY_LIMIT = 3

const displaySteps = computed(() =>
  showAll.value ? props.steps : props.steps.slice(-DISPLAY_LIMIT)
)

const hasMoreSteps = computed(() =>
  props.steps.length > DISPLAY_LIMIT && !showAll.value
)

function toggleDetail(stepId: string) {
  const s = expandedDetails.value
  s.has(stepId) ? s.delete(stepId) : s.add(stepId)
}

function getStepNumber(step: ReasoningStep): number {
  return props.steps.findIndex(s => s.id === step.id) + 1
}

// ── 步骤类型配置 ──
const STEP_CONFIG: Record<ReasoningStep["type"], {
  icon: typeof Brain
  label: string
  color: string
  bg: string
}> = {
  thinking:  { icon: Brain,      label: "思考",   color: "#6366f1", bg: "rgba(99,102,241,0.08)" },
  planning:  { icon: BarChart3,  label: "规划",   color: "#f59e0b", bg: "rgba(245,158,11,0.08)" },
  analyzing: { icon: Search,     label: "分析",   color: "#22d3ee", bg: "rgba(34,211,238,0.08)" },
  deciding:  { icon: BookOpen,   label: "决策",   color: "#a78bfa", bg: "rgba(167,139,250,0.08)" },
  executing: { icon: Code2,      label: "执行",   color: "#10b981", bg: "rgba(16,185,129,0.08)" },
}

function stepConfig(step: ReasoningStep) {
  return STEP_CONFIG[step.type] || STEP_CONFIG.thinking
}

// ── 统计数据 ──
const stats = computed(() => {
  const total = props.steps.length
  const completed = props.steps.filter(s => s.status === "completed").length
  const inProgress = props.steps.filter(s => s.status === "in_progress").length
  const errors = props.steps.filter(s => s.status === "error").length
  return { total, completed, inProgress, errors }
})

const totalElapsed = computed(() =>
  props.steps.reduce((sum, s) => sum + (s.elapsed_ms || 0), 0)
)

const progressPercent = computed(() => {
  if (stats.value.total === 0) return 0
  return Math.round((stats.value.completed / stats.value.total) * 100)
})

function formatElapsed(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  return `${(ms / 60000).toFixed(1)}min`
}
</script>

<template>
  <div v-if="steps.length > 0" class="reasoning-steps rounded-lg border border-white/[0.06] bg-white/[0.01] overflow-hidden">
    <!-- ═══════ 头部折叠栏 ═══════ -->
    <button
      @click="collapsed = !collapsed"
      class="w-full flex items-center justify-between px-3.5 py-2.5 border-b border-white/[0.04] hover:bg-white/[0.02] transition-colors cursor-pointer"
    >
      <div class="flex items-center gap-2 min-w-0">
        <Brain class="w-3.5 h-3.5 text-brand-400 shrink-0" />
        <span class="text-xs font-semibold text-gray-300">推理过程</span>

        <!-- 统计标签 -->
        <div class="flex items-center gap-1.5">
          <span v-if="stats.completed > 0" class="text-[10px] text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded-full tabular-nums">
            {{ stats.completed }}/{{ stats.total }}
          </span>
          <span v-if="stats.inProgress > 0" class="text-[10px] text-brand-400 bg-brand-500/10 px-1.5 py-0.5 rounded-full flex items-center gap-1">
            <Loader2 class="w-2.5 h-2.5 animate-spin" />{{ stats.inProgress }}
          </span>
          <span v-if="stats.errors > 0" class="text-[10px] text-red-400 bg-red-500/10 px-1.5 py-0.5 rounded-full">
            {{ stats.errors }} 失败
          </span>
          <span v-if="totalElapsed > 0" class="text-[10px] text-gray-500 flex items-center gap-0.5">
            <Clock class="w-2.5 h-2.5" />{{ formatElapsed(totalElapsed) }}
          </span>
        </div>
      </div>

      <span class="text-gray-600 text-xs transition-transform duration-200 shrink-0" :class="{ 'rotate-180': collapsed }">▾</span>
    </button>

    <!-- ═══════ 进度条 (Cline 风格) ═══════ -->
    <div v-if="!collapsed" class="h-0.5 bg-white/[0.04]">
      <div
        class="h-full transition-all duration-500 ease-out rounded-r"
        :class="stats.errors > 0 ? 'bg-amber-500/60' : 'bg-brand-500/60'"
        :style="{ width: `${Math.max(progressPercent, stats.inProgress > 0 ? 5 : 0)}%` }"
      />
    </div>

    <!-- ═══════ 步骤列表 ═══════ -->
    <div v-if="!collapsed" class="p-2 space-y-1 max-h-80 overflow-y-auto custom-scroll">
      <!-- "还有更多" 提示 -->
      <div v-if="hasMoreSteps" class="px-2 py-1">
        <button
          @click="showAll = true"
          class="text-[10px] text-brand-400 hover:text-brand-300 transition-colors flex items-center gap-1"
        >
          <span>▾</span> 还有 {{ steps.length - DISPLAY_LIMIT }} 步推理，点击展开
        </button>
      </div>

      <div
        v-for="step in displaySteps"
        :key="step.id"
        class="flex items-start gap-2.5 px-2.5 py-2 rounded-md transition-all duration-200 cursor-pointer group"
        :class="[
          step.status === 'in_progress'
            ? 'bg-brand-500/5 border border-brand-500/10'
            : step.status === 'error'
              ? 'bg-red-500/3 border border-red-500/8'
              : 'hover:bg-white/[0.02] border border-transparent'
        ]"
        @click="emit('stepClick', step)"
        @click.stop="toggleDetail(step.id)"
      >
        <!-- ── 左侧: 步骤序号 + 图标 ── -->
        <div class="flex flex-col items-center gap-1 shrink-0">
          <div
            class="w-6 h-6 rounded-md flex items-center justify-center"
            :style="{ background: stepConfig(step).bg }"
          >
            <component
              :is="step.status === 'in_progress' ? Loader2 : stepConfig(step).icon"
              :class="[step.status === 'in_progress' ? 'animate-spin' : '']"
              class="w-3.5 h-3.5"
              :style="{ color: stepConfig(step).color }"
            />
          </div>
          <!-- Cline 风格: 步骤序号 -->
          <span class="text-[9px] text-gray-600 tabular-nums font-mono">{{ getStepNumber(step) }}</span>
        </div>

        <!-- ── 右侧: 内容区 ── -->
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-1.5 mb-0.5">
            <!-- 类型标签 -->
            <span
              class="text-[10px] font-semibold uppercase tracking-wider"
              :style="{ color: stepConfig(step).color }"
            >
              {{ stepConfig(step).label }}
            </span>

            <!-- Cline 风格: 耗时显示 -->
            <span v-if="step.status === 'completed' && step.elapsed_ms" class="text-[10px] text-gray-500 tabular-nums flex items-center gap-0.5">
              <Clock class="w-2.5 h-2.5" />{{ formatElapsed(step.elapsed_ms) }}
            </span>

            <!-- 状态图标 -->
            <component
              :is="step.status === 'in_progress' ? Loader2 : CheckCircle2"
              :class="[
                'w-3 h-3',
                step.status === 'completed' ? 'text-emerald-400' :
                step.status === 'in_progress' ? 'text-brand-400 animate-spin' :
                step.status === 'error' ? 'text-red-400' : 'text-gray-600'
              ]"
            />
          </div>

          <!-- 主文本 -->
          <p
            class="text-xs leading-relaxed whitespace-pre-wrap break-words"
            :class="[
              step.status === 'error' ? 'text-red-300/80' :
              step.status === 'pending' ? 'text-gray-600' : 'text-gray-300'
            ]"
          >
            {{ step.content }}
          </p>

          <!-- ═══ Cline 风格: 展开详情 (文件引用 / 错误详情) ═══ -->
          <div v-if="expandedDetails.has(step.id)" class="mt-2 space-y-1.5">
            <!-- 文件引用 -->
            <div v-if="step.references?.length" class="pl-1 border-l-2 border-brand-500/20 ml-0.5">
              <div class="text-[10px] text-gray-500 font-medium mb-1">引用文件</div>
              <div
                v-for="ref in step.references"
                :key="ref"
                class="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] text-brand-400/70 bg-brand-500/5 font-mono"
              >
                <FileCode class="w-3 h-3 shrink-0" />
                <span class="truncate">{{ ref }}</span>
              </div>
            </div>

            <!-- 错误详情 -->
            <div v-if="step.status === 'error' && step.error_detail" class="pl-1 border-l-2 border-red-500/20 ml-0.5">
              <div class="flex items-center gap-1 mb-1">
                <XCircle class="w-3 h-3 text-red-400" />
                <span class="text-[10px] text-red-400 font-medium">错误详情</span>
              </div>
              <p class="text-[10px] text-red-300/70 leading-relaxed whitespace-pre-wrap pl-4">
                {{ step.error_detail }}
              </p>

              <!-- Cline 风格: 重试按钮 -->
              <button
                @click.stop="emit('retryStep', step)"
                class="mt-1.5 flex items-center gap-1 px-2 py-1 rounded-md text-[10px] bg-red-500/8 border border-red-500/15 text-red-400 hover:bg-red-500/15 transition-colors"
              >
                <RotateCcw class="w-3 h-3" /> 重试
              </button>
            </div>
          </div>
        </div>

        <!-- 展开/折叠箭头指示 -->
        <div v-if="step.references?.length || (step.status === 'error' && step.error_detail)" class="shrink-0 mt-0.5">
          <ChevronDown
            v-if="!expandedDetails.has(step.id)"
            class="w-3.5 h-3.5 text-gray-600 group-hover:text-gray-400 transition-colors"
          />
          <ChevronUp
            v-else
            class="w-3.5 h-3.5 text-brand-400"
          />
        </div>
      </div>
    </div>

    <!-- ═══════ 折叠时摘要 ═══════ -->
    <div v-else class="flex items-center gap-2 px-3.5 py-2 text-xs text-gray-500">
      <div class="flex-1">
        已完成 {{ stats.completed }}/{{ stats.total }} 步推理
        <span v-if="stats.inProgress > 0" class="text-brand-400"> · 执行中</span>
        <span v-if="stats.errors > 0" class="text-red-400"> · {{ stats.errors }} 失败</span>
        <span v-if="totalElapsed > 0" class="text-gray-600"> · {{ formatElapsed(totalElapsed) }}</span>
      </div>

      <!-- 折叠进度条 -->
      <div class="h-1 bg-white/[0.05] rounded-full w-16 overflow-hidden shrink-0">
        <div
          class="h-full rounded-full transition-all duration-500"
          :class="stats.errors > 0 ? 'bg-amber-500/60' : 'bg-brand-500/60'"
          :style="{ width: `${progressPercent}%` }"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scroll::-webkit-scrollbar { width: 3px; }
.custom-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,.06); border-radius: 9999px; }
</style>
