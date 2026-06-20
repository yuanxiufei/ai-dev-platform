<template>
  <div class="knowledge-graph-page">
    <div class="page-header">
      <div>
        <h1>知识图谱</h1>
        <p>Obsidian 风格 Wikilinks + JSON Canvas 知识图谱</p>
      </div>
      <div class="header-actions">
        <select v-model="viewMode" class="mode-select">
          <option value="graph">图谱视图</option>
          <option value="backlinks">反向链接</option>
          <option value="parse">解析器</option>
          <option value="stats">统计</option>
        </select>
        <button class="btn-primary" @click="refreshAll">刷新</button>
        <button class="btn-secondary" @click="downloadCanvas">下载 .canvas</button>
      </div>
    </div>

    <!-- Stats cards -->
    <div class="stats-row" v-if="stats">
      <div class="stat-card">
        <span class="stat-num">{{ stats.total_memories }}</span>
        <span class="stat-label">记忆总数</span>
      </div>
      <div class="stat-card">
        <span class="stat-num">{{ stats.total_links }}</span>
        <span class="stat-label">链接总数</span>
      </div>
      <div class="stat-card">
        <span class="stat-num">{{ stats.total_backlinks }}</span>
        <span class="stat-label">反向链接</span>
      </div>
      <div class="stat-card">
        <span class="stat-num">{{ stats.orphans }}</span>
        <span class="stat-label">孤立节点</span>
      </div>
      <div class="stat-card">
        <span class="stat-num">{{ stats.graph_density }}</span>
        <span class="stat-label">图密度</span>
      </div>
    </div>

    <!-- Graph View -->
    <div v-if="viewMode === 'graph'" class="canvas-view">
      <div class="canvas-toolbar">
        <span class="text-sm text-gray-400">节点 {{ graphData.node_count }} · 边 {{ graphData.edge_count }}</span>
      </div>
      <div class="graph-container" ref="graphContainer">
        <div v-if="!graphData.nodes?.length" class="empty-state">
          <Globe class="empty-icon" />
          <p>还没有知识图谱数据</p>
          <p class="text-sm text-gray-500">在记忆中使用 [[key]] 创建链接关系</p>
        </div>
        <!-- Simple SVG based graph visualization -->
        <svg v-else :viewBox="svgViewBox" class="graph-svg">
          <defs>
            <marker id="arrowhead" markerWidth="10" markerHeight="7" refX="10" refY="3.5" orient="auto">
              <polygon points="0 0, 10 3.5, 0 7" fill="#9B59B6" />
            </marker>
          </defs>
          <g v-for="edge in graphLayout.edges" :key="edge.id">
            <line
              :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2"
              stroke="#9B59B6" stroke-width="1.5" opacity="0.6"
              marker-end="url(#arrowhead)"
            />
          </g>
          <g v-for="node in graphLayout.nodes" :key="node.id" class="graph-node">
            <rect
              :x="node.x" :y="node.y"
              :width="node.width" :height="node.height"
              :rx="8" :ry="8"
              :fill="nodeColor(node.importance)"
              :opacity="0.85"
              stroke="#fff" stroke-width="2"
              class="node-rect"
            />
            <text
              :x="node.x + 10" :y="node.y + 22"
              font-size="13" font-weight="600" fill="#fff"
            >{{ truncate(node.label, 18) }}</text>
            <text
              :x="node.x + 10" :y="node.y + 40"
              font-size="10" fill="rgba(255,255,255,0.7)"
            >{{ node.domain }}</text>
          </g>
        </svg>
      </div>
    </div>

    <!-- Backlinks View -->
    <div v-if="viewMode === 'backlinks'" class="backlinks-view">
      <div class="backlink-list" v-if="backlinks.length">
        <div v-for="(bl, i) in backlinks" :key="bl.target_key" class="backlink-item" :class="{ 'border-l-2 border-green-500 pl-3': bl.source_count >= 3 }">
          <div class="flex items-center gap-2">
            <span class="text-sm font-mono font-bold text-green-400">{{ bl.target_key }}</span>
            <span class="text-xs px-1.5 py-0.5 rounded-full bg-green-500/15 text-green-400">{{ bl.source_count }} refs</span>
          </div>
          <div class="flex flex-wrap gap-1 mt-1">
            <span v-for="s in bl.sources" :key="s" class="text-xs px-1.5 py-0.5 rounded bg-zinc-700/50 text-zinc-400 font-mono">
              [[{{ s }}]]
            </span>
          </div>
        </div>
      </div>
      <div v-else class="empty-state">
        <p>暂无反向链接</p>
      </div>
    </div>

    <!-- Parse View -->
    <div v-if="viewMode === 'parse'" class="parse-view">
      <div class="parse-input-row">
        <input v-model="parseKey" placeholder="输入 memory key..." class="search-input" @keyup.enter="doParse" />
        <button class="btn-primary" @click="doParse">解析</button>
      </div>
      <div v-if="parseResult" class="parse-result">
        <!-- Frontmatter -->
        <div class="parse-section" v-if="parseResult.frontmatter.title || parseResult.frontmatter.tags?.length">
          <h3>🧩 Frontmatter</h3>
          <div class="fm-grid">
            <div v-if="parseResult.frontmatter.title" class="fm-item"><span class="fm-key">title</span><span class="fm-val">{{ parseResult.frontmatter.title }}</span></div>
            <div v-if="parseResult.frontmatter.tags?.length" class="fm-item"><span class="fm-key">tags</span><span class="fm-val">{{ parseResult.frontmatter.tags.join(', ') }}</span></div>
            <div v-if="parseResult.frontmatter.aliases?.length" class="fm-item"><span class="fm-key">aliases</span><span class="fm-val">{{ parseResult.frontmatter.aliases.join(', ') }}</span></div>
            <div v-if="parseResult.frontmatter.status" class="fm-item"><span class="fm-key">status</span><span class="fm-val fm-status" :class="'status-'+parseResult.frontmatter.status">{{ parseResult.frontmatter.status }}</span></div>
            <div v-if="parseResult.frontmatter.priority" class="fm-item"><span class="fm-key">priority</span><span class="fm-val fm-priority" :class="'priority-'+parseResult.frontmatter.priority">{{ parseResult.frontmatter.priority }}</span></div>
            <div v-if="parseResult.frontmatter.due_date" class="fm-item"><span class="fm-key">due_date</span><span class="fm-val">{{ parseResult.frontmatter.due_date }}</span></div>
          </div>
        </div>

        <!-- Wikilinks -->
        <div class="parse-section" v-if="parseResult.wikilinks?.length">
          <h3>🔗 Wikilinks ({{ parseResult.wikilink_count }})</h3>
          <div class="flex flex-wrap gap-1">
            <span v-for="wl in parseResult.wikilinks" :key="wl.target" class="text-xs px-2 py-1 rounded bg-blue-500/10 text-blue-400 font-mono">
              [[{{ wl.target }}{{ wl.heading ? '#'+wl.heading : '' }}{{ wl.display ? '|'+wl.display : '' }}]]
            </span>
          </div>
        </div>

        <!-- Callouts -->
        <div class="parse-section" v-if="parseResult.callouts?.length">
          <h3>📢 Callouts ({{ parseResult.callout_count }})</h3>
          <div v-for="(co, i) in parseResult.callouts" :key="i" class="callout-block" :class="'callout-'+co.type">
            <span class="callout-header">[!{{ co.type }}] {{ co.title }}</span>
            <p class="callout-body">{{ co.content }}</p>
          </div>
        </div>

        <!-- Tags -->
        <div class="parse-section" v-if="parseResult.tags?.length">
          <h3>🏷️ Tags</h3>
          <div class="flex flex-wrap gap-1">
            <span v-for="t in parseResult.tags" :key="t" class="text-xs px-2 py-0.5 rounded-full bg-zinc-600/30 text-zinc-300">
              #{{ t }}
            </span>
          </div>
        </div>

        <!-- Plain text -->
        <div class="parse-section" v-if="parseResult.plain_text">
          <h3>📝 纯文本</h3>
          <pre class="plain-text">{{ parseResult.plain_text }}</pre>
        </div>

        <div class="parse-section" v-if="!parseResult.wikilinks?.length && !parseResult.callouts?.length && !parseResult.frontmatter.title">
          <p class="text-gray-500">此记忆没有 Obsidian 风格的富文本内容</p>
        </div>
      </div>
    </div>

    <!-- Stats View -->
    <div v-if="viewMode === 'stats'" class="stats-view">
      <div class="section-title">🔝 最常被链接</div>
      <div class="most-linked" v-if="stats?.most_linked?.length">
        <div v-for="ml in stats.most_linked" :key="ml.key" class="linked-row">
          <span class="text-sm font-mono text-green-400">{{ ml.key }}</span>
          <div class="linked-bar">
            <div class="linked-bar-fill" :style="{ width: (ml.count / (stats.most_linked[0]?.count || 1) * 100) + '%' }" />
            <span class="linked-count">{{ ml.count }}</span>
          </div>
        </div>
      </div>

      <div class="section-title mt-6">📁 按 Domain</div>
      <div class="domains" v-if="stats?.domains">
        <div v-for="(count, domain) in stats.domains" :key="domain" class="domain-badge">
          <span class="font-mono">{{ domain }}</span>
          <span class="text-xs text-zinc-400">{{ count }}</span>
        </div>
      </div>

      <div class="section-title mt-6" v-if="stats?.orphan_keys?.length">🫙 孤立节点</div>
      <div class="flex flex-wrap gap-1" v-if="stats?.orphan_keys?.length">
        <span v-for="k in stats.orphan_keys" :key="k" class="text-xs px-2 py-1 rounded bg-zinc-700/50 text-zinc-400 font-mono">{{ k }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { Globe } from 'lucide-vue-next'
import { kgApi } from '@/api/model-features'

const viewMode = ref<'graph' | 'backlinks' | 'parse' | 'stats'>('graph')
const parseKey = ref('')
const parseResult = ref<any>(null)
const backlinks = ref<any[]>([])
const canvas = ref<any>({ nodes: [], edges: [] })
const graphData = ref<any>({ nodes: [], edges: [], node_count: 0, edge_count: 0 })
const stats = ref<any>(null)

const graphContainer = ref<HTMLElement>()

const COLORS = ['#2ECC71','#3498DB','#9B59B6','#E67E22','#E74C3C']

function nodeColor(importance: number) {
  if (importance >= 0.8) return '#E74C3C'
  if (importance >= 0.5) return '#E67E22'
  if (importance >= 0.3) return '#3498DB'
  return '#2ECC71'
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n) + '…' : s
}

// Simple grid layout
const graphLayout = computed(() => {
  const nodes = graphData.value.nodes || []
  const edges = graphData.value.edges || []
  const cols = Math.ceil(Math.sqrt(nodes.length)) || 3
  const cellW = 200
  const cellH = 90
  const gap = 40

  const nodeMap: Record<string, number> = {}
  const layoutNodes = nodes.map((n: any, i: number) => {
    const col = i % cols
    const row = Math.floor(i / cols)
    nodeMap[n.id] = i
    return {
      ...n,
      x: col * (cellW + gap) + gap,
      y: row * (cellH + gap) + gap,
      width: cellW,
      height: cellH,
    }
  })

  const layoutEdges = edges.map((e: any) => ({
    id: e.from + '_' + e.to,
    x1: (nodeMap[e.from] !== undefined ? (nodeMap[e.from] % cols) * (cellW + gap) + gap + cellW : 0),
    y1: (nodeMap[e.from] !== undefined ? Math.floor(nodeMap[e.from] / cols) * (cellH + gap) + gap + cellH / 2 : 0),
    x2: (nodeMap[e.to] !== undefined ? (nodeMap[e.to] % cols) * (cellW + gap) + gap : 0),
    y2: (nodeMap[e.to] !== undefined ? Math.floor(nodeMap[e.to] / cols) * (cellH + gap) + gap + cellH / 2 : 0),
  }))

  return { nodes: layoutNodes, edges: layoutEdges }
})

const svgViewBox = computed(() => {
  const n = graphData.value.nodes?.length || 1
  const cols = Math.ceil(Math.sqrt(n)) || 1
  const rows = Math.ceil(n / cols) || 1
  const cellW = 240
  const cellH = 130
  return `0 0 ${cols * cellW + 40} ${rows * cellH + 40}`
})

async function refreshAll() {
  try {
    const [statsRes, graphDataRes, backlinksRes] = await Promise.all([
      kgApi.stats().catch(() => null),
      kgApi.graphData().catch(() => null),
      kgApi.backlinks().catch(() => null),
    ])
    stats.value = statsRes
    graphData.value = graphDataRes || { nodes: [], edges: [], node_count: 0, edge_count: 0 }
    backlinks.value = backlinksRes?.backlinks || []
  } catch (e) {
    console.error('Failed to refresh', e)
  }
}

async function doParse() {
  if (!parseKey.value) return
  try {
    parseResult.value = await kgApi.parse(parseKey.value)
  } catch {
    parseResult.value = null
  }
}

async function downloadCanvas() {
  try {
    const res = await kgApi.downloadCanvas()
    const blob = new Blob([res.content], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = res.filename || 'knowledge-graph.canvas'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error('Download failed', e)
  }
}

onMounted(refreshAll)
</script>

<style scoped>
.knowledge-graph-page { padding: 1.5rem; display: flex; flex-direction: column; gap: 1rem; }
.page-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 0.75rem; }
.page-header h1 { font-size: 1.25rem; font-weight: 700; color: #fff; }
.page-header p { font-size: 0.875rem; color: #9ca3af; }
.header-actions { display: flex; align-items: center; gap: 0.5rem; }
.mode-select { background: #27272a; border: 1px solid #3f3f46; border-radius: 0.5rem; padding: 0.375rem 0.75rem; font-size: 0.875rem; color: #fff; }
.btn-primary { padding: 0.375rem 1rem; background: #16a34a; color: #fff; font-size: 0.875rem; border-radius: 0.5rem; font-weight: 500; border: none; cursor: pointer; transition: background 0.2s; }
.btn-primary:hover { background: #22c55e; }
.btn-secondary { padding: 0.375rem 1rem; background: #3f3f46; color: #fff; font-size: 0.875rem; border-radius: 0.5rem; font-weight: 500; border: none; cursor: pointer; transition: background 0.2s; }
.btn-secondary:hover { background: #52525b; }
.stats-row { display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.75rem; }
.stat-card { background: rgba(39, 39, 42, 0.8); border-radius: 0.75rem; padding: 1rem; text-align: center; border: 1px solid rgba(63, 63, 70, 0.5); }
.stat-num { display: block; font-size: 1.5rem; font-weight: 700; color: #4ade80; }
.stat-label { font-size: 0.75rem; color: #6b7280; margin-top: 0.25rem; }
.canvas-view { background: rgba(39, 39, 42, 0.8); border-radius: 0.75rem; border: 1px solid rgba(63, 63, 70, 0.5); }
.canvas-toolbar { padding: 0.75rem; border-bottom: 1px solid rgba(63, 63, 70, 0.5); }
.graph-container { padding: 1rem; min-height: 400px; }
.graph-svg { width: 100%; }
.node-rect { cursor: pointer; transition: opacity 0.2s; }
.node-rect:hover { opacity: 1 !important; }
.empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 4rem 0; color: #9ca3af; gap: 0.5rem; }
.empty-icon { width: 3rem; height: 3rem; opacity: 0.3; }

.backlink-item { background: rgba(39, 39, 42, 0.6); border-radius: 0.5rem; padding: 0.75rem; border: 1px solid rgba(63, 63, 70, 0.5); }

.parse-input-row { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
.search-input { flex: 1; background: #27272a; border: 1px solid #3f3f46; border-radius: 0.5rem; padding: 0.5rem 0.75rem; font-size: 0.875rem; color: #fff; }
.search-input::placeholder { color: #71717a; }
.parse-section { margin-bottom: 1rem; }
.parse-section h3 { font-size: 0.875rem; font-weight: 600; color: #d1d5db; margin-bottom: 0.5rem; }
.fm-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 0.5rem; }
.fm-item { display: flex; align-items: center; gap: 0.5rem; font-size: 0.875rem; }
.fm-key { color: #71717a; font-family: monospace; font-size: 0.75rem; min-width: 60px; }
.fm-val { color: #d1d5db; }
.fm-status { padding: 0.125rem 0.375rem; border-radius: 0.25rem; font-size: 0.75rem; font-weight: 500; }
.status-draft { background: rgba(234, 179, 8, 0.15); color: #facc15; }
.status-in-progress { background: rgba(59, 130, 246, 0.15); color: #60a5fa; }
.status-completed { background: rgba(34, 197, 94, 0.15); color: #4ade80; }
.status-archived { background: rgba(113, 113, 122, 0.15); color: #a1a1aa; }
.priority-low { color: #a1a1aa; }
.priority-medium { color: #facc15; }
.priority-high { color: #fb923c; }
.priority-critical { color: #f87171; }

.callout-block { border-radius: 0.5rem; padding: 0.75rem; border: 1px solid; margin-bottom: 0.5rem; }
.callout-header { font-size: 0.875rem; font-weight: 600; display: block; margin-bottom: 0.25rem; }
.callout-body { font-size: 0.75rem; color: #a1a1aa; }
.callout-note { background: rgba(59, 130, 246, 0.1); border-color: rgba(59, 130, 246, 0.3); }
.callout-note .callout-header { color: #60a5fa; }
.callout-warning { background: rgba(234, 179, 8, 0.1); border-color: rgba(234, 179, 8, 0.3); }
.callout-warning .callout-header { color: #facc15; }
.callout-tip { background: rgba(34, 197, 94, 0.1); border-color: rgba(34, 197, 94, 0.3); }
.callout-tip .callout-header { color: #4ade80; }
.callout-info { background: rgba(6, 182, 212, 0.1); border-color: rgba(6, 182, 212, 0.3); }
.callout-info .callout-header { color: #22d3ee; }
.callout-danger { background: rgba(239, 68, 68, 0.1); border-color: rgba(239, 68, 68, 0.3); }
.callout-danger .callout-header { color: #f87171; }
.callout-important { background: rgba(239, 68, 68, 0.1); border-color: rgba(239, 68, 68, 0.3); }
.callout-important .callout-header { color: #f87171; }
.callout-quote { background: rgba(113, 113, 122, 0.1); border-color: rgba(113, 113, 122, 0.3); }
.callout-quote .callout-header { color: #a1a1aa; }
.callout-example { background: rgba(147, 51, 234, 0.1); border-color: rgba(147, 51, 234, 0.3); }
.callout-example .callout-header { color: #c084fc; }
.callout-question { background: rgba(147, 51, 234, 0.1); border-color: rgba(147, 51, 234, 0.3); }
.callout-question .callout-header { color: #c084fc; }
.callout-success { background: rgba(34, 197, 94, 0.1); border-color: rgba(34, 197, 94, 0.3); }
.callout-success .callout-header { color: #4ade80; }
.callout-failure { background: rgba(239, 68, 68, 0.1); border-color: rgba(239, 68, 68, 0.3); }
.callout-failure .callout-header { color: #f87171; }
.callout-bug { background: rgba(239, 68, 68, 0.1); border-color: rgba(239, 68, 68, 0.3); }
.callout-bug .callout-header { color: #f87171; }
.callout-todo { background: rgba(147, 51, 234, 0.1); border-color: rgba(147, 51, 234, 0.3); }
.callout-todo .callout-header { color: #c084fc; }
.callout-abstract { background: rgba(147, 51, 234, 0.1); border-color: rgba(147, 51, 234, 0.3); }
.callout-abstract .callout-header { color: #c084fc; }
.plain-text { background: rgba(24, 24, 27, 0.5); border-radius: 0.5rem; padding: 0.75rem; font-size: 0.75rem; color: #a1a1aa; font-family: monospace; white-space: pre-wrap; max-height: 200px; overflow: auto; }

.linked-row { display: flex; align-items: center; gap: 0.75rem; padding: 0.375rem 0; }
.linked-bar { flex: 1; height: 1.25rem; background: rgba(24, 24, 27, 0.5); border-radius: 0.25rem; position: relative; overflow: hidden; }
.linked-bar-fill { height: 100%; background: rgba(34, 197, 94, 0.3); border-radius: 0.25rem; }
.linked-count { position: absolute; right: 0.5rem; top: 0; font-size: 0.75rem; color: #a1a1aa; line-height: 1.25rem; }
.domain-badge { display: inline-flex; gap: 0.5rem; padding: 0.375rem 0.75rem; border-radius: 0.5rem; background: rgba(63, 63, 70, 0.4); border: 1px solid rgba(82, 82, 91, 0.3); font-size: 0.875rem; }
.section-title { font-size: 0.875rem; font-weight: 600; color: #9ca3af; margin-bottom: 0.5rem; }
</style>
