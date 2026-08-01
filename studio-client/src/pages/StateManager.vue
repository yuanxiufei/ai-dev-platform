<script setup lang="ts">
/**
 * StateManager — 全局/工作区/会话状态持久化管理
 * 支持 3 种 scope: global / workspace / session
 */
import { ref, computed, onMounted, watch } from "vue"
import {
  Layers, Plus, Trash2, Save, RotateCcw, Search, RefreshCcw,
  Database, Sliders, Library, FolderOpen, Check, Copy, Edit3, X, AlertTriangle,
} from "lucide-vue-next"
import { stateApi, type StateItem } from "@/api/state"

// ── 状态 ──
const activeScope = ref<"global" | "workspace" | "session">("global")
const workspaceId = ref("default")
const stateData = ref<StateItem[]>([])
const loading = ref(false)
const error = ref("")
const searchQuery = ref("")
const copiedKey = ref("")

// 编辑弹窗
const showEditor = ref(false)
const editingKey = ref("")
const editingValue = ref("")
const editingTtl = ref(0)
const isNew = ref(false)

// 删除确认
const showDeleteConfirm = ref(false)
const deletingKey = ref("")

// 批量操作信息
const operationResult = ref<{ message: string; type: "success" | "error" } | null>(null)

// ── 过滤 ──
const filteredData = computed(() => {
  if (!searchQuery.value.trim()) return stateData.value
  const q = searchQuery.value.toLowerCase()
  return stateData.value.filter(
    (item) =>
      item.key.toLowerCase().includes(q) ||
      JSON.stringify(item.value).toLowerCase().includes(q)
  )
})

const totalKeys = computed(() => stateData.value.length)
const displayedKeys = computed(() => filteredData.value.length)
const keysWithTtl = computed(() => stateData.value.filter((i) => i.ttl > 0).length)

// ── 方法 ──
async function loadStates() {
  loading.value = true
  error.value = ""
  try {
    const result = await stateApi.list(activeScope.value, workspaceId.value)
    // 后端返回 { scope, workspaceId, data: {key:val,...} }，取内层 data
    const entries: StateItem[] = []
    const payload = result.data
    if (payload?.data && typeof payload.data === "object") {
      for (const [key, val] of Object.entries(payload.data as Record<string, unknown>)) {
        entries.push({
          key,
          value: val,
          scope: activeScope.value,
          ttl: 0,
        })
      }
    }
    stateData.value = entries
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "加载状态失败"
  } finally {
    loading.value = false
  }
}

async function saveState() {
  if (!editingKey.value.trim()) return
  try {
    await stateApi.set(activeScope.value, workspaceId.value, editingKey.value, {
      value: tryParseJson(editingValue.value),
      ttl: editingTtl.value,
    })
    showEditor.value = false
    await loadStates()
    showOpResult("状态保存成功", "success")
  } catch (e: any) {
    showOpResult("保存失败: " + (e?.response?.data?.detail || e?.message), "error")
  }
}

async function deleteState(key: string) {
  try {
    await stateApi.delete(activeScope.value, workspaceId.value, key)
    deletingKey.value = ""
    showDeleteConfirm.value = false
    await loadStates()
    showOpResult(`已删除 "${key}"`, "success")
  } catch (e: any) {
    showOpResult("删除失败: " + (e?.response?.data?.detail || e?.message), "error")
  }
}

async function doCleanup() {
  try {
    const result = await stateApi.cleanup()
    showOpResult(`清理完成，移除了 ${result.data.cleaned} 个过期状态`, "success")
    await loadStates()
  } catch (e: any) {
    showOpResult("清理失败: " + (e?.response?.data?.detail || e?.message), "error")
  }
}

async function doClearAll() {
  try {
    await stateApi.clearAll(workspaceId.value)
    showOpResult(`已清除工作区 "${workspaceId.value}" 的所有状态`, "success")
    await loadStates()
  } catch (e: any) {
    showOpResult("清除失败: " + (e?.response?.data?.detail || e?.message), "error")
  }
}

async function doFlush() {
  try {
    await stateApi.flush()
    showOpResult("已强制持久化所有状态", "success")
  } catch (e: any) {
    showOpResult("持久化失败: " + (e?.response?.data?.detail || e?.message), "error")
  }
}

function showOpResult(message: string, type: "success" | "error") {
  operationResult.value = { message, type }
  setTimeout(() => (operationResult.value = null), 4000)
}

// JSON 值处理
function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "null"
  if (typeof value === "string") return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function tryParseJson(str: string): unknown {
  try {
    return JSON.parse(str)
  } catch {
    return str
  }
}

function getValuePreview(value: unknown): string {
  const s = formatValue(value)
  return s.length > 80 ? s.slice(0, 80) + "..." : s
}

function getValueType(value: unknown): string {
  if (value === null) return "null"
  if (Array.isArray(value)) return "array"
  return typeof value
}

async function copyValue(value: unknown, key: string) {
  try {
    await navigator.clipboard.writeText(formatValue(value))
    copiedKey.value = key
    setTimeout(() => (copiedKey.value = ""), 2000)
  } catch {
    // ignored
  }
}

function openEdit(key = "", value = "", ttl = 0) {
  editingKey.value = key
  editingValue.value = typeof value === "string" ? value : formatValue(value)
  editingTtl.value = ttl
  isNew.value = !key
  showEditor.value = true
}

function confirmDelete(key: string) {
  deletingKey.value = key
  showDeleteConfirm.value = true
}

// 监听 scope/workspace 变化
watch([activeScope, workspaceId], () => {
  loadStates()
})

onMounted(() => {
  loadStates()
})

// ── 常量 ──
const scopeOptions = [
  { value: "global", label: "全局", icon: Database, description: "跨工作区共享" },
  { value: "workspace", label: "工作区", icon: FolderOpen, description: "当前工作区" },
  { value: "session", label: "会话", icon: Sliders, description: "当前会话" },
] as const
</script>

<template>
  <div class="h-full w-full flex flex-col bg-[var(--color-ide-bg)] text-[var(--color-ide-text)]">
    <!-- 顶部操作栏 -->
    <header class="flex-shrink-0 border-b border-[var(--color-ide-border)] px-5 py-3">
      <div class="flex items-center gap-3 flex-wrap">
        <Layers class="w-4 h-4 text-brand-400" />
        <h2 class="text-sm font-semibold">State Manager</h2>

        <!-- Scope 选择器 -->
        <div class="flex items-center gap-1 bg-surface-900 rounded-lg border border-[var(--color-ide-border)] p-0.5 ml-2">
          <button
            v-for="opt in scopeOptions"
            :key="opt.value"
            :class="[
              'flex items-center gap-1.5 px-3 py-1 rounded-md text-xs transition-all',
              activeScope === opt.value
                ? 'bg-brand-500/20 text-brand-300 font-medium'
                : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]',
            ]"
            @click="activeScope = opt.value"
          >
            <component :is="opt.icon" class="w-3 h-3" />
            {{ opt.label }}
          </button>
        </div>

        <!-- 工作区 ID -->
        <input
          v-if="activeScope === 'workspace'"
          v-model="workspaceId"
          class="px-2.5 py-1 rounded-md border border-[var(--color-ide-border)] bg-surface-900 text-xs text-[var(--color-ide-text)] w-32 focus:outline-none focus:border-brand-500/50"
          placeholder="Workspace ID"
        />

        <div class="flex-1" />

        <!-- 操作按钮 -->
        <div class="flex items-center gap-1.5">
          <!-- 新建 -->
          <button
            class="flex items-center gap-1 px-2.5 py-1 rounded-md bg-brand-500/10 hover:bg-brand-500/20 text-brand-400 text-xs border border-brand-500/20 transition-colors"
            @click="openEdit()"
          >
            <Plus class="w-3 h-3" /> 新建
          </button>

          <!-- 刷新 -->
          <button
            class="p-1.5 rounded-md hover:bg-white/10 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] transition-colors"
            title="刷新"
            @click="loadStates"
          >
            <RefreshCcw class="w-3.5 h-3.5" :class="{ 'animate-spin': loading }" />
          </button>
        </div>

        <!-- 高级操作 -->
        <div class="flex items-center gap-1.5 ml-2 border-l border-[var(--color-ide-border)] pl-2">
          <button
            class="text-[10px] px-2 py-1 rounded text-[var(--color-ide-text-dim)] hover:text-yellow-400 hover:bg-yellow-500/10 transition-colors"
            title="清理过期状态"
            @click="doCleanup"
          >
            清理
          </button>
          <button
            class="text-[10px] px-2 py-1 rounded text-[var(--color-ide-text-dim)] hover:text-brand-400 hover:bg-brand-500/10 transition-colors"
            title="强制持久化"
            @click="doFlush"
          >
            持久化
          </button>
          <button
            class="text-[10px] px-2 py-1 rounded text-[var(--color-ide-text-dim)] hover:text-red-400 hover:bg-red-500/10 transition-colors"
            title="清除所有状态"
            @click="doClearAll"
          >
            清除
          </button>
        </div>
      </div>

      <!-- 搜索 + 统计 -->
      <div class="flex items-center gap-3 mt-2.5">
        <div class="relative flex-1 max-w-sm">
          <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--color-ide-text-dim)]" />
          <input
            v-model="searchQuery"
            class="w-full pl-8 pr-3 py-1.5 rounded-md border border-[var(--color-ide-border)] bg-surface-900 text-xs text-[var(--color-ide-text)] placeholder:text-[var(--color-ide-text-dim)]/50 focus:outline-none focus:border-brand-500/50"
            placeholder="搜索 key 或值..."
          />
        </div>
        <div class="flex items-center gap-4 text-[10px] text-[var(--color-ide-text-dim)]">
          <span>总计 <strong class="text-[var(--color-ide-text)]">{{ totalKeys }}</strong> 个</span>
          <span v-if="searchQuery">显示 <strong class="text-[var(--color-ide-text)]">{{ displayedKeys }}</strong> 个</span>
          <span v-if="keysWithTtl > 0">含TTL <strong class="text-yellow-400">{{ keysWithTtl }}</strong> 个</span>
        </div>
      </div>
    </header>

    <!-- 消息条 -->
    <div
      v-if="operationResult"
      :class="[
        'flex-shrink-0 px-5 py-2 text-xs flex items-center gap-2 border-b',
        operationResult.type === 'success'
          ? 'bg-green-500/10 border-green-500/20 text-green-400'
          : 'bg-red-500/10 border-red-500/20 text-red-400',
      ]"
    >
      <Check v-if="operationResult.type === 'success'" class="w-3.5 h-3.5" />
      <AlertTriangle v-else class="w-3.5 h-3.5" />
      {{ operationResult.message }}
    </div>

    <!-- 主区域 -->
    <div class="flex-1 overflow-hidden flex flex-col">
      <!-- 加载 -->
      <div
        v-if="loading"
        class="flex-1 flex items-center justify-center"
      >
        <div class="flex flex-col items-center gap-2 text-[var(--color-ide-text-dim)]">
          <RefreshCcw class="w-6 h-6 animate-spin" />
          <span class="text-xs">加载状态数据...</span>
        </div>
      </div>

      <!-- 错误 -->
      <div
        v-else-if="error"
        class="flex-1 flex items-center justify-center"
      >
        <div class="flex flex-col items-center gap-3 text-red-400">
          <AlertTriangle class="w-8 h-8" />
          <span class="text-xs">{{ error }}</span>
          <button
            class="px-3 py-1.5 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-xs transition-colors"
            @click="loadStates"
          >
            重试
          </button>
        </div>
      </div>

      <!-- 空状态 -->
      <div
        v-else-if="stateData.length === 0"
        class="flex-1 flex items-center justify-center"
      >
        <div class="flex flex-col items-center gap-2 text-[var(--color-ide-text-dim)]/60">
          <Layers class="w-10 h-10" />
          <span class="text-sm">暂无状态数据</span>
          <span class="text-xs">点击 "新建" 添加第一个状态</span>
        </div>
      </div>

      <!-- 状态列表 -->
      <div v-else class="flex-1 overflow-y-auto p-3">
        <div class="space-y-1">
          <div
            v-for="item in filteredData"
            :key="item.key"
            class="group rounded-lg border border-[var(--color-ide-border)] bg-surface-900/60 hover:border-brand-500/30 transition-colors"
          >
            <!-- 展开行 -->
            <details class="[&>summary::-webkit-details-marker]:hidden [&>summary::marker]:hidden">
              <summary class="flex items-center gap-3 px-3 py-2 cursor-pointer select-none">
                <!-- 类型标签 -->
                <span
                  :class="[
                    'px-1.5 py-0.5 rounded text-[9px] font-mono font-medium uppercase border',
                    getValueType(item.value) === 'string'
                      ? 'text-green-400 border-green-500/20 bg-green-500/10'
                      : getValueType(item.value) === 'number'
                        ? 'text-blue-400 border-blue-500/20 bg-blue-500/10'
                        : getValueType(item.value) === 'boolean'
                          ? 'text-yellow-400 border-yellow-500/20 bg-yellow-500/10'
                          : getValueType(item.value) === 'array'
                            ? 'text-purple-400 border-purple-500/20 bg-purple-500/10'
                            : getValueType(item.value) === 'object'
                              ? 'text-cyan-400 border-cyan-500/20 bg-cyan-500/10'
                              : 'text-[var(--color-ide-text-dim)] border-[var(--color-ide-border)]',
                  ]"
                >
                  {{ getValueType(item.value) }}
                </span>

                <!-- Key -->
                <code class="text-xs text-brand-300 font-mono truncate flex-1 min-w-0">
                  {{ item.key }}
                </code>

                <!-- TTL -->
                <span
                  v-if="item.ttl > 0"
                  class="text-[10px] text-yellow-400/70 flex-shrink-0"
                >
                  TTL: {{ item.ttl }}s
                </span>

                <!-- Value 预览 -->
                <span class="text-[11px] text-[var(--color-ide-text-dim)]/70 truncate max-w-[200px] hidden sm:block">
                  {{ getValuePreview(item.value) }}
                </span>

                <!-- 操作按钮 -->
                <div class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
                  <button
                    class="p-1 rounded hover:bg-white/10 text-[var(--color-ide-text-dim)] hover:text-brand-400 transition-colors"
                    title="复制值"
                    @click.stop.prevent="copyValue(item.value, item.key)"
                  >
                    <Check v-if="copiedKey === item.key" class="w-3 h-3 text-green-400" />
                    <Copy v-else class="w-3 h-3" />
                  </button>
                  <button
                    class="p-1 rounded hover:bg-white/10 text-[var(--color-ide-text-dim)] hover:text-blue-400 transition-colors"
                    title="编辑"
                    @click.stop.prevent="openEdit(item.key, item.value, item.ttl)"
                  >
                    <Edit3 class="w-3 h-3" />
                  </button>
                  <button
                    class="p-1 rounded hover:bg-white/10 text-[var(--color-ide-text-dim)] hover:text-red-400 transition-colors"
                    title="删除"
                    @click.stop.prevent="confirmDelete(item.key)"
                  >
                    <Trash2 class="w-3 h-3" />
                  </button>
                </div>
                <ChevronRight class="w-3 h-3 text-[var(--color-ide-text-dim)]" />
              </summary>

              <!-- 展开内容 - 完整 JSON -->
              <div class="px-3 pb-3 border-t border-[var(--color-ide-border)]/50 pt-2">
                <pre class="text-xs text-[var(--color-ide-text)] font-mono bg-surface-900 rounded-md p-3 overflow-x-auto max-h-[300px] overflow-y-auto whitespace-pre-wrap">{{ formatValue(item.value) }}</pre>
              </div>
            </details>
          </div>
        </div>
      </div>
    </div>

    <!-- ── 编辑弹窗 ── -->
    <Teleport to="body">
      <div
        v-if="showEditor"
        class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50"
        @click.self="showEditor = false"
      >
        <div class="w-[500px] max-h-[80vh] rounded-xl border border-[var(--color-ide-border)] bg-surface-800 shadow-2xl flex flex-col">
          <div class="flex items-center justify-between px-5 py-3 border-b border-[var(--color-ide-border)]">
            <h3 class="text-sm font-semibold">{{ isNew ? "新建状态" : "编辑状态" }}</h3>
            <button
              class="p-1 rounded-md hover:bg-white/10 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] transition-colors"
              @click="showEditor = false"
            >
              <X class="w-4 h-4" />
            </button>
          </div>

          <div class="flex-1 overflow-y-auto p-5 space-y-4">
            <!-- Key -->
            <label class="flex flex-col gap-1.5">
              <span class="text-[11px] text-[var(--color-ide-text-dim)] font-medium">Key</span>
              <input
                v-model="editingKey"
                class="px-3 py-2 rounded-lg border border-[var(--color-ide-border)] bg-surface-900 text-sm text-[var(--color-ide-text)] font-mono focus:outline-none focus:border-brand-500/50"
                :placeholder="activeScope === 'global' ? 'eg: theme, language' : 'eg: lastFile, recentProjects'"
                :disabled="!isNew"
              />
            </label>

            <!-- Value -->
            <label class="flex flex-col gap-1.5">
              <span class="text-[11px] text-[var(--color-ide-text-dim)] font-medium">
                Value
                <span class="text-[10px] opacity-50">(自动解析 JSON)</span>
              </span>
              <textarea
                v-model="editingValue"
                class="w-full rounded-lg border border-[var(--color-ide-border)] bg-surface-900 p-3 text-sm text-[var(--color-ide-text)] font-mono resize-none focus:outline-none focus:border-brand-500/50 h-32"
                placeholder='eg: "hello world" or {"key": "value"} or [1, 2, 3]'
                spellcheck="false"
              />
            </label>

            <!-- TTL (仅 global/workspace) -->
            <label v-if="activeScope !== 'session'" class="flex flex-col gap-1.5">
              <span class="text-[11px] text-[var(--color-ide-text-dim)] font-medium">
                TTL (秒)
                <span class="text-[10px] opacity-50">0 = 永不过期</span>
              </span>
              <input
                v-model.number="editingTtl"
                type="number"
                min="0"
                step="60"
                class="px-3 py-2 rounded-lg border border-[var(--color-ide-border)] bg-surface-900 text-sm text-[var(--color-ide-text)] focus:outline-none focus:border-brand-500/50 w-40"
              />
            </label>
          </div>

          <div class="flex items-center justify-end gap-2 px-5 py-3 border-t border-[var(--color-ide-border)]">
            <button
              class="px-3 py-1.5 rounded-lg text-xs text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-surface-900 transition-colors"
              @click="showEditor = false"
            >
              取消
            </button>
            <button
              class="flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-xs font-medium transition-colors disabled:opacity-50"
              :disabled="!editingKey.trim()"
              @click="saveState"
            >
              <Save class="w-3 h-3" /> 保存
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ── 删除确认弹窗 ── -->
    <Teleport to="body">
      <div
        v-if="showDeleteConfirm"
        class="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50"
        @click.self="showDeleteConfirm = false"
      >
        <div class="w-[380px] rounded-xl border border-[var(--color-ide-border)] bg-surface-800 shadow-2xl">
          <div class="flex items-center gap-3 px-5 py-4">
            <div class="w-10 h-10 rounded-full bg-red-500/10 flex items-center justify-center flex-shrink-0">
              <AlertTriangle class="w-5 h-5 text-red-400" />
            </div>
            <div>
              <h4 class="text-sm font-semibold">确认删除</h4>
              <p class="text-xs text-[var(--color-ide-text-dim)] mt-1">
                确定要删除 <code class="text-brand-300">{{ deletingKey }}</code> 吗？此操作不可撤销。
              </p>
            </div>
          </div>
          <div class="flex items-center justify-end gap-2 px-5 py-3 border-t border-[var(--color-ide-border)]">
            <button
              class="px-3 py-1.5 rounded-lg text-xs text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-surface-900 transition-colors"
              @click="showDeleteConfirm = false"
            >
              取消
            </button>
            <button
              class="px-4 py-1.5 rounded-lg bg-red-500 hover:bg-red-600 text-white text-xs font-medium transition-colors"
              @click="deleteState(deletingKey)"
            >
              删除
            </button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
