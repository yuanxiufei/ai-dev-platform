<script setup lang="ts">
/**
 * VSCode Outline Panel — 文档大纲（符号树）
 *
 * 对标 VSCode outlinePane，从 Monaco 模型获取文档符号
 * 支持: 函数/类/接口/方法/变量/常量/类型/枚举/模块 等符号
 * 语言: JS/TS/TSX/Vue/Python/Go/Rust/HTML/CSS/JSON 等
 */
import { ArrowDown, ArrowRight, Hash, Variable, BoxSelect, Braces, Type, Puzzle, ListTree } from "lucide-vue-next"
import { computed, ref, watch } from "vue"
import { useIDEStore } from "@/stores/useIDEStore"

const store = useIDEStore()

export interface OutlineSymbol {
  name: string
  kind: SymbolKind
  lineNumber: number
  column?: number
  children?: OutlineSymbol[]
}

type SymbolKind = "function" | "class" | "method" | "variable" | "constant" | "interface" |
  "type" | "enum" | "enumMember" | "module" | "property" | "constructor" | "field"

/** 符号类型图标映射 */
const KIND_ICONS: Record<SymbolKind, any> = {
  function: BoxSelect, class: Puzzle, method: BoxSelect,
  variable: Variable, constant: Hash, interface: Type,
  type: Type, enum: ListTree, enumMember: Variable,
  module: Braces, property: Variable, constructor: BoxSelect,
  field: Variable,
}

/** 符号类型排序权重（越小越靠前） */
const KIND_ORDER: Record<SymbolKind, number> = {
  class: 0, interface: 1, type: 2, enum: 3,
  function: 100, method: 101, constructor: 102,
  module: 200, variable: 300, constant: 301,
  property: 400, field: 401, enumMember: 500,
}

// ── 状态 ──
const symbols = ref<OutlineSymbol[]>([])
const collapsedNodes = ref<Set<string>>(new Set())
const activeSymbolLine = ref<number | null>(null)

// ── 多语言 Regex 解析器 ──

/** TypeScript/JavaScript/TSX 符号正则 */
const TS_PATTERNS: { pattern: RegExp; kind: SymbolKind }[] = [
  { pattern: /^\s*export\s+(?:default\s+)?class\s+(\w+)/m, kind: "class" },
  { pattern: /^\s*export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)/m, kind: "function" },
  { pattern: /^\s*class\s+(\w+)/m, kind: "class" },
  { pattern: /^\s*interface\s+(\w+)/m, kind: "interface" },
  { pattern: /^\s*type\s+(\w+)\s*=/m, kind: "type" },
  { pattern: /^\s*enum\s+(\w+)/m, kind: "enum" },
  { pattern: /^\s*export\s+const\s+(\w+)/m, kind: "constant" },
  { pattern: /^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(/m, kind: "function" },
  { pattern: /^\s*(?:static\s+)?(?:async\s+)?(\w+)\s*\([^)]*\)\s*[:{]/m, kind: "method" },
  { pattern: /^\s*(?:let|var)\s+(\w+)/m, kind: "variable" },
  { pattern: /^\s*const\s+(\w+)/m, kind: "constant" },
  { pattern: /^\s*(\w+)\s*[=:]\s*(?:function|\(\)|class|{)/m, kind: "property" },
]

/** Python 符号正则 */
const PY_PATTERNS: { pattern: RegExp; kind: SymbolKind }[] = [
  { pattern: /^\s*class\s+(\w+)/m, kind: "class" },
  { pattern: /^\s*(?:async\s+)?def\s+(\w+)\s*\(/m, kind: "function" },
  { pattern: /^\s*(\w+)\s*[:=]\s*(?:[A-Z_][A-Z0-9_]*)/m, kind: "constant" },
  { pattern: /^\s*(\w+)\s*[:=]/m, kind: "variable" },
]

/** Go 符号正则 */
const GO_PATTERNS: { pattern: RegExp; kind: SymbolKind }[] = [
  { pattern: /^\s*type\s+(\w+)\s+struct/m, kind: "class" },
  { pattern: /^\s*type\s+(\w+)\s+interface/m, kind: "interface" },
  { pattern: /^\s*func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(/m, kind: "function" },
  { pattern: /^\s*var\s+(\w+)/m, kind: "variable" },
  { pattern: /^\s*const\s+(\w+)/m, kind: "constant" },
]

/** Rust 符号正则 */
const RS_PATTERNS: { pattern: RegExp; kind: SymbolKind }[] = [
  { pattern: /^\s*(?:pub\s+)?struct\s+(\w+)/m, kind: "class" },
  { pattern: /^\s*(?:pub\s+)?enum\s+(\w+)/m, kind: "enum" },
  { pattern: /^\s*(?:pub\s+)?trait\s+(\w+)/m, kind: "interface" },
  { pattern: /^\s*(?:pub\s+)?type\s+(\w+)/m, kind: "type" },
  { pattern: /^\s*(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*[<(]/m, kind: "function" },
  { pattern: /^\s*(?:pub\s+)?impl\s+\w+.*{/m, kind: "class" },
  { pattern: /^\s*(?:pub\s+)?(?:static\s+)?(?:const|let)\s+(?:mut\s+)?(\w+)/m, kind: "constant" },
]

/** Vue SFC 额外符号 */
const VUE_PATTERNS: { pattern: RegExp; kind: SymbolKind }[] = [
  { pattern: /^\s*(?:const|let|var)\s+(\w+)\s*=\s*defineComponent/m, kind: "function" },
  { pattern: /^\s*(?:const|let|var)\s+(\w+)\s*=\s*computed/m, kind: "function" },
  { pattern: /^\s*(?:const|let|var)\s+(\w+)\s*=\s*ref/m, kind: "variable" },
]

/** HTML/CSS 符号正则 */
const CSS_PATTERNS: { pattern: RegExp; kind: SymbolKind }[] = [
  { pattern: /^\s*(\.|#)([\w-]+)\s*{/m, kind: "class" },
  { pattern: /^\s*([\w-]+)\s*{/m, kind: "class" },
]

/** JSON 键列表 */
const JSON_KEY: RegExp = /^\s*"(\w+)"\s*:/m

/**
 * 根据文件扩展名获取解析器
 */
function getParser(filePath: string): { pattern: RegExp; kind: SymbolKind }[] {
  const ext = filePath.split(".").pop()?.toLowerCase() ?? ""
  switch (ext) {
    case "ts": case "tsx": case "js": case "jsx": case "mjs": case "cjs": return TS_PATTERNS
    case "py": case "pyw": return PY_PATTERNS
    case "go": return GO_PATTERNS
    case "rs": return RS_PATTERNS
    case "vue": return [...VUE_PATTERNS, ...TS_PATTERNS]
    case "css": case "scss": case "less": case "sass": return CSS_PATTERNS
    case "html": case "htm": return [...CSS_PATTERNS, ...TS_PATTERNS]
    case "json": return [{ pattern: JSON_KEY, kind: "property" as SymbolKind }]
    default: return TS_PATTERNS // 回退
  }
}

/**
 * 解析文档内容，提取符号树
 */
function parseOutline(code: string, filePath: string): OutlineSymbol[] {
  if (!code) return []
  const patterns = getParser(filePath)
  const lines = code.split("\n")
  const result: OutlineSymbol[] = []
  const seen = new Set<string>()

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    for (const { pattern, kind } of patterns) {
      // 重置 regex lastIndex
      const re = new RegExp(pattern.source, pattern.flags)
      const m = re.exec(line)
      if (m) {
        const name = m[1] || m[2]
        if (!name || seen.has(`${kind}:${name}:${i + 1}`)) continue
        // 过滤明显的误匹配（太短、纯数字、常见关键词）
        if (name.length < 1 || /^\d+$/.test(name) ||
          ["if", "for", "while", "return", "import", "export", "from", "as", "new",
           "throw", "try", "catch", "else", "break", "continue", "switch", "case",
           "default", "typeof", "instanceof", "in", "of", "await", "yield"].includes(name)) {
          continue
        }
        seen.add(`${kind}:${name}:${i + 1}`)
        result.push({ name, kind, lineNumber: i + 1, children: [] })
        break // 每行只匹配第一个
      }
    }
  }

  // 构建层级树：根据缩进深度
  return buildTree(result, lines)
}

/**
 * 基于缩进构建符号树
 */
function buildTree(flat: OutlineSymbol[], lines: string[]): OutlineSymbol[] {
  if (flat.length <= 1) return flat

  const getIndent = (lineNum: number) => {
    const line = lines[lineNum - 1] || ""
    const m = line.match(/^(\s*)/)
    return m ? m[1].length : 0
  }

  // 按行排序
  flat.sort((a, b) => a.lineNumber - b.lineNumber)

  const root: OutlineSymbol[] = []
  const stack: OutlineSymbol[] = []

  for (const sym of flat) {
    const indent = getIndent(sym.lineNumber)

    // 弹出比当前缩进更深或相等的节点
    while (stack.length > 0) {
      const top = stack[stack.length - 1]
      const topIndent = getIndent(top.lineNumber)
      if (topIndent < indent - 1) break // parent 比当前浅 → 保留
      stack.pop() // 同级或更深 → 弹出
    }

    if (stack.length === 0) {
      root.push(sym)
    } else {
      const parent = stack[stack.length - 1]
      if (!parent.children) parent.children = []
      parent.children.push(sym)
    }

    if (["class", "interface", "enum", "module"].includes(sym.kind)) {
      stack.push(sym)
    }
  }

  return root
}

// ── 监听 activeTab 内容变化 ──
watch(
  () => [store.activeTab?.content, store.activeTab?.filePath, store.activeTab?.id],
  () => {
    const tab = store.activeTab
    if (!tab || !tab.content) {
      symbols.value = []
      return
    }
    symbols.value = parseOutline(tab.content, tab.filePath || tab.label || "")
  },
  { immediate: true, deep: false },
)

// 监听光标位置更新高亮
watch(
  () => store.cursorPosition?.line,
  (line) => { activeSymbolLine.value = line ?? null },
)

// ── 交互 ──
function toggleCollapse(key: string): void {
  if (collapsedNodes.value.has(key)) {
    collapsedNodes.value.delete(key)
  } else {
    collapsedNodes.value.add(key)
  }
  collapsedNodes.value = new Set(collapsedNodes.value)
}

function scrollToLine(lineNumber: number): void {
  // 通过 store 暴露的方法滚动编辑器到指定行
  activeSymbolLine.value = lineNumber
  // 触发编辑器 gotoLine
  window.dispatchEvent(new CustomEvent("ide:goto-line", { detail: { line: lineNumber } }))
}

function isCollapsed(key: string): boolean {
  return collapsedNodes.value.has(key)
}

function nodeKey(sym: OutlineSymbol): string {
  return `${sym.kind}:${sym.name}:${sym.lineNumber}`
}

/** 检测当前高亮符号 */
function isActive(sym: OutlineSymbol): boolean {
  if (!activeSymbolLine.value || !store.cursorPosition?.totalLines) return false
  // 寻找包含光标位置的符号
  const nextSym = findNextSymbol(sym)
  return activeSymbolLine.value >= sym.lineNumber &&
    (nextSym ? activeSymbolLine.value < nextSym.lineNumber : true)
}

function findNextSymbol(sym: OutlineSymbol): OutlineSymbol | null {
  const all = flattenSymbols(symbols.value)
  const idx = all.findIndex(s => s === sym)
  return idx >= 0 && idx < all.length - 1 ? all[idx + 1] : null
}

function flattenSymbols(list: OutlineSymbol[]): OutlineSymbol[] {
  const result: OutlineSymbol[] = []
  for (const s of list) {
    result.push(s)
    if (s.children?.length) result.push(...flattenSymbols(s.children))
  }
  return result
}

// ── 查找当前活动符号（最靠近光标的） ──
const highlightedSymbol = computed(() => {
  if (!activeSymbolLine.value) return null
  const all = flattenSymbols(symbols.value).sort((a, b) => a.lineNumber - b.lineNumber)
  for (let i = all.length - 1; i >= 0; i--) {
    if (all[i].lineNumber <= activeSymbolLine.value) return all[i]
  }
  return null
})

/** 总数统计 */
const totalSymbols = computed(() => flattenSymbols(symbols.value).length)
</script>

<template>
  <div class="outline-panel h-full flex flex-col text-[12px]"
    style="color: var(--color-ide-text-dim);">
    <!-- Header -->
    <div class="flex items-center justify-between px-3 shrink-0"
      style="height: 28px; border-bottom: 1px solid var(--color-ide-border); font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px;">
      <span>大纲</span>
      <span style="font-size: 10px; opacity: 0.5;">{{ totalSymbols }} 符号</span>
    </div>

    <!-- Symbol Tree -->
    <div v-if="symbols.length > 0" class="flex-1 overflow-y-auto overflow-x-hidden py-1 outline-tree">
      <OutlineNode
        v-for="sym in symbols"
        :key="nodeKey(sym)"
        :sym="sym"
        :depth="0"
        :active="isActive(sym)"
        :collapsed="isCollapsed(nodeKey(sym))"
        @toggle="toggleCollapse(nodeKey(sym))"
        @click="scrollToLine(sym.lineNumber)"
      />
    </div>

    <!-- Empty state -->
    <div v-else class="flex-1 flex flex-col items-center justify-center text-center px-4 gap-1 opacity-40">
      <ListTree :size="20" />
      <p class="text-[11px]">无符号</p>
      <p class="text-[10px]">打开支持的源文件以查看其大纲</p>
    </div>
  </div>
</template>

<!-- ═══ 递归子组件：OutlineNode ═══ -->
<script lang="ts">
import { defineComponent, h, type PropType } from "vue"

export const OutlineNode = defineComponent({
  name: "OutlineNode",
  props: {
    sym: { type: Object as PropType<OutlineSymbol>, required: true },
    depth: { type: Number, default: 0 },
    active: { type: Boolean, default: false },
    collapsed: { type: Boolean, default: false },
  },
  emits: ["toggle", "click"],
  setup(props, { emit }) {
    const icons = {
      function: BoxSelect, class: Puzzle, method: BoxSelect,
      variable: Variable, constant: Hash, interface: Type,
      type: Type, enum: ListTree, enumMember: Variable,
      module: Braces, property: Variable, constructor: BoxSelect,
      field: Variable,
    }
    const indentLeft = props.depth * 12
    const hasChildren = props.sym.children && props.sym.children.length > 0

    return () => {
      const children: any[] = []

      // 渲染节点自身
      const iconComp = icons[props.sym.kind] || Variable
      const colorMap: Record<string, string> = {
        class: "#60A5FA", function: "#C084FC", method: "#C084FC",
        interface: "#38BDF8", type: "#38BDF8", enum: "#F59E0B",
        constant: "#34D399", variable: "#4ADE80", property: "#4ADE80",
        module: "#FB923C", constructor: "#C084FC", field: "#4ADE80", enumMember: "#34D399",
      }

      children.push(
        h("div", {
          class: `outline-node-item ${props.active ? "active" : ""}`,
          style: {
            display: "flex", alignItems: "center", height: "22px",
            paddingLeft: `${indentLeft + 8}px`, paddingRight: "8px",
            cursor: "pointer", fontSize: "12px",
            backgroundColor: props.active ? "var(--color-ide-surface-active)" : "transparent",
            color: props.active ? "var(--color-ide-text)" : "var(--color-ide-text-dim)",
            transition: "background-color 0.1s",
          },
          onClick: () => emit("click"),
          onMouseenter: (e: MouseEvent) => {
            if (!props.active) (e.currentTarget as HTMLElement).style.backgroundColor = "var(--color-ide-surface-hover)"
          },
          onMouseleave: (e: MouseEvent) => {
            if (!props.active) (e.currentTarget as HTMLElement).style.backgroundColor = "transparent"
          },
        }, [
          // 展开/折叠 箭头
          hasChildren
            ? h(props.collapsed ? ArrowRight : ArrowDown, {
              size: 10,
              style: { marginRight: "4px", flexShrink: 0, cursor: "pointer" },
              onClick: (e: Event) => { e.stopPropagation(); emit("toggle") },
            })
            : h("span", { style: { width: "14px" } }),
          // 图标
          h(iconComp, {
            size: 14,
            style: {
              marginRight: "4px", flexShrink: 0,
              color: colorMap[props.sym.kind] || "#9CA3AF",
            },
          }),
          // 名称
          h("span", {
            style: {
              overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
              flex: 1, fontSize: "12px",
              fontWeight: props.active ? 500 : 400,
            },
          }, props.sym.name),
          // 行号
          h("span", {
            style: {
              fontSize: "10px", opacity: 0.4, marginLeft: "6px", flexShrink: 0,
              fontFamily: "monospace",
            },
          }, `:${props.sym.lineNumber}`),
        ]),
      )

      // 递归渲染子节点
      if (hasChildren && !props.collapsed) {
        for (const child of (props.sym.children || [])) {
          children.push(
            h(OutlineNode, {
              sym: child,
              depth: props.depth + 1,
              active: false,
              collapsed: false,
              onToggle: () => {},
              onClick: () => emit("click"),
            }),
          )
        }
      }

      return h("div", { style: { lineHeight: "22px" } }, children)
    }
  },
})
</script>

<style scoped>
.outline-node-item:hover {
  background-color: var(--color-ide-surface-hover);
}
.outline-node-item.active {
  background-color: var(--color-ide-surface-active);
  color: var(--color-ide-text);
}
.outline-tree::-webkit-scrollbar {
  width: 6px;
}
.outline-tree::-webkit-scrollbar-thumb {
  background: var(--color-ide-border);
  border-radius: 3px;
}
</style>
