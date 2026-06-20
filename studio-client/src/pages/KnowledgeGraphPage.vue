<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { kgApi, type GraphNode, type GraphEdge, type BacklinkItem } from '@/api/model-features'
import { GitGraph, Search, RefreshCw } from 'lucide-vue-next'

const viewMode = ref<'graph' | 'backlinks' | 'parse' | 'stats'>('graph')
const graphData = ref<{ nodes: GraphNode[]; edges: GraphEdge[]; node_count: number; edge_count: number }>({ nodes: [], edges: [], node_count: 0, edge_count: 0 })
const backlinks = ref<BacklinkItem[]>([])
const stats = ref<any>(null)
const parseKey = ref('')
const parseResult = ref<any>(null)

async function refreshAll() {
  try {
    const [gd, bl, st] = await Promise.all([
      kgApi.graphData().catch(() => null),
      kgApi.backlinks().catch(() => null),
      kgApi.stats().catch(() => null),
    ])
    if (gd) graphData.value = gd.data
    if (bl) backlinks.value = bl.data.backlinks || []
    if (st) stats.value = st.data
  } catch {}
}

async function doParse() {
  if (!parseKey.value) return
  try { parseResult.value = (await kgApi.parse(parseKey.value)).data }
  catch { parseResult.value = null }
}

const graphLayout = computed(() => {
  const nodes = graphData.value.nodes || []
  const edges = graphData.value.edges || []
  const cols = Math.ceil(Math.sqrt(nodes.length)) || 3
  const cellW = 160; const cellH = 70; const gap = 30
  const nodeMap: Record<string, number> = {}
  const ln = nodes.map((n, i) => { nodeMap[n.id] = i; return { ...n, x: (i % cols) * (cellW + gap) + gap, y: Math.floor(i / cols) * (cellH + gap) + gap, w: cellW, h: cellH } })
  const le = edges.map(e => ({
    x1: nodeMap[e.from] !== undefined ? (nodeMap[e.from] % cols) * (cellW + gap) + gap + cellW : 0,
    y1: nodeMap[e.from] !== undefined ? Math.floor(nodeMap[e.from] / cols) * (cellH + gap) + gap + cellH / 2 : 0,
    x2: nodeMap[e.to] !== undefined ? (nodeMap[e.to] % cols) * (cellW + gap) + gap : 0,
    y2: nodeMap[e.to] !== undefined ? Math.floor(nodeMap[e.to] / cols) * (cellH + gap) + gap + cellH / 2 : 0,
  }))
  return { nodes: ln, edges: le }
})

const svgViewBox = computed(() => {
  const n = graphData.value.nodes?.length || 1
  const cols = Math.ceil(Math.sqrt(n)) || 1
  const rows = Math.ceil(n / cols) || 1
  return `0 0 ${cols * 190 + 30} ${rows * 100 + 30}`
})

function nodeColor(importance: number) {
  if (importance >= 0.8) return '#E74C3C'
  if (importance >= 0.5) return '#E67E22'
  if (importance >= 0.3) return '#3498DB'
  return '#2ECC71'
}

onMounted(refreshAll)
</script>

<template>
  <div class="p-6 max-w-5xl mx-auto space-y-6">
    <header class="flex items-center justify-between">
      <div>
        <h1 class="text-3xl font-bold text-white">知识图谱</h1>
        <p class="text-gray-400 mt-2">Wikilinks 关系图 · 反向链接 · 统计分析</p>
      </div>
      <div class="flex gap-2">
        <select v-model="viewMode" class="bg-gray-800 border border-gray-700/50 rounded-xl px-3 py-2 text-sm text-gray-200 outline-none">
          <option value="graph">图谱视图</option>
          <option value="backlinks">反向链接</option>
          <option value="parse">解析器</option>
          <option value="stats">统计</option>
        </select>
        <button @click="refreshAll" class="px-3 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm transition"><RefreshCw class="w-4 h-4" /></button>
      </div>
    </header>

    <div v-if="stats" class="grid grid-cols-3 md:grid-cols-5 gap-3">
      <div class="p-3 rounded-xl bg-gray-900/50 border border-gray-800/50 text-center"><span class="block text-xl font-bold text-green-400">{{ stats.total_memories }}</span><span class="text-xs text-gray-500">记忆</span></div>
      <div class="p-3 rounded-xl bg-gray-900/50 border border-gray-800/50 text-center"><span class="block text-xl font-bold text-brand-400">{{ stats.total_links }}</span><span class="text-xs text-gray-500">链接</span></div>
      <div class="p-3 rounded-xl bg-gray-900/50 border border-gray-800/50 text-center"><span class="block text-xl font-bold text-purple-400">{{ stats.most_linked?.length || 0 }}</span><span class="text-xs text-gray-500">热门节点</span></div>
    </div>

    <!-- Graph -->
    <div v-if="viewMode === 'graph'" class="bg-gray-900/50 rounded-2xl p-6 border border-gray-800/50">
      <div v-if="!graphData.nodes?.length" class="text-center py-16 text-gray-500">
        <GitGraph class="w-12 h-12 mx-auto mb-3 text-gray-600" />
        <p>还没有知识图谱数据</p>
        <p class="text-sm">在记忆中使用 [[key]] 创建链接关系</p>
      </div>
      <svg v-else :viewBox="svgViewBox" class="w-full">
        <defs><marker id="arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#9B59B6" /></marker></defs>
        <line v-for="(e, i) in graphLayout.edges" :key="'e'+i" :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2" stroke="#9B59B6" stroke-width="1.5" opacity="0.4" marker-end="url(#arrow)" />
        <g v-for="(n, i) in graphLayout.nodes" :key="n.id">
          <rect :x="n.x" :y="n.y" :width="n.w" :height="n.h" rx="8" :fill="nodeColor(n.importance)" opacity="0.85" stroke="#fff" stroke-width="1.5" />
          <text :x="n.x + 10" :y="n.y + 22" font-size="12" font-weight="600" fill="#fff">{{ n.label.length > 14 ? n.label.slice(0,14)+'…' : n.label }}</text>
          <text :x="n.x + 10" :y="n.y + 40" font-size="9" fill="rgba(255,255,255,0.6)">{{ n.domain }}</text>
        </g>
      </svg>
    </div>

    <!-- Backlinks -->
    <div v-if="viewMode === 'backlinks'" class="space-y-2">
      <div v-if="!backlinks.length" class="text-center py-12 text-gray-500">暂无反向链接</div>
      <div v-for="bl in backlinks" :key="bl.target_key" class="bg-gray-900/50 rounded-xl p-4 border border-gray-800/50">
        <div class="flex items-center gap-2 mb-2">
          <span class="text-sm font-mono font-bold text-green-400">{{ bl.target_key }}</span>
          <span class="text-xs px-1.5 py-0.5 rounded-full bg-green-500/15 text-green-400">{{ bl.source_count }} 引用</span>
        </div>
        <div class="flex flex-wrap gap-1">
          <span v-for="s in bl.sources" :key="s" class="text-xs px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 font-mono">[[{{ s }}]]</span>
        </div>
      </div>
    </div>

    <!-- Parse -->
    <div v-if="viewMode === 'parse'" class="space-y-4">
      <div class="flex gap-2">
        <input v-model="parseKey" @keyup.enter="doParse" class="flex-1 bg-gray-900/50 border border-gray-800/50 rounded-xl px-4 py-3 text-sm text-gray-200 outline-none" placeholder="输入 memory key..." />
        <button @click="doParse" class="px-4 py-3 rounded-xl bg-brand-500 hover:bg-brand-600 text-white font-medium text-sm">解析</button>
      </div>
      <div v-if="parseResult" class="bg-gray-900/50 rounded-xl p-5 border border-gray-800/50 space-y-3">
        <div v-if="parseResult.frontmatter?.title" class="text-sm text-gray-200">📄 {{ parseResult.frontmatter.title }}</div>
        <div v-if="parseResult.wikilinks?.length" class="flex flex-wrap gap-1">
          <span v-for="wl in parseResult.wikilinks" :key="wl.target" class="text-xs px-2 py-1 rounded bg-blue-500/10 text-blue-400 font-mono">[[{{ wl.target }}]]</span>
        </div>
        <div v-if="parseResult.tags?.length" class="flex gap-1">
          <span v-for="t in parseResult.tags" :key="t" class="text-xs px-2 py-0.5 rounded-full bg-gray-800 text-gray-300">#{{ t }}</span>
        </div>
        <pre v-if="parseResult.plain_text" class="text-xs text-gray-400 whitespace-pre-wrap max-h-64 overflow-auto bg-gray-800/50 rounded-lg p-3">{{ parseResult.plain_text }}</pre>
      </div>
    </div>

    <!-- Stats -->
    <div v-if="viewMode === 'stats'" class="space-y-4">
      <div v-if="stats?.most_linked?.length" class="bg-gray-900/50 rounded-xl p-5 border border-gray-800/50">
        <h3 class="text-sm font-semibold text-white mb-3">最常被链接</h3>
        <div v-for="ml in stats.most_linked" :key="ml.key" class="flex items-center gap-3 py-1">
          <span class="text-sm font-mono text-green-400 w-40 truncate">{{ ml.key }}</span>
          <div class="flex-1 h-4 bg-gray-800 rounded-full overflow-hidden"><div class="h-full rounded-full bg-green-500/30" :style="{ width: (ml.count / (stats.most_linked[0]?.count || 1) * 100) + '%' }" /></div>
          <span class="text-xs text-gray-400 w-8 text-right">{{ ml.count }}</span>
        </div>
      </div>
      <div v-if="stats?.domains" class="bg-gray-900/50 rounded-xl p-5 border border-gray-800/50">
        <h3 class="text-sm font-semibold text-white mb-3">按领域</h3>
        <div class="flex flex-wrap gap-2">
          <span v-for="(count, domain) in stats.domains" :key="domain" class="px-3 py-1.5 rounded-lg bg-gray-800 text-sm"><span class="font-mono text-gray-200">{{ domain }}</span><span class="ml-2 text-xs text-gray-500">{{ count }}</span></span>
        </div>
      </div>
    </div>
  </div>
</template>
