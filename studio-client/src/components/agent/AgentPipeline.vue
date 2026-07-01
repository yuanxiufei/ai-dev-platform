<script setup lang="ts">
/**
 * AgentPipeline.vue — 多Agent编排管线可视化
 *
 * 参考项目：LangGraph (graph workflow), AutoGen (multi-agent), CrewAI (role-based)
 *
 * 展示 Planner → Coder → Reviewer 三阶段流水线
 * 每阶段带状态指示、工具调用计数、摘要
 */
import {
  Bot,
  CheckCircle2,
  Code2,
  FileSearch,
  GitPullRequest,
  Loader2,
  XCircle,
} from "lucide-vue-next"
import { computed } from "vue"
import type { PipelineStage, ToolCallRecord } from "@/types/studio"

const props = defineProps<{
  stages: PipelineStage[]
  /** 是否正在运行中 */
  isActive?: boolean
  /** 当前活跃的阶段名 */
  activeStage?: string
}>()

const emit = defineEmits<{
  (e: "stageClick", stage: PipelineStage): void
}>()

// ── 阶段配置映射 ──
const STAGE_CONFIG: Record<string, {
  icon: typeof Bot
  label: string
  color: string
  bg: string
  description: string
}> = {
  planner: {
    icon: FileSearch,
    label: "Planner",
    color: "#6366f1",
    bg: "rgba(99,102,241,0.08)",
    description: "分析需求，制定计划",
  },
  coder: {
    icon: Code2,
    label: "Coder",
    color: "#10b981",
    bg: "rgba(16,185,129,0.08)",
    description: "执行编码任务",
  },
  reviewer: {
    icon: GitPullRequest,
    label: "Reviewer",
    color: "#f59e0b",
    bg: "rgba(245,158,11,0.08)",
    description: "审查代码质量",
  },
}

function stageConfig(stage: PipelineStage) {
  const key = stage.agent_name?.toLowerCase() || ""
  return STAGE_CONFIG[key] || {
    icon: Bot,
    label: stage.agent_name,
    color: "#a78bfa",
    bg: "rgba(167,139,250,0.08)",
    description: "",
  }
}

// ── 阶段状态图标 ──
const statusIcon: Record<PipelineStage["status"], typeof CheckCircle2> = {
  pending: CheckCircle2,
  in_progress: Loader2,
  completed: CheckCircle2,
  error: XCircle,
}

const statusColor: Record<PipelineStage["status"], string> = {
  pending: "#475569",
  in_progress: "#6366f1",
  completed: "#10b981",
  error: "#ef4444",
}

const statusLabel: Record<PipelineStage["status"], string> = {
  pending: "等待中",
  in_progress: "执行中",
  completed: "已完成",
  error: "出错",
}

// ── 总工具调用数 ──
const totalToolCalls = computed(() =>
  props.stages.reduce((sum, s) => sum + (s.tool_calls?.length || 0), 0)
)

const completedStages = computed(() =>
  props.stages.filter(s => s.status === "completed").length
)
</script>

<template>
  <div class="agent-pipeline rounded-xl border border-white/[0.06] bg-white/[0.02] overflow-hidden">
    <!-- 头部统计 -->
    <div class="flex items-center justify-between px-4 py-2.5 border-b border-white/[0.05] bg-white/[0.01]">
      <div class="flex items-center gap-2">
        <div class="w-5 h-5 rounded-md bg-brand-500/10 flex items-center justify-center">
          <Bot class="w-3 h-3 text-brand-400" />
        </div>
        <span class="text-xs font-semibold text-gray-300">Agent 编排管线</span>
        <span v-if="isActive" class="flex items-center gap-1 text-[10px] text-brand-400">
          <Loader2 class="w-3 h-3 animate-spin" />
          运行中
        </span>
      </div>
      <div class="flex items-center gap-3 text-[10px] text-gray-500">
        <span>{{ completedStages }}/{{ stages.length }} 阶段完成</span>
        <span v-if="totalToolCalls > 0">{{ totalToolCalls }} 次工具调用</span>
      </div>
    </div>

    <!-- 管线流程图 -->
    <div class="p-4">
      <div class="flex items-stretch gap-0">
        <template v-for="(stage, idx) in stages" :key="stage.id">
          <!-- 阶段卡片 -->
          <button
            v-if="stage.agent_name"
            @click="emit('stageClick', stage)"
            class="flex-1 flex flex-col items-center gap-2 px-2 py-3 rounded-lg border transition-all duration-200 cursor-pointer min-w-0 group"
            :style="{
              background: stageConfig(stage).bg,
              borderColor: stage.status === 'in_progress'
                ? stageConfig(stage).color + '40'
                : stage.status === 'completed'
                  ? stageConfig(stage).color + '20'
                  : 'rgba(255,255,255,0.04)',
            }"
          >
            <!-- 状态图标 -->
            <div
              class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 transition-all"
              :class="stage.status === 'in_progress' ? 'animate-pulse' : ''"
              :style="{ background: stageConfig(stage).bg, border: `1px solid ${stageConfig(stage).color}30` }"
            >
              <component
                :is="stage.status === 'in_progress' ? Loader2 : stageConfig(stage).icon"
                :class="[stage.status === 'in_progress' ? 'animate-spin' : '']"
                class="w-4 h-4"
                :style="{ color: statusColor[stage.status] }"
              />
            </div>

            <!-- 阶段标签 -->
            <span
              class="text-[11px] font-semibold truncate max-w-full"
              :style="{ color: stage.status === 'pending' ? '#64748b' : '#e2e8f0' }"
            >
              {{ stageConfig(stage).label }}
            </span>

            <!-- 状态文字 -->
            <span class="text-[9px]" :style="{ color: statusColor[stage.status] }">
              {{ statusLabel[stage.status] }}
            </span>

            <!-- 工具调用计数 -->
            <span
              v-if="stage.tool_calls?.length"
              class="text-[9px] px-1.5 py-0.5 rounded-full"
              :style="{
                background: stageConfig(stage).color + '15',
                color: stageConfig(stage).color,
              }"
            >
              {{ stage.tool_calls.length }} tools
            </span>

            <!-- 摘要 (完成时) -->
            <div
              v-if="stage.status === 'completed' && stage.summary"
              class="text-[9px] text-gray-500 text-center leading-tight mt-0.5 line-clamp-2"
            >
              {{ stage.summary }}
            </div>

            <!-- 错误信息 -->
            <div
              v-if="stage.status === 'error'"
              class="text-[9px] text-red-400 text-center leading-tight mt-0.5"
            >
              执行失败
            </div>
          </button>

          <!-- 连线箭头 -->
          <div
            v-if="idx < stages.length - 1 && stage.agent_name"
            class="flex items-center shrink-0 px-0.5"
          >
            <div class="flex items-center">
              <!-- 箭头线 -->
              <div
                class="w-4 h-px"
                :style="{
                  background: `linear-gradient(90deg, ${statusColor[stage.status]}30, ${statusColor[stages[idx + 1]?.status || 'pending']}30)`,
                }"
              />
              <!-- 箭头尖 -->
              <div
                class="w-0 h-0 border-t-4 border-b-4 border-l-4 border-t-transparent border-b-transparent"
                :style="{ borderLeftColor: statusColor[stages[idx + 1]?.status || 'pending'] + '40' }"
              />
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="stages.length === 0" class="flex flex-col items-center justify-center py-8 text-gray-600">
      <Bot class="w-8 h-8 mb-2 opacity-20" />
      <p class="text-xs">等待 Agent 编排启动...</p>
    </div>
  </div>
</template>

<style scoped>
.agent-pipeline {
  min-height: 0;
}
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
