<script setup lang="ts">
/**
 * ToolCallCard.vue — Cline/RooCode 风格工具调用内嵌卡片
 *
 * 参考 Cline ChatRow + RooCode McpExecution/ChatRow 的设计模式：
 *   - 低风险工具 (read/list/search) → 紧凑折叠列表
 *   - 高风险工具 (write/execute/delete) → 独立卡片，展示参数+结果
 *   - 流式工具：带旋转动画的 "执行中..." 状态
 *   - 错误工具：红色边框 + 错误详情展开
 *
 * 视觉结构：
 * ┌─────────────────────────────────────┐
 * │ 🛠️ read_file    ✓ 完成  12ms      │  ← 头部 (图标 + 名称 + 状态 + 耗时)
 * │   src/utils/helpers.ts            │  ← 参数摘要
 * │   ┌─────────────────────────────┐ │
 * │   │ [文件内容 / 执行结果...]     │ │  ← 可折叠结果区
 * │   └─────────────────────────────┘ │
 * └─────────────────────────────────────┘
 */
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronRight,
  Clock,
  Copy,
  FileCode,
  FilePlus,
  FileSearch,
  FileText,
  FileX,
  FolderSearch,
  Globe,
  Loader2,
  Search,
  Terminal,
  Trash2,
  Wrench,
  XCircle,
} from "lucide-vue-next"
import { computed, ref } from "vue"
import type { ToolCallRecord } from "@/types/studio"

const props = defineProps<{
  tool: ToolCallRecord
  /** 工具所属消息 (用于 Diff 跳转) */
  messageId?: string
}>()

const emit = defineEmits<{
  (e: "approve", toolId: string): void
  (e: "reject", toolId: string): void
}>()

// ── 展开/折叠状态 ──
const isExpanded = ref(false)
const showFullResult = ref(false)

// ── 工具类型分类 ──
const LOW_STAKES_TOOLS = new Set([
  "read_file", "list_files", "search_files",
  "list_code_symbols", "get_code_symbols",
  "search_graph", "query_graph",
])

const COMMAND_TOOLS = new Set([
  "execute_command", "run_shell", "bash",
])

const FILE_WRITE_TOOLS = new Set([
  "write_to_file", "create_file", "edit_file",
])

const FILE_DELETE_TOOLS = new Set([
  "delete_file", "remove_file",
])

// ── 工具图标映射 (参考 Cline ChatRow 的 switch case) ──
const toolIcon = computed(() => {
  const name = props.tool.name
  if (COMMAND_TOOLS.has(name)) return Terminal
  if (FILE_WRITE_TOOLS.has(name)) return FilePlus
  if (FILE_DELETE_TOOLS.has(name)) return Trash2
  if (name === "read_file") return FileText
  if (name === "list_files" || name === "list_code_symbols") return FolderSearch
  if (name.includes("search")) return FileSearch
  if (name.includes("web") || name.includes("fetch")) return Globe
  if (name === "apply_diff" || name === "diff") return FileCode
  return Wrench
})

// ── 工具名称映射 ──
const displayName = computed(() => {
  const map: Record<string, string> = {
    read_file: "读取文件",
    write_to_file: "写入文件",
    edit_file: "编辑文件",
    create_file: "创建文件",
    delete_file: "删除文件",
    list_files: "列出文件",
    search_files: "搜索文件",
    execute_command: "执行命令",
    run_shell: "运行Shell",
    list_code_symbols: "列举符号",
    get_code_symbols: "获取符号",
    search_graph: "搜索图谱",
    query_graph: "查询图谱",
    web_fetch: "网页抓取",
    web_search: "网络搜索",
    apply_diff: "应用差异",
    summarize: "总结",
  }
  return map[props.tool.name] || props.tool.name
})

// ── 低风险标记 ──
const isLowStakes = computed(() => LOW_STAKES_TOOLS.has(props.tool.name))

// ── 状态相关的 CSS 类 ──
const statusClass = computed(() => {
  if (props.tool.success === false) return "border-red-600/40 bg-red-500/5"
  if (props.tool.approval_status === "pending") return "border-amber-500/40 bg-amber-500/5"
  if (!props.tool.result) return "border-blue-500/30 bg-blue-500/5 animate-pulse"
  if (props.tool.success) return "border-emerald-500/30 bg-emerald-500/5"
  return "border-white/10 bg-white/[0.02]"
})

// ── 文件路径提取 ──
const filePath = computed(() => {
  const args = props.tool.arguments
  return (args?.path as string) || (args?.file_path as string) || (args?.file as string) || ""
})

// ── 参数摘要 ──
const argsSummary = computed(() => {
  const args = { ...props.tool.arguments }
  // 移除大内容字段，只保留关键参数
  delete args.content
  delete args.code
  delete args.query
  const entries = Object.entries(args)
  if (entries.length === 0 && filePath.value) return filePath.value
  if (entries.length === 1) {
    const [, val] = entries[0]
    return String(val).substring(0, 120)
  }
  return entries
    .map(([k, v]) => `${k}: ${String(v).substring(0, 60)}`)
    .join(", ")
    .substring(0, 200)
})

// ── 截断的结果预览 ──
const resultPreview = computed(() => {
  if (!props.tool.result) return ""
  // 参考 SWE-agent SmartRead: 默认100行
  const lines = props.tool.result.split("\n")
  if (lines.length <= 15) return props.tool.result
  return lines.slice(0, 15).join("\n") + `\n... (共 ${lines.length} 行)`
})

// ── 复制工具调用信息 ──
const copyToolInfo = () => {
  const info = [
    `工具: ${props.tool.name}`,
    `参数: ${JSON.stringify(props.tool.arguments, null, 2)}`,
    props.tool.result ? `结果:\n${props.tool.result}` : "",
  ].filter(Boolean).join("\n\n")
  navigator.clipboard.writeText(info)
}
</script>

<template>
  <div
    class="tool-call-card rounded-lg border p-3 mb-2 transition-colors"
    :class="[statusClass, { 'text-sm': isLowStakes }]"
  >
    <!-- ── 头部: 图标 + 工具名 + 状态 + 耗时 ── -->
    <div
      class="flex items-center gap-2 cursor-pointer select-none"
      :class="isLowStakes ? 'text-xs' : 'text-sm'"
      @click="isExpanded = !isExpanded"
    >
      <!-- 状态图标 -->
      <component
        :is="props.tool.success === false ? XCircle : props.tool.result ? Check : tool.approval_status === 'pending' ? Clock : Loader2"
        :class="[
          'shrink-0',
          isLowStakes ? 'size-3' : 'size-4',
          props.tool.success === false ? 'text-red-400' :
          props.tool.result ? 'text-emerald-400' :
          props.tool.approval_status === 'pending' ? 'text-amber-400 animate-pulse' :
          'text-blue-400 animate-spin'
        ]"
      />

      <!-- 工具图标 + 名称 -->
      <component :is="toolIcon" :class="['shrink-0 opacity-60', isLowStakes ? 'size-3' : 'size-3.5']" />
      <span class="font-medium text-white/90 truncate">{{ displayName }}</span>

      <!-- 参数摘要 (低风险工具显示) -->
      <span v-if="isLowStakes && argsSummary" class="text-white/40 truncate max-w-[200px]">
        {{ argsSummary }}
      </span>

      <!-- Spacer -->
      <span class="flex-1" />

      <!-- 耗时 (RooCode 风格) -->
      <span
        v-if="props.tool.latency_ms != null"
        class="text-white/40 tabular-nums shrink-0"
        :class="isLowStakes ? 'text-[10px]' : 'text-xs'"
      >
        {{ props.tool.latency_ms < 1000 ? `${props.tool.latency_ms}ms` : `${(props.tool.latency_ms / 1000).toFixed(1)}s` }}
      </span>

      <!-- 安全级别标签 -->
      <span
        v-if="props.tool.security_level && props.tool.security_level !== 'READ_ONLY'"
        class="text-[10px] px-1.5 py-0.5 rounded font-medium shrink-0"
        :class="{
          'bg-amber-500/20 text-amber-400': props.tool.security_level === 'FILE_MODIFY',
          'bg-red-500/20 text-red-400': props.tool.security_level === 'SYSTEM' || props.tool.security_level === 'UNSAFE',
          'bg-blue-500/20 text-blue-400': props.tool.security_level === 'FILE_CREATE',
        }"
      >
        {{ props.tool.security_level === 'FILE_MODIFY' ? '修改' : props.tool.security_level === 'SYSTEM' ? '系统' : props.tool.security_level }}
      </span>

      <!-- 展开/折叠箭头 -->
      <component
        :is="isExpanded ? ChevronDown : ChevronRight"
        :class="['shrink-0 text-white/30', isLowStakes ? 'size-3' : 'size-3.5']"
      />
    </div>

    <!-- ── 展开区域 ── -->
    <div v-if="isExpanded" class="mt-2 space-y-2">
      <!-- 审批按钮 (待审批状态) -->
      <div
        v-if="props.tool.approval_status === 'pending'"
        class="flex items-center gap-2 p-2 rounded bg-amber-500/10 border border-amber-500/20"
      >
        <AlertTriangle class="size-4 text-amber-400 shrink-0" />
        <span class="text-xs text-amber-300 flex-1">
          此操作需要审批: <strong>{{ displayName }}</strong>
          <span v-if="filePath"> — {{ filePath }}</span>
        </span>
        <button
          class="px-2 py-1 text-xs rounded bg-emerald-600/80 hover:bg-emerald-600 text-white font-medium"
          @click.stop="emit('approve', props.tool.id)"
        >
          批准
        </button>
        <button
          class="px-2 py-1 text-xs rounded bg-red-600/80 hover:bg-red-600 text-white font-medium"
          @click.stop="emit('reject', props.tool.id)"
        >
          拒绝
        </button>
      </div>

      <!-- 参数区域 -->
      <div v-if="Object.keys(props.tool.arguments).length > 0" class="space-y-1">
        <div class="text-[10px] uppercase tracking-wider text-white/30 font-semibold">参数</div>
        <pre class="text-xs bg-black/30 rounded p-2 overflow-x-auto text-white/70">{{ JSON.stringify(props.tool.arguments, null, 2) }}</pre>
      </div>

      <!-- 结果区域 -->
      <div v-if="props.tool.result" class="space-y-1">
        <div class="flex items-center justify-between">
          <span class="text-[10px] uppercase tracking-wider text-white/30 font-semibold">
            {{ props.tool.success === false ? '错误' : '结果' }}
          </span>
          <div class="flex items-center gap-1">
            <button
              class="text-[10px] text-white/40 hover:text-white/70 px-1.5 py-0.5 rounded hover:bg-white/5 flex items-center gap-0.5"
              @click.stop="copyToolInfo"
            >
              <Copy class="size-2.5" />
              复制
            </button>
            <button
              class="text-[10px] text-white/40 hover:text-white/70 px-1.5 py-0.5 rounded hover:bg-white/5"
              @click.stop="showFullResult = !showFullResult"
            >
              {{ showFullResult ? '收起' : '展开全部' }}
            </button>
          </div>
        </div>
        <pre
          class="text-xs rounded p-2 overflow-x-auto max-h-48 overflow-y-auto"
          :class="props.tool.success === false ? 'bg-red-500/10 text-red-300 border border-red-500/20' : 'bg-black/30 text-white/70'"
        >{{ showFullResult ? props.tool.result : resultPreview }}</pre>
      </div>

      <!-- 加载中状态 -->
      <div
        v-if="!props.tool.result && props.tool.approval_status !== 'pending'"
        class="flex items-center gap-2 py-1 text-xs text-blue-400"
      >
        <Loader2 class="size-3 animate-spin" />
        <span>执行中...</span>
      </div>
    </div>
  </div>
</template>
