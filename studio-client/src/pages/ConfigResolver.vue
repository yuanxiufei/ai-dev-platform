<script setup lang="ts">
/**
 * ConfigResolver — 变量解析器，VSCode 风格配置变量预览
 * 输入带 ${variable} 的文本 → 实时解析为最终值
 */
import { ref, computed, onMounted } from "vue"
import { configResolverApi, type VariableDef, type ResolveResult } from "@/api/configResolver"
import { Braces, Play, Copy, Check, RotateCcw, BookOpen, Search, ChevronRight, Wand2, Trash2 } from "lucide-vue-next"

// ── 状态 ──
const inputText = ref("")
const resolvedResult = ref<ResolveResult | null>(null)
const variables = ref<VariableDef[]>([])
const loadingVars = ref(false)
const resolving = ref(false)
const error = ref("")
const copied = ref(false)

// 上下文变量
const context = ref({
  workspace_root: "",
  file: "/src/app/main.py",
  file_basename: "main.py",
  file_extname: ".py",
  file_dirname: "/src/app",
  relative_file: "app/main.py",
  line_number: "",
  selected_text: "",
})

// 覆写
const configOverrides = ref<{ key: string; value: string }[]>([])
const envOverrides = ref<{ key: string; value: string }[]>([])

// 历史
const history = ref<{ text: string; result: ResolveResult; timestamp: number }[]>([])

// ── 计算变量出现 ──
interface VariableOccurrence {
  full: string
  name: string
  defaultValue: string
  resolved: string
  found: boolean
  description: string
}

const detectedVars = computed((): VariableOccurrence[] => {
  const regex = /\$\{(\w+)(?::([^}]*))?\}/g
  const results: VariableOccurrence[] = []
  let match: RegExpExecArray | null
  while ((match = regex.exec(inputText.value)) !== null) {
    const name = match[1]
    const def = variables.value.find((v) => v.name === name)
    results.push({
      full: match[0],
      name,
      defaultValue: match[2] ?? "",
      resolved: "",
      found: !!def,
      description: def?.description ?? "未知变量",
    })
  }
  return results
})

const uniqueDetectedVars = computed(() => {
  const seen = new Set<string>()
  return detectedVars.value.filter((v) => {
    if (seen.has(v.name)) return false
    seen.add(v.name)
    return true
  })
})

// ── 高亮后的文本 ──
const highlightedInput = computed(() => {
  if (!inputText.value) return ""
  return inputText.value.replace(
    /\$\{(\w+)(?::([^}]*))?\}/g,
    '<mark class="bg-brand-500/20 text-brand-300 px-0.5 rounded">$&</mark>'
  )
})

// ── 高亮后的结果 ──
const highlightedResult = computed(() => {
  if (!resolvedResult.value) return ""
  // 标识变化部分
  return resolvedResult.value.resolved
})

// ── 方法 ──
async function loadVariables() {
  loadingVars.value = true
  try {
    const r = await configResolverApi.listVariables()
    variables.value = r.data.variables
  } catch (e: any) {
    // 变量列表加载失败不影响核心功能
    console.warn("加载变量列表失败:", e)
  } finally {
    loadingVars.value = false
  }
}

async function doResolve() {
  if (!inputText.value.trim()) return
  resolving.value = true
  error.value = ""
  try {
    const overrides: Record<string, any> = {}
    for (const ov of configOverrides.value) {
      if (ov.key.trim()) overrides[ov.key.trim()] = ov.value
    }
    const env: Record<string, string> = {}
    for (const ev of envOverrides.value) {
      if (ev.key.trim()) env[ev.key.trim()] = ev.value
    }

    const result = await configResolverApi.resolve(inputText.value, {
      ...context.value,
      config_overrides: overrides,
      env_overrides: env,
    })
    resolvedResult.value = result.data
    history.value.unshift({ text: inputText.value, result: result.data, timestamp: Date.now() })
    if (history.value.length > 20) history.value.pop()
  } catch (e: any) {
    error.value = e?.response?.data?.detail || e?.message || "解析失败"
  } finally {
    resolving.value = false
  }
}

function loadFromHistory(item: typeof history.value[0]) {
  inputText.value = item.text
  resolvedResult.value = item.result
}

async function copyResult() {
  if (!resolvedResult.value) return
  try {
    await navigator.clipboard.writeText(resolvedResult.value.resolved)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    // fallback ignored
  }
}

function addOverride(section: "config" | "env") {
  if (section === "config") {
    configOverrides.value.push({ key: "", value: "" })
  } else {
    envOverrides.value.push({ key: "", value: "" })
  }
}

function removeOverride(section: "config" | "env", idx: number) {
  if (section === "config") configOverrides.value.splice(idx, 1)
  else envOverrides.value.splice(idx, 1)
}

function insertVariable(name: string) {
  const varStr = `\${${name}}`
  // 插入到光标位置或末尾
  inputText.value += (inputText.value ? " " : "") + varStr
}

function clearAll() {
  inputText.value = ""
  resolvedResult.value = null
  error.value = ""
}

onMounted(() => {
  loadVariables()
})
</script>

<template>
  <div class="h-full w-full flex bg-[var(--color-ide-bg)] text-[var(--color-ide-text)]">
    <!-- 左侧：变量库 -->
    <aside class="w-64 flex-shrink-0 border-r border-[var(--color-ide-border)] bg-surface-900/40 flex flex-col">
      <div class="px-4 py-3 border-b border-[var(--color-ide-border)]">
        <div class="flex items-center gap-2 text-xs font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-wider">
          <BookOpen class="w-3.5 h-3.5" />
          可用变量
        </div>
        <div class="relative mt-2">
          <Search class="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--color-ide-text-dim)]" />
          <input
            class="w-full pl-8 pr-3 py-1.5 rounded-md border border-[var(--color-ide-border)] bg-surface-900 text-xs text-[var(--color-ide-text)] placeholder:text-[var(--color-ide-text-dim)]/50 focus:outline-none focus:border-brand-500/50"
            placeholder="搜索变量..."
          />
        </div>
      </div>
      <div class="flex-1 overflow-y-auto p-2">
        <div v-if="loadingVars" class="text-xs text-[var(--color-ide-text-dim)] text-center py-4">
          加载中...
        </div>
        <div v-else-if="variables.length === 0" class="text-xs text-[var(--color-ide-text-dim)]/60 text-center py-4">
          暂无变量定义
        </div>
        <div v-else class="space-y-0.5">
          <button
            v-for="v in variables"
            :key="v.name"
            class="w-full text-left px-2.5 py-1.5 rounded-md hover:bg-white/5 text-xs transition-colors group flex items-center justify-between"
            @click="insertVariable(v.name)"
          >
            <div class="min-w-0">
              <code class="text-brand-400 font-mono text-[11px]">$&#123;{{ v.name }}}</code>
              <p class="text-[10px] text-[var(--color-ide-text-dim)]/60 truncate mt-0.5">{{ v.description }}</p>
            </div>
            <Wand2 class="w-3 h-3 text-[var(--color-ide-text-dim)]/30 group-hover:text-brand-400 transition-colors flex-shrink-0 ml-2" />
          </button>
        </div>
      </div>

      <!-- 检测到的变量 -->
      <div v-if="uniqueDetectedVars.length > 0" class="border-t border-[var(--color-ide-border)] p-3">
        <div class="text-[10px] font-semibold text-[var(--color-ide-text-dim)] uppercase mb-2">
          当前文本中的变量
        </div>
        <div class="space-y-1">
          <div
            v-for="dv in uniqueDetectedVars"
            :key="dv.name"
            class="flex items-center gap-1.5 text-[11px]"
          >
            <span
              :class="['w-1.5 h-1.5 rounded-full flex-shrink-0', dv.found ? 'bg-green-400' : 'bg-yellow-400']"
            />
            <code class="font-mono text-[11px]" :class="dv.found ? 'text-brand-400' : 'text-yellow-400'">
              {{ dv.name }}
            </code>
            <span v-if="dv.defaultValue" class="text-[var(--color-ide-text-dim)]/50 text-[10px]">
              ="{{ dv.defaultValue }}"
            </span>
          </div>
        </div>
      </div>
    </aside>

    <!-- 右侧：主区域 -->
    <div class="flex-1 flex flex-col min-w-0">
      <!-- 上下文设置 -->
      <header class="flex-shrink-0 border-b border-[var(--color-ide-border)] bg-surface-900/40 px-5 py-3">
        <div class="flex items-center gap-2 mb-2">
          <Braces class="w-4 h-4 text-brand-400" />
          <h2 class="text-sm font-semibold">Config Resolver</h2>
          <span class="text-[10px] text-[var(--color-ide-text-dim)]/60 ml-auto">
            输入含 &#36;{variable} 的文本，预览解析结果
          </span>
        </div>

        <!-- 上下文变量行 -->
        <div class="grid grid-cols-4 gap-2 mt-2">
          <label class="flex flex-col gap-0.5">
            <span class="text-[10px] text-[var(--color-ide-text-dim)]">workspaceRoot</span>
            <input
              v-model="context.workspace_root"
              class="px-2 py-1 rounded border border-[var(--color-ide-border)] bg-surface-900 text-[11px] text-[var(--color-ide-text)] focus:outline-none focus:border-brand-500/50"
              placeholder="/path/to/workspace"
            />
          </label>
          <label class="flex flex-col gap-0.5">
            <span class="text-[10px] text-[var(--color-ide-text-dim)]">file</span>
            <input
              v-model="context.file"
              class="px-2 py-1 rounded border border-[var(--color-ide-border)] bg-surface-900 text-[11px] text-[var(--color-ide-text)] focus:outline-none focus:border-brand-500/50"
            />
          </label>
          <label class="flex flex-col gap-0.5">
            <span class="text-[10px] text-[var(--color-ide-text-dim)]">relativeFile</span>
            <input
              v-model="context.relative_file"
              class="px-2 py-1 rounded border border-[var(--color-ide-border)] bg-surface-900 text-[11px] text-[var(--color-ide-text)] focus:outline-none focus:border-brand-500/50"
            />
          </label>
          <label class="flex flex-col gap-0.5">
            <span class="text-[10px] text-[var(--color-ide-text-dim)]">lineNumber / selectedText</span>
            <div class="flex gap-1">
              <input
                v-model="context.line_number"
                class="flex-1 px-2 py-1 rounded border border-[var(--color-ide-border)] bg-surface-900 text-[11px] text-[var(--color-ide-text)] focus:outline-none focus:border-brand-500/50"
                placeholder="行号"
              />
              <input
                v-model="context.selected_text"
                class="flex-1 px-2 py-1 rounded border border-[var(--color-ide-border)] bg-surface-900 text-[11px] text-[var(--color-ide-text)] focus:outline-none focus:border-brand-500/50"
                placeholder="选中文本"
              />
            </div>
          </label>
        </div>

        <!-- 覆写区域 - 可折叠 -->
        <details class="mt-2">
          <summary class="text-[10px] text-[var(--color-ide-text-dim)] cursor-pointer hover:text-[var(--color-ide-text)] transition-colors select-none">
            覆写设置 (Config: {{ configOverrides.length }} / Env: {{ envOverrides.length }})
          </summary>
          <div class="grid grid-cols-2 gap-3 mt-2">
            <!-- Config 覆写 -->
            <div>
              <div class="flex items-center gap-2 mb-1.5">
                <span class="text-[10px] text-[var(--color-ide-text-dim)] font-medium">Config Overrides</span>
                <button
                  class="text-[10px] text-brand-400 hover:text-brand-300 transition-colors"
                  @click="addOverride('config')"
                >
                  + 添加
                </button>
              </div>
              <div class="space-y-1 max-h-24 overflow-y-auto">
                <div
                  v-for="(ov, idx) in configOverrides"
                  :key="'cfg-' + idx"
                  class="flex items-center gap-1"
                >
                  <input
                    v-model="ov.key"
                    placeholder="key"
                    class="flex-1 px-1.5 py-0.5 rounded border border-[var(--color-ide-border)] bg-surface-900 text-[10px] text-[var(--color-ide-text)] focus:outline-none focus:border-brand-500/50"
                  />
                  <input
                    v-model="ov.value"
                    placeholder="value"
                    class="flex-1 px-1.5 py-0.5 rounded border border-[var(--color-ide-border)] bg-surface-900 text-[10px] text-[var(--color-ide-text)] focus:outline-none focus:border-brand-500/50"
                  />
                  <button
                    class="p-0.5 rounded text-[var(--color-ide-text-dim)] hover:text-red-400 transition-colors"
                    @click="removeOverride('config', idx)"
                  >
                    <Trash2 class="w-3 h-3" />
                  </button>
                </div>
              </div>
            </div>
            <!-- Env 覆写 -->
            <div>
              <div class="flex items-center gap-2 mb-1.5">
                <span class="text-[10px] text-[var(--color-ide-text-dim)] font-medium">Env Overrides</span>
                <button
                  class="text-[10px] text-brand-400 hover:text-brand-300 transition-colors"
                  @click="addOverride('env')"
                >
                  + 添加
                </button>
              </div>
              <div class="space-y-1 max-h-24 overflow-y-auto">
                <div
                  v-for="(ov, idx) in envOverrides"
                  :key="'env-' + idx"
                  class="flex items-center gap-1"
                >
                  <input
                    v-model="ov.key"
                    placeholder="KEY"
                    class="flex-1 px-1.5 py-0.5 rounded border border-[var(--color-ide-border)] bg-surface-900 text-[10px] text-[var(--color-ide-text)] focus:outline-none focus:border-brand-500/50"
                  />
                  <input
                    v-model="ov.value"
                    placeholder="VALUE"
                    class="flex-1 px-1.5 py-0.5 rounded border border-[var(--color-ide-border)] bg-surface-900 text-[10px] text-[var(--color-ide-text)] focus:outline-none focus:border-brand-500/50"
                  />
                  <button
                    class="p-0.5 rounded text-[var(--color-ide-text-dim)] hover:text-red-400 transition-colors"
                    @click="removeOverride('env', idx)"
                  >
                    <Trash2 class="w-3 h-3" />
                  </button>
                </div>
              </div>
            </div>
          </div>
        </details>
      </header>

      <!-- 输入区域 -->
      <div class="flex-1 flex flex-col overflow-hidden p-4 gap-3">
        <!-- 输入框 -->
        <div class="flex-1 flex flex-col min-h-0">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-[10px] text-[var(--color-ide-text-dim)] font-medium uppercase">输入文本</span>
            <div class="flex items-center gap-1">
              <button
                class="flex items-center gap-1 px-2 py-1 rounded text-[10px] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-white/5 transition-colors"
                @click="clearAll"
              >
                <RotateCcw class="w-3 h-3" /> 清空
              </button>
              <button
                class="flex items-center gap-1 px-2.5 py-1 rounded bg-brand-500 hover:bg-brand-600 text-white text-[11px] font-medium transition-colors disabled:opacity-50"
                :disabled="!inputText.trim() || resolving"
                @click="doResolve"
              >
                <Play class="w-3 h-3" />
                {{ resolving ? "解析中..." : "解析" }}
              </button>
            </div>
          </div>
          <textarea
            v-model="inputText"
            class="flex-1 w-full rounded-lg border border-[var(--color-ide-border)] bg-surface-900 p-3 text-sm text-[var(--color-ide-text)] font-mono resize-none focus:outline-none focus:border-brand-500/50 placeholder:text-[var(--color-ide-text-dim)]/40"
            placeholder="输入带 ${variable} 的文本，例如：&#10;Working on ${workspaceFolder} with file ${file}...&#10;Current line: ${lineNumber}"
            spellcheck="false"
          />
          <!-- 变量高亮预览 -->
          <div
            v-if="inputText"
            class="mt-1 px-3 py-1.5 border border-[var(--color-ide-border)]/50 rounded-md bg-surface-900/50 text-xs text-[var(--color-ide-text-dim)] overflow-x-auto whitespace-pre"
            v-html="highlightedInput || '（输入文本预览）'"
          />
        </div>

        <!-- 结果区域 -->
        <div class="flex-1 flex flex-col min-h-0">
          <div class="flex items-center justify-between mb-1.5">
            <span class="text-[10px] text-[var(--color-ide-text-dim)] font-medium uppercase">
              解析结果
              <span v-if="resolvedResult" class="text-green-400 ml-1">✅</span>
            </span>
            <button
              v-if="resolvedResult"
              class="flex items-center gap-1 px-2 py-1 rounded text-[10px] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-white/5 transition-colors"
              @click="copyResult"
            >
              <Check v-if="copied" class="w-3 h-3 text-green-400" />
              <Copy v-else class="w-3 h-3" />
              {{ copied ? "已复制" : "复制" }}
            </button>
          </div>

          <!-- 错误 -->
          <div
            v-if="error"
            class="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-400"
          >
            {{ error }}
          </div>

          <!-- 结果对比 -->
          <div
            v-else-if="resolvedResult"
            class="flex-1 rounded-lg border border-[var(--color-ide-border)] overflow-hidden flex flex-col"
          >
            <div class="grid grid-cols-2 flex-1 min-h-0">
              <div class="border-r border-[var(--color-ide-border)] flex flex-col min-h-0">
                <div class="px-3 py-1.5 border-b border-[var(--color-ide-border)]/50 bg-surface-900/60">
                  <span class="text-[10px] text-[var(--color-ide-text-dim)] font-medium">原始</span>
                </div>
                <pre class="flex-1 p-3 text-xs text-[var(--color-ide-text-dim)] font-mono overflow-auto whitespace-pre-wrap">{{ resolvedResult.original }}</pre>
              </div>
              <div class="flex flex-col min-h-0">
                <div class="px-3 py-1.5 border-b border-[var(--color-ide-border)]/50 bg-surface-900/60">
                  <span class="text-[10px] text-green-400 font-medium">已解析</span>
                </div>
                <pre class="flex-1 p-3 text-xs text-[var(--color-ide-text)] font-mono overflow-auto whitespace-pre-wrap">{{ resolvedResult.resolved }}</pre>
              </div>
            </div>
          </div>

          <!-- 空结果提示 -->
          <div
            v-else
            class="flex-1 rounded-lg border border-dashed border-[var(--color-ide-border)] flex items-center justify-center"
          >
            <div class="flex flex-col items-center gap-2 text-[var(--color-ide-text-dim)]/50">
              <Braces class="w-8 h-8" />
              <span class="text-xs">输入文本后点击 "解析" 查看结果</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 历史记录 -->
      <footer
        v-if="history.length > 0"
        class="flex-shrink-0 border-t border-[var(--color-ide-border)] bg-surface-900/30 px-4 py-2"
      >
        <div class="flex items-center gap-3 text-[10px] text-[var(--color-ide-text-dim)]">
          <span class="font-medium">历史:</span>
          <div class="flex items-center gap-1.5 overflow-x-auto">
            <button
              v-for="(item, idx) in history.slice(0, 8)"
              :key="idx"
              class="px-2 py-0.5 rounded border border-[var(--color-ide-border)]/50 hover:border-brand-500/50 hover:bg-surface-800 transition-colors text-[10px] truncate max-w-[160px] text-left"
              title="点击恢复"
              @click="loadFromHistory(item)"
            >
              {{ item.text.slice(0, 30) }}{{ item.text.length > 30 ? '...' : '' }}
            </button>
          </div>
        </div>
      </footer>
    </div>
  </div>
</template>
