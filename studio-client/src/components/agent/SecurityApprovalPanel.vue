<script setup lang="ts">
/**
 * SecurityApprovalPanel.vue — 安全审批面板
 *
 * 参考项目：Open Interpreter (分级审批：bash / file / script)
 *         AutoCLI (5级安全策略：READ_ONLY → UNSAFE)
 *
 * 功能：
 *   1. 列出等待审批的工具调用（含安全级别、参数预览）
 *   2. 分级显示：绿色(READ_ONLY) → 黄色(FILE_MODIFY) → 红色(UNSAFE)
 *   3. 审批操作：批准单个 / 拒绝单个 / 批准所有 / 拒绝所有
 *   4. 自动批准模式：设置最低安全阈值，低于阈值的自动通过
 *   5. 审计日志：记录每次审批决策
 */
import {
  AlertTriangle,
  Check,
  ChevronRight,
  ExternalLink,
  History,
  Shield,
  ShieldAlert,
  ShieldCheck,
  ShieldOff,
  Terminal,
  X,
  Wrench,
  Code,
  FileText,
  Search,
  Globe,
} from "lucide-vue-next"
import { computed, onMounted, ref } from "vue"
import type { ToolCallRecord } from "@/types/studio"

const props = defineProps<{
  pending: ToolCallRecord[]
  /** 已完成的审批历史 */
  history?: ToolCallRecord[]
  /** 自动批准模式 */
  autoApprove?: boolean
  /** 自动批准的最低安全级别阈值（低于此级别自动批准） */
  autoApproveThreshold?: "READ_ONLY" | "FILE_CREATE" | "FILE_MODIFY" | "SYSTEM" | "UNSAFE"
}>()

const emit = defineEmits<{
  (e: "approve", toolId: string): void
  (e: "reject", toolId: string): void
  (e: "approveAll"): void
  (e: "rejectAll"): void
  (e: "toggleAutoApprove", enabled: boolean): void
  (e: "setThreshold", level: string): void
  /** 🆕 Cline 风格: 添加到 Always Allow 列表 */
  (e: "alwaysAllow", toolId: string, toolName: string): void
}>()

// ═══════════════════ 状态 ═══════════════════
const expandedIds = ref<Set<string>>(new Set())
const showHistory = ref(false)

/** 🆕 Cline 风格: Always Allow 记忆模式 */
const ALWAYS_ALLOW_KEY = "security_always_allow"
const alwaysAllowTools = ref<Set<string>>(new Set())

onMounted(() => {
  try {
    const raw = localStorage.getItem(ALWAYS_ALLOW_KEY)
    if (raw) alwaysAllowTools.value = new Set(JSON.parse(raw))
  } catch { /* ignore */ }
})

function saveAlwaysAllow() {
  try {
    localStorage.setItem(ALWAYS_ALLOW_KEY, JSON.stringify([...alwaysAllowTools.value]))
  } catch { /* ignore */ }
}

function handleAlwaysAllow(toolId: string, toolName: string) {
  if (alwaysAllowTools.value.has(toolName)) {
    alwaysAllowTools.value.delete(toolName)
  } else {
    alwaysAllowTools.value.add(toolName)
  }
  saveAlwaysAllow()
  emit("alwaysAllow", toolId, toolName)
}

function toggleExpand(id: string) {
  expandedIds.value.has(id) ? expandedIds.value.delete(id) : expandedIds.value.add(id)
}

// ═══════════════════ 安全级别配置 ═══════════════════
const SECURITY_CONFIG = {
  READ_ONLY: {
    label: "只读",
    color: "text-emerald-400",
    bg: "bg-emerald-500/8",
    border: "border-emerald-500/15",
    icon: ShieldCheck,
    level: 0,
    description: "仅读取信息，无副作用",
  },
  FILE_CREATE: {
    label: "新建文件",
    color: "text-blue-400",
    bg: "bg-blue-500/8",
    border: "border-blue-500/15",
    icon: Shield,
    level: 1,
    description: "创建新文件，不修改现有文件",
  },
  FILE_MODIFY: {
    label: "修改文件",
    color: "text-amber-400",
    bg: "bg-amber-500/8",
    border: "border-amber-500/15",
    icon: ShieldAlert,
    level: 2,
    description: "修改现有文件内容",
  },
  SYSTEM: {
    label: "系统命令",
    color: "text-orange-400",
    bg: "bg-orange-500/8",
    border: "border-orange-500/15",
    icon: AlertTriangle,
    level: 3,
    description: "执行系统级命令，需谨慎",
  },
  UNSAFE: {
    label: "危险操作",
    color: "text-red-400",
    bg: "bg-red-500/8",
    border: "border-red-500/15",
    icon: ShieldOff,
    level: 4,
    description: "高风险操作，需要显式确认",
  },
} as const

function securityLevel(level?: string) {
  const key = (level || "SYSTEM") as keyof typeof SECURITY_CONFIG
  return SECURITY_CONFIG[key] || SECURITY_CONFIG.SYSTEM
}

// ═══════════════════ 参数格式化 ═══════════════════
function formatArgs(args: Record<string, unknown>): string {
  try {
    return JSON.stringify(args, null, 2)
  } catch {
    return String(args)
  }
}

function truncateArgs(args: Record<string, unknown>, maxLen = 80): string {
  const str = formatArgs(args)
  return str.length > maxLen ? str.slice(0, maxLen) + "…" : str
}

// ═══════════════════ 统计 ═══════════════════
const stats = computed(() => {
  const total = props.pending.length
  const byLevel: Record<string, number> = {}
  for (const t of props.pending) {
    const lv = t.security_level || "SYSTEM"
    byLevel[lv] = (byLevel[lv] || 0) + 1
  }
  return { total, byLevel }
})

// 是否有危险操作
const hasUnsafe = computed(() =>
  props.pending.some(t => t.security_level === "UNSAFE")
)

// 是否有高风险命令
const hasSystemCommands = computed(() =>
  props.pending.some(t => t.security_level === "SYSTEM" || t.security_level === "UNSAFE")
)
</script>

<template>
  <div v-if="pending.length > 0 || (history && history.length > 0)" class="security-panel rounded-xl border border-[var(--color-ide-border)] bg-white/[0.01] overflow-hidden">
    <!-- 头部警告 -->
    <div
      :class="[
        'flex items-center justify-between px-4 py-3 border-b',
        hasUnsafe ? 'border-red-500/15 bg-red-500/[0.04]' :
        hasSystemCommands ? 'border-orange-500/15 bg-orange-500/[0.03]' :
        'border-white/[0.04] bg-white/[0.02]'
      ]"
    >
      <div class="flex items-center gap-2.5">
        <component
          :is="hasUnsafe ? ShieldOff : hasSystemCommands ? AlertTriangle : Shield"
          :class="['w-4 h-4', hasUnsafe ? 'text-red-400' : hasSystemCommands ? 'text-orange-400' : 'text-brand-400']"
        />
        <span class="text-sm font-semibold text-[var(--color-ide-text)]">
          工具审批 ({{ stats.total }})
        </span>

        <!-- 安全级别分布 -->
        <div class="flex items-center gap-1">
          <span
            v-for="(count, level) in stats.byLevel"
            :key="level"
            :class="['text-[10px] px-1.5 py-0.5 rounded-full', securityLevel(level).bg, securityLevel(level).color]"
          >
            {{ securityLevel(level).label }} {{ count }}
          </span>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <!-- 🆕 Always Allow 计数 -->
        <span
          v-if="alwaysAllowTools.size > 0"
          class="text-[10px] text-emerald-400/70 bg-emerald-500/5 px-1.5 py-0.5 rounded-full flex items-center gap-1"
          title="已设置始终允许的工具"
        >
          <Check class="w-2.5 h-2.5" />
          始终允许 {{ alwaysAllowTools.size }}
        </span>

        <!-- 自动批准开关 -->
        <label class="flex items-center gap-1.5 cursor-pointer">
          <span class="text-[10px] text-[var(--color-ide-text-dim)]">自动批准</span>
          <button
            @click="emit('toggleAutoApprove', !autoApprove)"
            :class="[
              'relative w-8 h-4 rounded-full transition-colors duration-200',
              autoApprove ? 'bg-emerald-500/30' : 'bg-[var(--color-ide-surface-hover)]'
            ]"
          >
            <span
              :class="[
                'absolute top-0.5 w-3 h-3 rounded-full bg-white transition-all duration-200',
                autoApprove ? 'left-4' : 'left-0.5'
              ]"
            />
          </button>
        </label>

        <!-- 批量审批 -->
        <div class="flex items-center gap-1 pl-2 border-l border-[var(--color-ide-border)]">
          <button
            @click="emit('approveAll')"
            class="flex items-center gap-1 px-2 py-1 text-[11px] text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 rounded-md transition-colors"
          >
            <Check class="w-3 h-3" /> 全部通过
          </button>
          <button
            @click="emit('rejectAll')"
            class="flex items-center gap-1 px-2 py-1 text-[11px] text-red-400 bg-red-500/10 hover:bg-red-500/20 rounded-md transition-colors"
          >
            <X class="w-3 h-3" /> 全部拒绝
          </button>
        </div>
      </div>
    </div>

    <!-- 审批列表 -->
    <div class="max-h-[400px] overflow-y-auto custom-scroll divide-y divide-white/[0.03]">
      <div
        v-for="tool in pending"
        :key="tool.id"
        :class="['transition-colors duration-150', securityLevel(tool.security_level).bg]"
      >
        <!-- 工具行 -->
        <div
          @click="toggleExpand(tool.id)"
          class="flex items-center gap-2.5 px-4 py-2.5 cursor-pointer group"
        >
          <button class="p-0.5 rounded text-[var(--color-ide-text-dim)] group-hover:text-[var(--color-ide-text-dim)] transition-colors shrink-0">
            <ChevronRight v-if="!expandedIds.has(tool.id)" class="w-3.5 h-3.5" />
            <ChevronRight v-else class="w-3.5 h-3.5 rotate-90" />
          </button>

          <!-- 安全级别徽章 -->
          <div
            :class="[
              'w-8 h-8 rounded-lg flex items-center justify-center shrink-0',
              securityLevel(tool.security_level).bg,
              'border',
              securityLevel(tool.security_level).border
            ]"
          >
            <component
              :is="securityLevel(tool.security_level).icon"
              :class="['w-4 h-4', securityLevel(tool.security_level).color]"
            />
          </div>

          <!-- 工具信息 -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="text-sm font-mono font-medium text-[var(--color-ide-text)]">{{ tool.name }}</span>
              <span
                :class="['text-[9px] font-semibold uppercase px-1.5 py-0.5 rounded-full', securityLevel(tool.security_level).bg, securityLevel(tool.security_level).color]"
              >
                {{ securityLevel(tool.security_level).label }}
              </span>
            </div>
            <p class="text-[11px] text-[var(--color-ide-text-dim)] truncate font-mono">{{ truncateArgs(tool.arguments) }}</p>
          </div>

          <!-- 审批按钮 -->
          <div class="flex items-center gap-1 shrink-0">
            <button
              @click.stop="emit('reject', tool.id)"
              class="p-1.5 rounded-lg text-red-500 hover:bg-red-500/10 transition-colors"
              title="拒绝"
            >
              <X class="w-3.5 h-3.5" />
            </button>
            <button
              @click.stop="emit('approve', tool.id)"
              class="p-1.5 rounded-lg text-emerald-500 hover:bg-emerald-500/10 transition-colors"
              title="批准"
            >
              <Check class="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        <!-- 展开的参数详情 -->
        <div v-if="expandedIds.has(tool.id)" :class="['px-4 pb-3', securityLevel(tool.security_level).border, 'border-t']">
          <div class="pt-2 space-y-2">
            <!-- 安全描述 -->
            <div class="flex items-start gap-2 text-[11px]" :class="securityLevel(tool.security_level).color">
              <AlertTriangle class="w-3.5 h-3.5 mt-px shrink-0" />
              <span>{{ securityLevel(tool.security_level).description }}</span>
            </div>

            <!-- 完整参数 -->
            <div class="bg-surface-900/80 rounded-lg border border-white/[0.04] p-2.5">
              <pre class="text-[11px] text-[var(--color-ide-text)] font-mono whitespace-pre-wrap">{{ formatArgs(tool.arguments) }}</pre>
            </div>

            <!-- 操作 -->
            <div class="flex items-center gap-2">
              <button
                @click="emit('approve', tool.id)"
                class="flex items-center gap-1 px-3 py-1.5 text-xs text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 rounded-lg transition-colors"
              >
                <Check class="w-3 h-3" /> 批准执行
              </button>
              <button
                @click="emit('reject', tool.id)"
                class="flex items-center gap-1 px-3 py-1.5 text-xs text-red-400 bg-red-500/10 hover:bg-red-500/20 rounded-lg transition-colors"
              >
                <X class="w-3 h-3" /> 拒绝
              </button>

              <!-- 🆕 Cline 风格: Always Allow 记忆 -->
              <div class="flex-1" />
              <label
                class="flex items-center gap-1.5 cursor-pointer px-2 py-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] transition-colors"
                :title="alwaysAllowTools.has(tool.name) ? '取消自动批准' : '以后自动批准此工具'"
              >
                <span
                  :class="[
                    'w-3.5 h-3.5 rounded border flex items-center justify-center transition-colors',
                    alwaysAllowTools.has(tool.name)
                      ? 'bg-emerald-500/30 border-emerald-500/50'
                      : 'border-[var(--color-ide-border)]'
                  ]"
                  @click.stop="handleAlwaysAllow(tool.id, tool.name)"
                >
                  <Check v-if="alwaysAllowTools.has(tool.name)" class="w-2.5 h-2.5 text-emerald-300" />
                </span>
                <span class="text-[10px] text-[var(--color-ide-text-dim)] whitespace-nowrap">始终允许</span>
              </label>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 审批历史 (底部可折叠) -->
    <div v-if="history && history.length > 0" class="border-t border-white/[0.04]">
      <button
        @click="showHistory = !showHistory"
        class="w-full flex items-center gap-2 px-4 py-2 text-xs text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-white/[0.01] transition-colors"
      >
        <History class="w-3.5 h-3.5" />
        审批历史 ({{ history.length }})
        <ChevronRight :class="['w-3 h-3 transition-transform ml-auto', showHistory ? 'rotate-90' : '']" />
      </button>

      <div v-if="showHistory" class="max-h-[160px] overflow-y-auto custom-scroll border-t border-white/[0.02]">
        <div
          v-for="h in history"
          :key="h.id"
          class="flex items-center gap-2 px-4 py-1.5 text-xs"
        >
          <span
            :class="[
              'w-1.5 h-1.5 rounded-full shrink-0',
              h.approval_status === 'approved' ? 'bg-emerald-400' : 'bg-red-400'
            ]"
          />
          <span class="text-[var(--color-ide-text)] font-mono">{{ h.name }}</span>
          <span
            :class="h.approval_status === 'approved' ? 'text-emerald-400' : 'text-red-400'"
          >
            {{ h.approval_status === 'approved' ? '已批准' : '已拒绝' }}
          </span>
          <span class="text-[var(--color-ide-text-dim)] ml-auto">{{ h.security_level }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scroll::-webkit-scrollbar { width: 3px; }
.custom-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,.06); border-radius: 9999px; }
</style>
