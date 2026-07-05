<script setup lang="ts">
/**
 * GoToSymbol.vue — VSCode Ctrl+Shift+O 符号导航弹窗
 *
 * Session 36: 借鉴 VSCode src/vs/editor/contrib/quickAccess/browser/gotoSymbolQuickAccess.ts
 * 从编辑器内容中提取函数/类/变量/常量，支持搜索过滤和快速跳转
 */

import { computed, ref, onMounted, nextTick, watch } from "vue"
import { useIDEStore } from "@/stores/useIDEStore"
import { Search, Hash, Variable, FunctionSquare as FunIcon, Box, Layers } from "lucide-vue-next"

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: "close"): void
  (e: "go-to", line: number, column: number): void
}>()

const store = useIDEStore()

// ── 符号类型 ──
interface SymbolEntry {
  name: string
  kind: "function" | "class" | "variable" | "constant" | "interface" | "type" | "method" | "property"
  line: number
  column: number
  container?: string
}

// ── 搜索状态 ──
const query = ref("")
const selectedIndex = ref(0)
const inputRef = ref<HTMLInputElement | null>(null)

// ── 从编辑器内容提取符号 ──
const symbols = computed<SymbolEntry[]>(() => {
  const tab = store.activeTab
  if (!tab?.content) return []

  const lines = tab.content.split("\n")
  const results: SymbolEntry[] = []

  // 根据文件类型决定解析策略
  const ext = tab.filePath?.split(".").pop()?.toLowerCase() ?? ""
  const isJS = ["js", "jsx", "ts", "tsx", "mjs", "cjs"].includes(ext)
  const isPython = ext === "py"
  const isVue = ext === "vue"
  const isGo = ext === "go"
  const isRust = ext === "rs"
  const isJava = ext === "java" || ext === "kt"
  const isShell = ext === "sh" || ext === "bash" || ext === "zsh"
  const isCSS = ext === "css" || ext === "scss" || ext === "less"
  const isHTML = ext === "html" || ext === "xml" || ext === "svg"

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    const trimmed = line.trim()
    const lineNum = i + 1

    if (!trimmed || trimmed.startsWith("//") || trimmed.startsWith("#") && isShell) continue

    // JS/TS 解析
    if (isJS || isVue) {
      // function / async function / export function
      let m = trimmed.match(/(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+(\w[\w$]*)\s*\(/)
      if (m) { results.push({ name: m[1], kind: "function", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      // class
      m = trimmed.match(/(?:export\s+(?:default\s+)?)?class\s+(\w[\w$]*)/)
      if (m) { results.push({ name: m[1], kind: "class", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      // arrow function const/let/var
      m = trimmed.match(/(?:export\s+)?(?:const|let|var)\s+(\w[\w$]*)\s*=\s*(?:async\s*)?\(/)
      if (m) { results.push({ name: m[1], kind: "function", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }
      m = trimmed.match(/(?:export\s+)?(?:const|let|var)\s+(\w[\w$]*)\s*=\s*(?:async\s+)?(?:\([\w$,\s]*\)|[\w$]+)\s*=>/)
      if (m) { results.push({ name: m[1], kind: "function", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      // const (non-function)
      m = trimmed.match(/(?:export\s+)?const\s+(\w[\w$]*)\s*=/)
      if (m) { results.push({ name: m[1], kind: "constant", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      // interface / type
      m = trimmed.match(/(?:export\s+)?(?:interface|type)\s+(\w[\w$]*)/)
      if (m) { results.push({ name: m[1], kind: "interface", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      // method in class (indentation hint)
      m = trimmed.match(/^(?:static\s+)?(?:async\s+)?(\w[\w$]*)\s*\([\w$,\s'"`:[\]{}]*\)\s*\{?\s*$/)
      if (m && line.startsWith("  ") && m[1] !== "if" && m[1] !== "for" && m[1] !== "while" && m[1] !== "switch" && m[1] !== "catch" && m[1] !== "return") {
        results.push({ name: m[1], kind: "method", line: lineNum, column: trimmed.indexOf(m[1]) })
        continue
      }
    }

    // Python 解析
    if (isPython) {
      let m = trimmed.match(/^def\s+(\w+)\s*\(/)
      if (m) { results.push({ name: m[1], kind: "function", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      m = trimmed.match(/^class\s+(\w+)/)
      if (m) { results.push({ name: m[1], kind: "class", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      m = trimmed.match(/^([A-Z_][A-Z0-9_]*)\s*=\s*/)
      if (m) { results.push({ name: m[1], kind: "constant", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      m = trimmed.match(/^(\w[a-z_]*)\s*=\s*/)
      if (m && m[1] !== "if" && !trimmed.startsWith("if ")) {
        results.push({ name: m[1], kind: "variable", line: lineNum, column: trimmed.indexOf(m[1]) })
        continue
      }
    }

    // Go 解析
    if (isGo) {
      let m = trimmed.match(/^func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(/)
      if (m) { results.push({ name: m[1], kind: "function", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      m = trimmed.match(/^type\s+(\w+)\s+struct/)
      if (m) { results.push({ name: m[1], kind: "class", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      m = trimmed.match(/^type\s+(\w+)\s+interface/)
      if (m) { results.push({ name: m[1], kind: "interface", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      m = trimmed.match(/^(?:var|const)\s+(\w+)/)
      if (m) { results.push({ name: m[1], kind: "variable", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }
    }

    // Rust 解析
    if (isRust) {
      let m = trimmed.match(/^fn\s+(\w+)\s*[<(]/)
      if (m) { results.push({ name: m[1], kind: "function", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      m = trimmed.match(/^(?:pub\s+)?struct\s+(\w+)/)
      if (m) { results.push({ name: m[1], kind: "class", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      m = trimmed.match(/^(?:pub\s+)?enum\s+(\w+)/)
      if (m) { results.push({ name: m[1], kind: "class", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      m = trimmed.match(/^(?:pub\s+)?trait\s+(\w+)/)
      if (m) { results.push({ name: m[1], kind: "interface", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      m = trimmed.match(/^(?:pub\s+)?(?:static\s+)?(?:let|const)\s+(\w+)/)
      if (m) { results.push({ name: m[1], kind: "constant", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      m = trimmed.match(/^(?:pub\s+)?type\s+(\w+)/)
      if (m) { results.push({ name: m[1], kind: "type", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }
    }

    // Java/Kotlin
    if (isJava) {
      let m = trimmed.match(/(?:public|private|protected|static|\s)+\s+[\w<>[\],\s]+\s+(\w+)\s*\(/)
      if (m) { results.push({ name: m[1], kind: "method", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      m = trimmed.match(/(?:public\s+)?class\s+(\w+)/)
      if (m) { results.push({ name: m[1], kind: "class", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }

      m = trimmed.match(/(?:public\s+)?interface\s+(\w+)/)
      if (m) { results.push({ name: m[1], kind: "interface", line: lineNum, column: trimmed.indexOf(m[1]) }); continue }
    }

    // CSS 选择器
    if (isCSS) {
      const m = trimmed.match(/^([.#]?[\w-]+(?:\s*[,>+~]\s*[.#]?[\w-]+)*)\s*\{/)
      if (m && !m[1].startsWith("@")) {
        results.push({ name: m[1], kind: "class", line: lineNum, column: trimmed.indexOf(m[1]) })
        continue
      }
    }

    // HTML 元素
    if (isHTML) {
      const m = trimmed.match(/<(\w[\w-]*)[\s>]/)
      if (m && !m[1].startsWith("!")) {
        results.push({ name: `<${m[1]}>`, kind: "class", line: lineNum, column: trimmed.indexOf(m[1]) })
        continue
      }
    }

    // Shell 函数
    if (isShell) {
      const m = trimmed.match(/^function\s+(\w[\w-]*)\s*\{?\s*$|^(\w[\w-]*)\s*\(\s*\)\s*\{?\s*$/)
      if (m) {
        const name = m[1] || m[2]
        results.push({ name, kind: "function", line: lineNum, column: trimmed.indexOf(name) })
        continue
      }
    }
  }

  return results
})

// ── 过滤后的符号列表 ──
const filteredSymbols = computed(() => {
  const q = query.value.toLowerCase().trim()
  if (!q) return symbols.value
  return symbols.value.filter(s => s.name.toLowerCase().includes(q))
})

// ── 图标映射 ──
function getKindIcon(kind: string): any {
  switch (kind) {
    case "function":
    case "method": return FunIcon
    case "class": return Box
    case "variable":
    case "property": return Variable
    case "constant": return Hash
    case "interface":
    case "type": return Layers
    default: return Variable
  }
}

/** 颜色映射 ── VSCode SymbolIcon 色板 */
function getKindColor(kind: string): string {
  switch (kind) {
    case "function":
    case "method": return "#DCDCAA"
    case "class": return "#4EC9B0"
    case "variable":
    case "property": return "#9CDCFE"
    case "constant": return "#4FC1FF"
    case "interface":
    case "type": return "#C586C0"
    default: return "var(--color-ide-text-dim)"
  }
}

// ── 导航 ──
function selectSymbol(sym: SymbolEntry): void {
  emit("go-to", sym.line, sym.column)
  emit("close")
}

// ── 键盘导航 ──
function onKeydown(e: KeyboardEvent): void {
  if (e.key === "ArrowDown") {
    e.preventDefault()
    selectedIndex.value = Math.min(selectedIndex.value + 1, filteredSymbols.value.length - 1)
  } else if (e.key === "ArrowUp") {
    e.preventDefault()
    selectedIndex.value = Math.max(selectedIndex.value - 1, 0)
  } else if (e.key === "Enter") {
    e.preventDefault()
    const sel = filteredSymbols.value[selectedIndex.value]
    if (sel) selectSymbol(sel)
  } else if (e.key === "Escape") {
    emit("close")
  }
}

// ── 打开时重置状态 ──
watch(() => props.visible, (v) => {
  if (v) {
    query.value = ""
    selectedIndex.value = 0
    nextTick(() => inputRef.value?.focus())
  }
})
</script>

<template>
  <!-- VSCode Go To Symbol 弹窗: 覆盖在编辑器中央偏上 -->
  <Teleport to="body">
    <Transition
      enter-active-class="transition-all duration-150 ease-out"
      enter-from-class="opacity-0 scale-95"
      enter-to-class="opacity-100 scale-100"
      leave-active-class="transition-all duration-100 ease-in"
      leave-from-class="opacity-100 scale-100"
      leave-to-class="opacity-0 scale-95"
    >
      <div
        v-if="visible"
        class="fixed inset-0 flex items-start justify-center z-[60]"
        style="padding-top: 80px;"
        @click.self="emit('close')"
      >
        <div
          class="goto-symbol-popup flex flex-col overflow-hidden"
          :style="{
            width: '520px',
            maxHeight: '360px',
            background: 'var(--color-ide-bg)',
            border: '1px solid var(--color-ide-border)',
            borderRadius: '8px',
            boxShadow: '0 12px 48px rgba(0,0,0,0.5), 0 2px 8px rgba(0,0,0,0.2)',
          }"
          @click.stop
        >
          <!-- 搜索输入框 -->
          <div
            class="flex items-center gap-2 px-3 shrink-0"
            :style="{
              height: '36px',
              borderBottom: '1px solid var(--color-ide-border)',
            }"
          >
            <Search :size="14" style="color: var(--color-ide-text-dim); flex-shrink: 0;" />
            <input
              ref="inputRef"
              v-model="query"
              type="text"
              class="flex-1 bg-transparent border-none outline-none text-[13px] placeholder:text-[var(--color-ide-text-dim)]"
              placeholder="输入符号名称进行搜索   (例如: @handleClick)"
              style="color: var(--color-ide-text);"
              @keydown="onKeydown"
            />
            <span
              class="text-[10px] px-1.5 py-0 rounded"
              style="
                color: var(--color-ide-text-dim);
                background: var(--color-ide-surface-hover);
                flex-shrink: 0;
              "
            >
              {{ filteredSymbols.length }} 个符号
            </span>
          </div>

          <!-- 符号列表 -->
          <div class="flex-1 overflow-y-auto" style="scrollbar-gutter: stable;">
            <div v-if="filteredSymbols.length === 0" class="flex flex-col items-center justify-center py-10 gap-2">
              <Search :size="24" style="color: var(--color-ide-text-dim); opacity: 0.3;" />
              <span class="text-[12px]" style="color: var(--color-ide-text-dim);">
                未找到符号
              </span>
            </div>
            <div
              v-for="(sym, idx) in filteredSymbols"
              :key="`${sym.line}-${sym.name}`"
              class="goto-symbol-item flex items-center gap-2.5 px-3 py-1.5 cursor-pointer"
              :style="{
                color: idx === selectedIndex ? 'var(--color-ide-text)' : 'var(--color-ide-text-dim)',
                background: idx === selectedIndex ? 'var(--color-ide-surface-active)' : 'transparent',
                fontSize: '13px',
                lineHeight: '22px',
                borderLeft: idx === selectedIndex ? `2px solid var(--color-ide-accent)` : '2px solid transparent',
              }"
              @click="selectSymbol(sym)"
              @mouseenter="selectedIndex = idx"
            >
              <!-- 图标 -->
              <component
                :is="getKindIcon(sym.kind)"
                :size="14"
                style="flex-shrink: 0;"
                :color="getKindColor(sym.kind)"
              />
              <!-- 符号名 -->
              <span class="font-medium truncate" :style="{ color: getKindColor(sym.kind) }">
                {{ sym.name }}
              </span>
              <!-- 容器 -->
              <span
                v-if="sym.container"
                class="text-[11px] truncate opacity-50"
                style="color: var(--color-ide-text-dim);"
              >
                in {{ sym.container }}
              </span>
              <span class="flex-1" />
              <!-- 行号 -->
              <span class="text-[11px] opacity-40 flex-shrink-0" style="color: var(--color-ide-text-dim);">
                行 {{ sym.line }}
              </span>
            </div>
          </div>

          <!-- 底部提示 -->
          <div
            class="flex items-center px-3 shrink-0 gap-4 text-[10px]"
            style="
              height: '24px';
              color: var(--color-ide-text-dim);
              borderTop: '1px solid var(--color-ide-border)';
            "
          >
            <span>↑↓ 导航</span>
            <span>↵ 跳转</span>
            <span>esc 关闭</span>
            <span class="flex-1" />
            <span>Ctrl+Shift+O</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.goto-symbol-item:hover {
  background: var(--color-ide-surface-hover) !important;
}
</style>
