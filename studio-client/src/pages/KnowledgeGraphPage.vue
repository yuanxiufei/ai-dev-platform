<script setup lang="ts">
import { computed, onMounted, ref } from "vue"
import { RefreshCw, GitGraph, Search, X, ZoomIn, ZoomOut, Maximize2 } from "lucide-vue-next"
import {
  type BacklinkItem,
  type GraphEdge,
  type GraphNode,
  kgApi,
} from "@/api/model-features"

// ── Reactive state ──────────────────────────────────────
const viewMode = ref<"graph" | "backlinks" | "parse" | "stats">("graph")
const loading = ref(false)
const error = ref("")

const graphData = ref<{
  nodes: GraphNode[]
  edges: GraphEdge[]
  node_count: number
  edge_count: number
}>({ nodes: [], edges: [], node_count: 0, edge_count: 0 })

const backlinks = ref<BacklinkItem[]>([])
const stats = ref<any>(null)
const parseKey = ref("")
const parseResult = ref<any>(null)
const parseLoading = ref(false)

// ── Graph interaction ───────────────────────────────────
const selectedNode = ref<GraphNode | null>(null)
const graphSearch = ref("")
const graphZoom = ref(1)

// ── Data fetching ───────────────────────────────────────
async function refreshAll() {
  loading.value = true
  error.value = ""
  try {
    const [gd, bl, st] = await Promise.all([
      kgApi.graphData().catch(() => null),
      kgApi.backlinks().catch(() => null),
      kgApi.stats().catch(() => null),
    ])
    if (gd) graphData.value = gd.data
    if (bl) backlinks.value = bl.data.backlinks || []
    if (st) stats.value = st.data
  } catch (e: any) {
    error.value = e?.message || "加载失败"
  } finally {
    loading.value = false
  }
}

async function doParse() {
  if (!parseKey.value.trim()) return
  parseLoading.value = true
  parseResult.value = null
  try {
    parseResult.value = (await kgApi.parse(parseKey.value.trim())).data
  } catch {
    parseResult.value = { error: "解析失败" }
  } finally {
    parseLoading.value = false
  }
}

// ── Filtered nodes & edges ─────────────────────────────
const filteredGraph = computed(() => {
  let nodes = graphData.value.nodes || []
  const edges = graphData.value.edges || []

  if (graphSearch.value.trim()) {
    const q = graphSearch.value.trim().toLowerCase()
    nodes = nodes.filter(
      (n) =>
        n.id.toLowerCase().includes(q) ||
        n.label.toLowerCase().includes(q) ||
        (n.domain || "").toLowerCase().includes(q),
    )
  }

  const nodeIds = new Set(nodes.map((n) => n.id))
  const filteredEdges = edges.filter(
    (e) => nodeIds.has(e.from) && nodeIds.has(e.to),
  )

  return { nodes, edges: filteredEdges }
})

// ── SVG layout ──────────────────────────────────────────
const graphLayout = computed(() => {
  const nodes = filteredGraph.value.nodes
  const edges = filteredGraph.value.edges
  const cols = Math.max(Math.ceil(Math.sqrt(Math.max(nodes.length, 1))), 2)
  const cellW = 170
  const cellH = 80
  const gap = 36

  const nodeMap: Record<string, number> = {}
  const ln = nodes.map((n, i) => {
    nodeMap[n.id] = i
    return {
      ...n,
      x: (i % cols) * (cellW + gap) + gap,
      y: Math.floor(i / cols) * (cellH + gap) + gap,
      w: cellW,
      h: cellH,
    }
  })

  const le = edges.map((e) => {
    const fi = nodeMap[e.from]
    const ti = nodeMap[e.to]
    if (fi === undefined || ti === undefined) return null
    const fx = (fi % cols) * (cellW + gap) + gap + cellW
    const fy = Math.floor(fi / cols) * (cellH + gap) + gap + cellH / 2
    const tx = (ti % cols) * (cellW + gap) + gap
    const ty = Math.floor(ti / cols) * (cellH + gap) + gap + cellH / 2
    return { x1: fx, y1: fy, x2: tx, y2: ty }
  }).filter(Boolean) as { x1: number; y1: number; x2: number; y2: number }[]

  return { nodes: ln, edges: le }
})

const svgViewBox = computed(() => {
  const n = Math.max(filteredGraph.value.nodes.length, 1)
  const cols = Math.max(Math.ceil(Math.sqrt(n)), 2)
  const rows = Math.max(Math.ceil(n / cols), 1)
  const w = cols * 206 + 36
  const h = rows * 116 + 36
  return `0 0 ${w} ${h}`
})

// ── Node color ──────────────────────────────────────────
function nodeColor(importance: number): string {
  if (importance >= 0.8) return "#ef4444"
  if (importance >= 0.5) return "#f59e0b"
  if (importance >= 0.3) return "#3b82f6"
  return "#10b981"
}

function nodeColorBg(importance: number): string {
  if (importance >= 0.8) return "rgba(239,68,68,0.15)"
  if (importance >= 0.5) return "rgba(245,158,11,0.15)"
  if (importance >= 0.3) return "rgba(59,130,246,0.15)"
  return "rgba(16,185,129,0.15)"
}

// ── Domain color map ────────────────────────────────────
const domainColors: Record<string, string> = {}
const domainPalette = [
  "#6366f1", "#ec4899", "#14b8a6", "#f97316", "#8b5cf6",
  "#06b6d4", "#e11d48", "#22c55e", "#eab308", "#3b82f6",
]

function domainColor(domain: string): string {
  if (!domainColors[domain]) {
    const keys = Object.keys(domainColors)
    domainColors[domain] = domainPalette[keys.length % domainPalette.length]
  }
  return domainColors[domain]
}

// ── Zoom handlers ───────────────────────────────────────
function zoomIn() {
  graphZoom.value = Math.min(graphZoom.value + 0.15, 2.5)
}
function zoomOut() {
  graphZoom.value = Math.max(graphZoom.value - 0.15, 0.3)
}
function resetZoom() {
  graphZoom.value = 1
}

// ── Helpers ─────────────────────────────────────────────
function truncate(s: string, max: number): string {
  return s.length > max ? s.slice(0, max) + "…" : s
}

onMounted(refreshAll)
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto space-y-6">
    <!-- Header -->
    <header class="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-3xl font-bold text-white">知识图谱</h1>
        <p class="text-[var(--color-ide-text-dim)] mt-1 text-sm">Memory 关系图 · 反向链接 · 解析 · 统计</p>
      </div>
      <div class="flex gap-2 items-center">
        <select
          v-model="viewMode"
          class="bg-gray-800 border border-gray-700/50 rounded-xl px-3 py-2 text-sm text-[var(--color-ide-text)] outline-none focus:border-brand-500/50"
        >
          <option value="graph">图谱视图</option>
          <option value="backlinks">反向链接</option>
          <option value="parse">解析器</option>
          <option value="stats">统计</option>
        </select>
        <button
          @click="refreshAll"
          :disabled="loading"
          class="p-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-[var(--color-ide-text)] text-sm transition disabled:opacity-50"
          title="刷新"
        >
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': loading }" />
        </button>
      </div>
    </header>

    <!-- Error banner -->
    <div
      v-if="error"
      class="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-2"
    >
      <X class="w-4 h-4 shrink-0" />
      {{ error }}
      <button @click="error = ''" class="ml-auto text-red-300 hover:text-red-200">&times;</button>
    </div>

    <!-- Stat cards -->
    <div v-if="stats" class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3">
      <div class="p-3 rounded-xl bg-gray-900/50 border border-gray-800/50 text-center">
        <span class="block text-xl font-bold text-green-400">{{ stats.total_memories ?? 0 }}</span>
        <span class="text-xs text-[var(--color-ide-text-dim)]">记忆总数</span>
      </div>
      <div class="p-3 rounded-xl bg-gray-900/50 border border-gray-800/50 text-center">
        <span class="block text-xl font-bold text-brand-400">{{ stats.total_links ?? 0 }}</span>
        <span class="text-xs text-[var(--color-ide-text-dim)]">链接数</span>
      </div>
      <div class="p-3 rounded-xl bg-gray-900/50 border border-gray-800/50 text-center">
        <span class="block text-xl font-bold text-purple-400">{{ stats.total_backlinks ?? 0 }}</span>
        <span class="text-xs text-[var(--color-ide-text-dim)]">反向链接</span>
      </div>
      <div class="p-3 rounded-xl bg-gray-900/50 border border-gray-800/50 text-center">
        <span class="block text-xl font-bold text-amber-400">{{ stats.orphans ?? 0 }}</span>
        <span class="text-xs text-[var(--color-ide-text-dim)]">孤立节点</span>
      </div>
      <div class="p-3 rounded-xl bg-gray-900/50 border border-gray-800/50 text-center">
        <span class="block text-xl font-bold text-cyan-400">{{ stats.most_linked?.length ?? 0 }}</span>
        <span class="text-xs text-[var(--color-ide-text-dim)]">热门节点</span>
      </div>
      <div v-if="stats.graph_density !== undefined" class="p-3 rounded-xl bg-gray-900/50 border border-gray-800/50 text-center">
        <span class="block text-xl font-bold text-pink-400">{{ (stats.graph_density * 100).toFixed(1) }}%</span>
        <span class="text-xs text-[var(--color-ide-text-dim)]">图密度</span>
      </div>
    </div>

    <!-- ═══════════ GRAPH VIEW ═══════════ -->
    <div v-if="viewMode === 'graph'" class="space-y-4">
      <!-- Toolbar -->
      <div class="flex items-center gap-3 flex-wrap">
        <div class="relative flex-1 max-w-xs">
          <Search class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-ide-text-dim)]" />
          <input
            v-model="graphSearch"
            placeholder="搜索节点…"
            class="w-full bg-gray-900/50 border border-gray-800/50 rounded-xl pl-9 pr-3 py-2 text-sm text-[var(--color-ide-text)] outline-none focus:border-brand-500/50"
          />
          <button
            v-if="graphSearch"
            @click="graphSearch = ''"
            class="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]"
          >
            <X class="w-3.5 h-3.5" />
          </button>
        </div>
        <div class="flex items-center gap-1 bg-gray-900/50 rounded-xl border border-gray-800/50 p-0.5">
          <button @click="zoomOut" class="p-1.5 rounded-lg hover:bg-gray-800 text-[var(--color-ide-text-dim)]" title="缩小">
            <ZoomOut class="w-4 h-4" />
          </button>
          <button @click="resetZoom" class="px-2 py-1 text-xs text-[var(--color-ide-text-dim)] font-mono min-w-[3rem]">
            {{ (graphZoom * 100).toFixed(0) }}%
          </button>
          <button @click="zoomIn" class="p-1.5 rounded-lg hover:bg-gray-800 text-[var(--color-ide-text-dim)]" title="放大">
            <ZoomIn class="w-4 h-4" />
          </button>
          <button @click="resetZoom" class="p-1.5 rounded-lg hover:bg-gray-800 text-[var(--color-ide-text-dim)]" title="重置">
            <Maximize2 class="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <!-- Empty state -->
      <div
        v-if="!filteredGraph.nodes?.length"
        class="bg-gray-900/50 rounded-2xl p-6 border border-gray-800/50 text-center py-20"
      >
        <GitGraph class="w-14 h-14 mx-auto mb-4 text-[var(--color-ide-text-dim)]" />
        <p class="text-[var(--color-ide-text-dim)] font-medium">还没有知识图谱数据</p>
        <p class="text-sm text-[var(--color-ide-text-dim)] mt-1">在记忆中使用 <code class="px-1.5 py-0.5 bg-gray-800 rounded text-green-400 text-xs">[[key]]</code> 创建链接关系</p>
      </div>

      <!-- SVG graph -->
      <div
        v-else
        class="bg-gray-900/50 rounded-2xl p-4 border border-gray-800/50 overflow-auto"
        style="max-height: 75vh"
      >
        <svg
          :viewBox="svgViewBox"
          class="w-full"
          :style="{ minWidth: '600px', transform: `scale(${graphZoom})`, transformOrigin: 'top center' }"
        >
          <defs>
            <marker id="arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="#8b5cf6" />
            </marker>
            <filter id="node-shadow">
              <feDropShadow dx="0" dy="1" stdDeviation="2" flood-opacity="0.3" />
            </filter>
          </defs>

          <!-- Edges -->
          <g v-for="(e, i) in graphLayout.edges" :key="'e' + i">
            <line
              :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
              stroke="#8b5cf6" stroke-width="1.5" opacity="0.35"
              marker-end="url(#arrow)"
            />
          </g>

          <!-- Nodes -->
          <g
            v-for="n in graphLayout.nodes"
            :key="n.id"
            class="cursor-pointer"
            @click="selectedNode = selectedNode?.id === n.id ? null : n"
          >
            <rect
              :x="n.x" :y="n.y" :width="n.w" :height="n.h"
              rx="10"
              :fill="nodeColorBg(n.importance)"
              :stroke="selectedNode?.id === n.id ? '#a78bfa' : nodeColor(n.importance)"
              :stroke-width="selectedNode?.id === n.id ? 2.5 : 1.5"
              filter="url(#node-shadow)"
            />
            <text
              :x="n.x + 12" :y="n.y + 22"
              font-size="12" font-weight="700" fill="#e5e7eb"
            >
              {{ truncate(n.label, 16) }}
            </text>
            <text
              :x="n.x + 12" :y="n.y + 40"
              font-size="10" fill="rgba(255,255,255,0.45)"
            >
              {{ n.domain || "—" }}
            </text>
            <text
              :x="n.x + n.w - 24" :y="n.y + 22"
              font-size="10" text-anchor="end"
              :fill="nodeColor(n.importance)"
              font-weight="600"
            >
              {{ (n.importance * 100).toFixed(0) }}%
            </text>
          </g>
        </svg>
      </div>

      <!-- Node detail panel -->
      <div
        v-if="selectedNode"
        class="bg-gray-900/50 rounded-xl p-4 border border-purple-500/20 flex gap-4 items-start"
      >
        <div class="shrink-0 w-10 h-10 rounded-lg flex items-center justify-center text-white text-xs font-bold" :style="{ background: nodeColor(selectedNode.importance) }">
          {{ selectedNode.label.charAt(0).toUpperCase() }}
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <span class="font-semibold text-white text-sm">{{ selectedNode.label }}</span>
            <span class="text-xs px-1.5 py-0.5 rounded-full bg-gray-800 text-[var(--color-ide-text-dim)] font-mono">{{ selectedNode.id }}</span>
          </div>
          <div class="flex items-center gap-3 text-xs text-[var(--color-ide-text-dim)]">
            <span>领域: <span class="text-[var(--color-ide-text)]">{{ selectedNode.domain || "—" }}</span></span>
            <span>重要性: <span class="font-mono" :style="{ color: nodeColor(selectedNode.importance) }">{{ (selectedNode.importance * 100).toFixed(0) }}%</span></span>
          </div>
        </div>
        <button @click="selectedNode = null" class="text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] p-1">
          <X class="w-4 h-4" />
        </button>
      </div>
    </div>

    <!-- ═══════════ BACKLINKS VIEW ═══════════ -->
    <div v-if="viewMode === 'backlinks'" class="space-y-2">
      <div v-if="!backlinks.length" class="text-center py-16 text-[var(--color-ide-text-dim)]">
        <p class="font-medium">暂无反向链接</p>
        <p class="text-sm mt-1">创建包含 <code class="px-1.5 py-0.5 bg-gray-800 rounded text-green-400 text-xs">[[key]]</code> 的记忆即可生成反向链接</p>
      </div>
      <div
        v-for="bl in backlinks"
        :key="bl.target_key"
        class="bg-gray-900/50 rounded-xl p-4 border border-gray-800/50 hover:border-gray-700/50 transition"
      >
        <div class="flex items-center justify-between mb-3">
          <div class="flex items-center gap-2">
            <div
              class="w-2.5 h-2.5 rounded-full"
              :style="{ background: domainColor(bl.target_key) }"
            />
            <span class="text-sm font-mono font-bold text-green-400">{{ bl.target_key }}</span>
          </div>
          <span class="text-xs px-2 py-0.5 rounded-full bg-green-500/10 text-green-400 font-medium">
            {{ bl.source_count }} 条引用
          </span>
        </div>
        <div class="flex flex-wrap gap-1.5">
          <span
            v-for="s in bl.sources"
            :key="s"
            class="text-xs px-2 py-1 rounded-md bg-gray-800 text-[var(--color-ide-text-dim)] font-mono hover:bg-gray-700 hover:text-[var(--color-ide-text)] cursor-default transition"
          >
            [[{{ s }}]]
          </span>
        </div>
      </div>
    </div>

    <!-- ═══════════ PARSE VIEW ═══════════ -->
    <div v-if="viewMode === 'parse'" class="space-y-4">
      <div class="flex gap-2">
        <input
          v-model="parseKey"
          @keyup.enter="doParse"
          class="flex-1 bg-gray-900/50 border border-gray-800/50 rounded-xl px-4 py-3 text-sm text-[var(--color-ide-text)] outline-none focus:border-brand-500/50"
          placeholder="输入记忆 key 解析 (如 frontend-setup)…"
        />
        <button
          @click="doParse"
          :disabled="parseLoading || !parseKey.trim()"
          class="px-5 py-3 rounded-xl bg-brand-500 hover:bg-brand-600 text-white font-medium text-sm disabled:opacity-50 transition"
        >
          {{ parseLoading ? "解析中…" : "解析" }}
        </button>
      </div>

      <!-- Result -->
      <div
        v-if="parseResult"
        class="bg-gray-900/50 rounded-xl p-5 border border-gray-800/50 space-y-4"
      >
        <!-- Frontmatter -->
        <div v-if="parseResult.frontmatter?.title || parseResult.frontmatter?.tags?.length" class="space-y-2">
          <h3 class="text-xs font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-wider">Frontmatter</h3>
          <div v-if="parseResult.frontmatter.title" class="text-sm text-[var(--color-ide-text)] font-medium">📄 {{ parseResult.frontmatter.title }}</div>
          <div v-if="parseResult.frontmatter.tags?.length" class="flex flex-wrap gap-1">
            <span v-for="t in parseResult.frontmatter.tags" :key="t" class="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-[var(--color-ide-text)]">#{{ t }}</span>
          </div>
          <div v-if="parseResult.frontmatter.status" class="text-xs text-[var(--color-ide-text-dim)]">
            状态: <span class="text-[var(--color-ide-text)]">{{ parseResult.frontmatter.status }}</span>
            <span v-if="parseResult.frontmatter.priority" class="ml-3">优先级: <span class="text-[var(--color-ide-text)]">{{ parseResult.frontmatter.priority }}</span></span>
          </div>
        </div>

        <!-- Wikilinks -->
        <div v-if="parseResult.wikilinks?.length">
          <h3 class="text-xs font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-2">Wikilinks ({{ parseResult.wikilinks.length }})</h3>
          <div class="flex flex-wrap gap-1.5">
            <span
              v-for="wl in parseResult.wikilinks"
              :key="wl.target"
              class="text-xs px-2 py-1 rounded-md bg-blue-500/10 text-blue-400 font-mono hover:bg-blue-500/20 cursor-pointer transition"
            >
              [[{{ wl.target }}]]<span v-if="wl.heading" class="text-blue-500/50">#{{ wl.heading }}</span>
            </span>
          </div>
        </div>

        <!-- Tags -->
        <div v-if="parseResult.tags?.length">
          <h3 class="text-xs font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-2">标签</h3>
          <div class="flex flex-wrap gap-1.5">
            <span v-for="t in parseResult.tags" :key="t" class="text-xs px-2 py-1 rounded-full bg-gray-800 text-[var(--color-ide-text)]">#{{ t }}</span>
          </div>
        </div>

        <!-- Callouts -->
        <div v-if="parseResult.callouts?.length">
          <h3 class="text-xs font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-2">Callouts ({{ parseResult.callout_count }})</h3>
          <div
            v-for="(c, i) in parseResult.callouts.slice(0, 3)"
            :key="i"
            class="bg-gray-800/50 rounded-lg p-3 border-l-2"
            :style="{ borderColor: c.type === 'warning' ? '#f59e0b' : c.type === 'error' ? '#ef4444' : c.type === 'info' ? '#3b82f6' : '#10b981' }"
          >
            <div class="text-xs font-semibold text-[var(--color-ide-text)] mb-1">{{ c.title || c.type }}</div>
            <div class="text-xs text-[var(--color-ide-text-dim)]">{{ c.content }}</div>
          </div>
        </div>

        <!-- Plain text -->
        <div v-if="parseResult.plain_text">
          <h3 class="text-xs font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-2">纯文本</h3>
          <pre class="text-xs text-[var(--color-ide-text-dim)] whitespace-pre-wrap max-h-56 overflow-auto bg-gray-800/50 rounded-lg p-3">{{ parseResult.plain_text }}</pre>
        </div>

        <div v-if="parseResult.error" class="text-sm text-red-400 bg-red-500/5 rounded-lg p-3">
          {{ parseResult.error }}
        </div>
      </div>
    </div>

    <!-- ═══════════ STATS VIEW ═══════════ -->
    <div v-if="viewMode === 'stats'" class="space-y-4">
      <!-- Most linked -->
      <div v-if="stats?.most_linked?.length" class="bg-gray-900/50 rounded-xl p-5 border border-gray-800/50">
        <h3 class="text-sm font-semibold text-white mb-4">最常被链接的节点</h3>
        <div class="space-y-2">
          <div
            v-for="(ml, i) in stats.most_linked"
            :key="ml.key"
            class="flex items-center gap-3"
          >
            <span class="text-xs text-[var(--color-ide-text-dim)] w-5 text-right font-mono">{{ i + 1 }}</span>
            <span class="text-sm font-mono text-green-400 w-44 truncate" :title="ml.key">{{ ml.key }}</span>
            <div class="flex-1 h-5 bg-gray-800 rounded-full overflow-hidden">
              <div
                class="h-full rounded-full bg-gradient-to-r from-purple-500/50 to-purple-400/30 transition-all duration-500"
                :style="{ width: ((ml.count / (stats.most_linked[0]?.count || 1)) * 100) + '%' }"
              />
            </div>
            <span class="text-xs text-[var(--color-ide-text-dim)] w-10 text-right font-mono font-medium">{{ ml.count }}</span>
          </div>
        </div>
      </div>

      <!-- Domains -->
      <div v-if="stats?.domains && Object.keys(stats.domains).length" class="bg-gray-900/50 rounded-xl p-5 border border-gray-800/50">
        <h3 class="text-sm font-semibold text-white mb-4">按领域分布</h3>
        <div class="flex flex-wrap gap-2">
          <span
            v-for="(count, domain) in stats.domains"
            :key="domain"
            class="px-3 py-1.5 rounded-lg border text-sm flex items-center gap-2"
            :style="{ background: domainColor(domain as string) + '15', borderColor: domainColor(domain as string) + '30' }"
          >
            <span
              class="w-2 h-2 rounded-full shrink-0"
              :style="{ background: domainColor(domain as string) }"
            />
            <span class="font-mono text-[var(--color-ide-text)]">{{ domain }}</span>
            <span class="text-xs text-[var(--color-ide-text-dim)]">{{ count }}</span>
          </span>
        </div>
      </div>

      <!-- Orphans -->
      <div v-if="stats?.orphan_keys?.length" class="bg-gray-900/50 rounded-xl p-5 border border-gray-800/50">
        <h3 class="text-sm font-semibold text-white mb-3">孤立节点 ({{ stats.orphans }})</h3>
        <div class="flex flex-wrap gap-1.5">
          <span
            v-for="k in stats.orphan_keys.slice(0, 30)"
            :key="k"
            class="text-xs px-2 py-1 rounded-md bg-amber-500/10 text-amber-400/80 font-mono"
          >
            {{ k }}
          </span>
          <span v-if="stats.orphan_keys.length > 30" class="text-xs text-[var(--color-ide-text-dim)] self-center">+{{ stats.orphan_keys.length - 30 }} more</span>
        </div>
      </div>
    </div>
  </div>
</template>
