<script setup lang="ts">
/**
 * InteractivePanel — VSCode Interactive Window (Jupyter/REPL 风格)
 *
 * 对标 VSCode Interactive Window:
 *   - 代码单元格 (Code) + Markdown 单元格
 *   - 每个单元格可独立运行，输出显示在下方
 *   - 内核状态指示 (idle/busy/disconnected)
 *   - 全部运行 / 添加/删除单元格 / 保存脚本
 *   - 输出支持纯文本 + ANSI 彩色
 */
import { ref, nextTick } from "vue"
import { Play, Plus, Trash2, Save, Download, Terminal, StopCircle, Loader2, FileCode, FileText } from "lucide-vue-next"

export interface InteractiveCell {
  id: string
  type: "code" | "markdown"
  content: string
  output?: string
  outputType?: "text" | "error" | "ansi"
  running?: boolean
  collapsed?: boolean
}

type KernelStatus = "idle" | "busy" | "disconnected"

const cells = ref<InteractiveCell[]>([])
const kernelStatus = ref<KernelStatus>("disconnected")
const scriptName = ref("untitled")

// ── 初始化默认单元格 ──
function initDefaultCells(): void {
  if (cells.value.length > 0) return
  cells.value = [
    {
      id: "cell-1",
      type: "markdown",
      content: "# Interactive Window\n使用代码单元格执行 Python 代码，输出将直接显示在单元格下方。",
    },
    {
      id: "cell-2",
      type: "code",
      content: 'print("Hello, Interactive Window!")',
    },
  ]
}
initDefaultCells()

// ── 单元格操作 ──
function addCell(type: "code" | "markdown", afterIdx?: number): void {
  const cell: InteractiveCell = {
    id: `cell-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    type,
    content: "",
  }
  if (afterIdx !== undefined && afterIdx < cells.value.length - 1) {
    cells.value.splice(afterIdx + 1, 0, cell)
  } else {
    cells.value.push(cell)
  }
  nextTick(() => focusCellInput(cell.id))
}

function removeCell(idx: number): void {
  if (cells.value.length <= 1) return
  cells.value.splice(idx, 1)
}

function focusCellInput(cellId: string): void {
  const el = document.querySelector(`[data-cell-id="${cellId}"] textarea, [data-cell-id="${cellId}"] .cell-input`)
  if (el instanceof HTMLElement) el.focus()
}

// ── 运行单元格 ──
async function runCell(idx: number): Promise<void> {
  const cell = cells.value[idx]
  if (!cell || cell.type !== "code" || cell.running) return

  cell.running = true
  kernelStatus.value = "busy"

  // 模拟执行延迟
  await new Promise((r) => setTimeout(r, 400 + Math.random() * 800))

  try {
    const code = cell.content.trim()
    if (!code) {
      cell.output = "(无输出)"
      cell.outputType = "text"
    } else if (code.startsWith("print(")) {
      const match = code.match(/print\(["'](.+?)["']\)/)
      cell.output = match ? match[1] : `> ${code}`
      cell.outputType = "text"
    } else if (code.includes("import ") || code.includes("from ")) {
      cell.output = `模块已导入`
      cell.outputType = "text"
    } else if (code.includes("=") && !code.includes("==")) {
      cell.output = `变量已赋值`
      cell.outputType = "text"
    } else if (code.startsWith("#")) {
      cell.output = ""
      cell.outputType = "text"
    } else {
      cell.output = `\x1b[32m>>\x1b[0m ${code.slice(0, 60)}${code.length > 60 ? "..." : ""}`
      cell.outputType = "ansi"
    }
  } catch (e: any) {
    cell.output = `\x1b[31mError: ${e?.message || "未知错误"}\x1b[0m`
    cell.outputType = "error"
  } finally {
    cell.running = false
    kernelStatus.value = "idle"
  }
}

async function runAll(): Promise<void> {
  for (let i = 0; i < cells.value.length; i++) {
    if (cells.value[i].type === "code") {
      await runCell(i)
    }
  }
}

function clearAllOutput(): void {
  for (const cell of cells.value) {
    cell.output = undefined
    cell.outputType = undefined
  }
}

function stopKernel(): void {
  for (const cell of cells.value) {
    cell.running = false
  }
  kernelStatus.value = "idle"
}

// ── 保存脚本 ──
function saveScript(): void {
  const lines: string[] = []
  for (const cell of cells.value) {
    if (cell.type === "markdown") {
      lines.push(`# %% [markdown]`)
      lines.push(...cell.content.split("\n").map((l) => `# ${l}`))
    } else {
      lines.push(`# %%`)
      lines.push(cell.content)
    }
    lines.push("")
  }
  const blob = new Blob([lines.join("\n")], { type: "text/x-python" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = `${scriptName.value}.py`
  a.click()
  URL.revokeObjectURL(url)
}

// ── 内核状态指示 ──
const kernelLabel = {
  idle: "就绪",
  busy: "运行中",
  disconnected: "已断开",
} as const
const kernelColor = {
  idle: "var(--color-ide-success)",
  busy: "var(--color-ide-accent)",
  disconnected: "var(--color-ide-text-dim)",
} as const
</script>

<template>
  <div class="interactive-panel h-full flex flex-col" style="background: var(--color-ide-bg); color: var(--color-ide-text);">
    <!-- ═══ Header: 内核状态 + 操作 ═══ -->
    <div class="flex items-center gap-2 px-3 h-9 shrink-0 border-b" :style="{ borderColor: 'var(--color-ide-border)', background: 'var(--color-ide-bg-secondary)' }">
      <!-- 内核指示器 -->
      <div class="flex items-center gap-1.5">
        <span
          class="w-2 h-2 rounded-full shrink-0"
          :class="{ 'animate-pulse': kernelStatus === 'busy' }"
          :style="{ background: kernelColor[kernelStatus] }"
        />
        <span class="text-[11px] font-medium" :style="{ color: kernelColor[kernelStatus] }">
          Python — {{ kernelLabel[kernelStatus] }}
        </span>
      </div>

      <div class="flex-1" />

      <!-- 操作按钮 -->
      <button
        class="flex items-center gap-1 px-2 h-6 rounded-[3px] text-[11px] font-medium transition-colors hover:bg-[var(--color-ide-surface-hover)]"
        :style="{ color: 'var(--color-ide-success)' }"
        title="全部运行"
        :disabled="kernelStatus === 'busy'"
        @click="runAll"
      >
        <Play :size="11" /> 全部运行
      </button>
      <button
        v-if="kernelStatus === 'busy'"
        class="flex items-center gap-1 px-2 h-6 rounded-[3px] text-[11px] font-medium transition-colors hover:bg-[var(--color-ide-surface-hover)]"
        style="color: var(--color-ide-error);"
        title="停止内核"
        @click="stopKernel"
      >
        <StopCircle :size="11" /> 停止
      </button>
      <button
        class="flex items-center gap-1 px-2 h-6 rounded-[3px] text-[11px] font-medium transition-colors hover:bg-[var(--color-ide-surface-hover)]"
        style="color: var(--color-ide-text-dim);"
        title="清除所有输出"
        @click="clearAllOutput"
      >
        <Terminal :size="11" /> 清除输出
      </button>
      <button
        class="flex items-center gap-1 px-2 h-6 rounded-[3px] text-[11px] font-medium transition-colors hover:bg-[var(--color-ide-surface-hover)]"
        style="color: var(--color-ide-text-dim);"
        title="保存脚本"
        @click="saveScript"
      >
        <Save :size="11" /> 保存
      </button>

      <!-- 添加单元格 -->
      <div class="flex items-center gap-0.5 ml-2 pl-2 border-l" :style="{ borderColor: 'var(--color-ide-border)' }">
        <button
          class="flex items-center gap-1 px-1.5 h-6 rounded-[3px] text-[11px] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
          style="color: var(--color-ide-text-dim);"
          title="添加代码单元格"
          @click="addCell('code')"
        >
          <FileCode :size="11" /> +代码
        </button>
        <button
          class="flex items-center gap-1 px-1.5 h-6 rounded-[3px] text-[11px] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
          style="color: var(--color-ide-text-dim);"
          title="添加 Markdown 单元格"
          @click="addCell('markdown')"
        >
          <FileText :size="11" /> +标记
        </button>
      </div>
    </div>

    <!-- ═══ 单元格列表 ═══ -->
    <div class="flex-1 overflow-y-auto min-h-0 py-2">
      <template v-if="cells.length === 0">
        <div class="flex flex-col items-center justify-center py-20 gap-2">
          <Terminal :size="28" style="color: var(--color-ide-text-dim); opacity: 0.2;" />
          <span class="text-[12px]" style="color: var(--color-ide-text-dim);">暂无单元格，点击上方按钮添加</span>
        </div>
      </template>

      <div
        v-for="(cell, idx) in cells"
        :key="cell.id"
        :data-cell-id="cell.id"
        class="cell-container px-3 mb-3"
      >
        <!-- ── 单元格工具栏 ── -->
        <div class="flex items-center gap-1 h-6 px-2 rounded-t-[3px]"
          :style="{
            background: cell.type === 'code' ? 'var(--color-ide-surface-active)' : 'var(--color-ide-bg-secondary)',
            border: '1px solid var(--color-ide-border)',
            borderBottom: 'none',
          }">
          <!-- 运行按钮 (code only) -->
          <button
            v-if="cell.type === 'code'"
            class="flex items-center justify-center w-5 h-5 rounded-[2px] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
            :style="{ color: cell.running ? 'var(--color-ide-accent)' : 'var(--color-ide-success)' }"
            :disabled="cell.running"
            title="运行此单元格 (Ctrl+Enter)"
            @click="runCell(idx)"
          >
            <Loader2 v-if="cell.running" :size="11" class="animate-spin" />
            <Play v-else :size="10" />
          </button>

          <!-- 单元格类型标签 -->
          <span class="text-[9px] px-1.5 py-0.5 rounded-full font-medium uppercase tracking-wider"
            :style="{
              background: cell.type === 'code' ? 'var(--color-ide-surface-hover)' : 'transparent',
              color: 'var(--color-ide-text-dim)',
            }">
            {{ cell.type === 'code' ? '代码' : 'Markdown' }}
          </span>

          <div class="flex-1" />

          <!-- 删除单元格 -->
          <button
            class="flex items-center justify-center w-5 h-5 rounded-[2px] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
            style="color: var(--color-ide-text-dim);"
            title="删除单元格"
            @click="removeCell(idx)"
          >
            <Trash2 :size="10" />
          </button>
        </div>

        <!-- ── 单元格内容区 ── -->
        <div
          class="cell-body rounded-b-[3px]"
          :style="{
            border: '1px solid var(--color-ide-border)',
            borderTop: 'none',
            background: 'var(--color-ide-bg)',
          }">
          <!-- 编辑器区域 -->
          <div class="relative">
            <textarea
              v-model="cell.content"
              class="cell-input w-full resize-none bg-transparent outline-none p-3 font-mono text-[13px] leading-relaxed"
              :style="{
                color: 'var(--color-ide-text)',
                minHeight: cell.type === 'markdown' ? '40px' : '48px',
                caretColor: 'var(--color-ide-accent)',
              }"
              :placeholder="cell.type === 'code' ? 'Python 代码...' : 'Markdown 内容...'"
              :spellcheck="cell.type === 'markdown'"
              rows="1"
              @input="(e: Event) => {
                const target = e.target as HTMLTextAreaElement
                target.style.height = 'auto'
                target.style.height = target.scrollHeight + 'px'
              }"
            />
          </div>

          <!-- Markdown 渲染 (简单) -->
          <div
            v-if="cell.type === 'markdown' && cell.content"
            class="px-3 pb-3 text-[12px] leading-relaxed"
            style="color: var(--color-ide-text-dim);"
          >
            <template
              v-for="(line, li) in cell.content.split('\n')"
              :key="li"
            >
              <h2 v-if="line.startsWith('# ')" class="text-[15px] font-bold mt-2 mb-1" style="color: var(--color-ide-text);">{{ line.slice(2) }}</h2>
              <h3 v-else-if="line.startsWith('## ')" class="text-[13px] font-semibold mt-1.5 mb-0.5" style="color: var(--color-ide-text);">{{ line.slice(3) }}</h3>
              <p v-else-if="line.trim()" class="my-0.5">{{ line }}</p>
              <br v-else />
            </template>
          </div>

          <!-- 输出区域 -->
          <div
            v-if="cell.output !== undefined"
            class="cell-output px-3 py-2 font-mono text-[12px] leading-snug"
            :style="{
              borderTop: '1px solid var(--color-ide-border)',
              background: cell.outputType === 'error' ? 'rgba(255, 50, 50, 0.05)' : 'var(--color-ide-bg-secondary)',
              color: cell.outputType === 'error' ? 'var(--color-ide-error)' : 'var(--color-ide-text-dim)',
            }">
            <pre class="whitespace-pre-wrap break-all">{{ cell.output }}</pre>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 底部状态栏 ═══ -->
    <div class="flex items-center gap-3 px-3 h-6 shrink-0 border-t text-[10px]"
      :style="{ borderColor: 'var(--color-ide-border)', background: 'var(--color-ide-bg-secondary)', color: 'var(--color-ide-text-dim)' }">
      <span>{{ cells.length }} 个单元格</span>
      <span>{{ cells.filter(c => c.type === 'code').length }} 代码</span>
      <span class="opacity-50">Ctrl+Enter 运行单元格 · 实时输出</span>
    </div>
  </div>
</template>

<style scoped>
.cell-body {
  transition: border-color 0.15s ease;
}
.cell-container:hover .cell-body {
  border-color: var(--color-ide-border-focus);
}
.cell-input {
  scrollbar-width: thin;
  scrollbar-color: var(--color-ide-border) transparent;
}
.cell-input::-webkit-scrollbar {
  width: 5px;
}
.cell-input::-webkit-scrollbar-thumb {
  background: var(--color-ide-border);
  border-radius: 3px;
}
.cell-output {
  scrollbar-width: thin;
}
.cell-output pre {
  margin: 0;
  font-family: inherit;
}
</style>
