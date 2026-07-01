<template>
  <!-- HermesStudio 风格 Memory 图可视化面板 -->
  <div class="memory-graph-panel">
    <!-- Header -->
    <div class="panel-header">
      <h3 class="panel-title">
        <BrainCircuit class="title-icon" :size="20" />
        Memory 关系图
      </h3>
      <div class="header-actions">
        <button
          v-for="typ in activeTypes"
          :key="typ"
          :class="['type-chip', { active: selectedTypes.includes(typ) }]"
          @click="toggleType(typ)"
        >
          {{ typeLabels[typ] || typ }}
        </button>
        <span class="separator">|</span>
        <label class="filter-label">
          <Filter :size="14" />
          Importance &ge;
          <input
            v-model.number="minImportance"
            type="range"
            min="0"
            max="100"
            class="importance-slider"
          />
          <span class="filter-value">{{ minImportance }}%</span>
        </label>
        <button class="refresh-btn" @click="fetchGraphData" :disabled="loading">
          <RefreshCw :size="14" :class="{ spinning: loading }" />
        </button>
      </div>
    </div>

    <!-- Stats Bar -->
    <div v-if="stats" class="stats-bar">
      <div class="stat-item">
        <span class="stat-value">{{ stats.total_nodes }}</span>
        <span class="stat-label">记忆节点</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ stats.total_edges }}</span>
        <span class="stat-label">关系边</span>
      </div>
      <div class="stat-item" v-for="(count, typ) in stats.by_type" :key="typ">
        <span class="stat-value">{{ count }}</span>
        <span class="stat-label">{{ typeLabels[typ] || typ }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-value">{{ stats.avg_importance?.toFixed(1) }}</span>
        <span class="stat-label">平均重要性</span>
      </div>
    </div>

    <!-- Graph Canvas -->
    <div ref="canvasRef" class="graph-canvas" :class="{ loading: loading }">
      <!-- Loading -->
      <div v-if="loading" class="loading-state">
        <Loader2 :size="24" class="spinning" />
        <span>加载图数据...</span>
      </div>

      <!-- Empty -->
      <div v-else-if="!nodes.length" class="empty-state">
        <GitGraph :size="48" class="empty-icon" />
        <span>暂无关系图数据</span>
        <span class="empty-hint">使用 Agent 生成代码后自动构建记忆关系</span>
      </div>

      <!-- Graph (纯 CSS + SVG 实现) -->
      <svg
        v-else
        class="graph-svg"
        :viewBox="viewBox"
        @mousedown="startDrag"
        @mousemove="onDrag"
        @mouseup="endDrag"
        @wheel.prevent="onZoom"
      >
        <!-- Edges -->
        <line
          v-for="edge in layoutEdges"
          :key="edge.id"
          :x1="edge.x1"
          :y1="edge.y1"
          :x2="edge.x2"
          :y2="edge.y2"
          :class="['graph-edge', edge.relation_type]"
          :stroke-width="Math.max(1, edge.weight * 2)"
        >
          <title>{{ edge.label }}</title>
        </line>

        <!-- Nodes -->
        <g
          v-for="node in layoutNodes"
          :key="node.id"
          :transform="`translate(${node.x}, ${node.y})`"
          :class="['graph-node', { selected: selectedNode === node.id }]"
          @click="selectNode(node.id)"
        >
          <!-- Node circle -->
          <circle
            :r="nodeRadius(node)"
            :class="['node-circle', node.memory_type]"
          />
          <!-- Node label -->
          <text
            :y="nodeRadius(node) + 16"
            text-anchor="middle"
            class="node-label"
          >
            {{ truncate(node.content, 12) }}
          </text>
        </g>
      </svg>
    </div>

    <!-- Node Detail Panel (slide-in) -->
    <div v-if="selectedNode && nodeDetail" class="detail-panel">
      <div class="detail-header">
        <span class="detail-type" :class="nodeDetail.memory_type">
          {{ typeLabels[nodeDetail.memory_type] || nodeDetail.memory_type }}
        </span>
        <button class="close-btn" @click="selectedNode = null">&times;</button>
      </div>
      <div class="detail-body">
        <p class="detail-content">{{ nodeDetail.content }}</p>
        <div class="detail-meta">
          <div class="meta-row">
            <span class="meta-label">Importance</span>
            <span class="meta-value">{{ (nodeDetail.importance * 100).toFixed(0) }}%</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">Access Count</span>
            <span class="meta-value">{{ nodeDetail.access_count }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-label">Created</span>
            <span class="meta-value">{{ formatDate(nodeDetail.created_at) }}</span>
          </div>
          <div class="meta-row" v-if="nodeDetail.tags">
            <span class="meta-label">Tags</span>
            <span class="meta-value">
              <span v-for="tag in nodeDetail.tags" :key="tag" class="tag-badge">{{ tag }}</span>
            </span>
          </div>
        </div>
        <!-- Connected nodes -->
        <div v-if="nodeConnections.length" class="connections">
          <h4 class="connections-title">关联记忆 ({{ nodeConnections.length }})</h4>
          <div
            v-for="conn in nodeConnections"
            :key="conn.id"
            class="connection-item"
          >
            <span :class="['conn-arrow', conn.relation_type]">{{ conn.is_source ? '→' : '←' }}</span>
            <span class="conn-type">{{ relationLabels[conn.relation_type] || conn.relation_type }}</span>
            <span class="conn-content">{{ truncate(conn.content, 40) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import {
  BrainCircuit, RefreshCw, Filter, Loader2, GitGraph,
} from 'lucide-vue-next'

// ── Types ─────────────────────────────────────────────
interface NodeLayout {
  id: string
  x: number
  y: number
  content: string
  memory_type: string
  importance: number
  access_count: number
  created_at: string
  tags?: string[]
}

interface EdgeLayout {
  id: string
  x1: number
  y1: number
  x2: number
  y2: number
  relation_type: string
  weight: number
  label: string
}

interface GraphData {
  nodes: NodeLayout[]
  edges: EdgeLayout[]
}

interface GraphStats {
  total_nodes: number
  total_edges: number
  by_type: Record<string, number>
  avg_importance: number
}

// ── Props ──────────────────────────────────────────────
const props = defineProps<{
  apiBase?: string
}>()

// ── State ──────────────────────────────────────────────
const canvasRef = ref<HTMLElement | null>(null)
const loading = ref(false)
const rawData = ref<GraphData>({ nodes: [], edges: [] })
const stats = ref<GraphStats | null>(null)
const selectedNode = ref<string | null>(null)
const selectedTypes = ref<string[]>([
  'code', 'conversation', 'decision', 'lesson', 'fact', 'pattern',
])
const minImportance = ref(20)

// 拖拽/缩放
const dragState = ref({ dragging: false, startX: 0, startY: 0 })
const panOffset = ref({ x: 0, y: 0 })
const zoom = ref(1)

// ── Labels ─────────────────────────────────────────────
const typeLabels: Record<string, string> = {
  code: '代码',
  conversation: '对话',
  decision: '决策',
  lesson: '教训',
  fact: '事实',
  pattern: '模式',
  preference: '偏好',
}

const relationLabels: Record<string, string> = {
  relates_to: '关联',
  depends_on: '依赖',
  before: '时序前',
  after: '时序后',
  enhances: '增强',
  contradicts: '矛盾',
  derived_from: '派生',
}

const activeTypes = [
  'code', 'conversation', 'decision', 'lesson', 'fact', 'pattern', 'preference',
]

// ── Layout computation ─────────────────────────────────
const filteredNodes = computed(() => {
  return rawData.value.nodes.filter(n =>
    selectedTypes.value.includes(n.memory_type) &&
    n.importance >= minImportance.value / 100
  )
})

const filteredEdges = computed(() => {
  const nodeIds = new Set(filteredNodes.value.map(n => n.id))
  return rawData.value.edges.filter(
    e => nodeIds.has(e.id.split('->')[0]) && nodeIds.has(e.id.split('->')[1] || '')
  )
})

const layoutNodes = computed(() => {
  const nodes = [...filteredNodes.value]
  const count = nodes.length
  const cols = Math.ceil(Math.sqrt(count * 1.6))
  const rows = Math.ceil(count / cols)
  const spacingX = 600 / cols
  const spacingY = 500 / rows

  return nodes.map((node, i) => {
    const col = i % cols
    const row = Math.floor(i / cols)
    // 也支持圆形布局（少量节点时更好看）
    if (count <= 12) {
      const angle = (i / count) * Math.PI * 2
      const radius = 180
      return {
        ...node,
        x: 300 + Math.cos(angle) * radius + panOffset.value.x,
        y: 250 + Math.sin(angle) * radius + panOffset.value.y,
      }
    }
    return {
      ...node,
      x: spacingX * (col + 0.5) + panOffset.value.x,
      y: spacingY * (row + 0.5) + panOffset.value.y,
    }
  })
})

const layoutEdges = computed(() => {
  const nodeMap = new Map(layoutNodes.value.map(n => [n.id, n]))
  return filteredEdges.value.map(edge => {
    const parts = edge.id.split('->')
    const source = nodeMap.get(parts[0])
    const target = nodeMap.get(parts[1])
    if (!source || !target) return null
    return { ...edge, x1: source.x, y1: source.y, x2: target.x, y2: target.y }
  }).filter(Boolean) as EdgeLayout[]
})

const viewBox = computed(() => {
  const scale = 1 / zoom.value
  return `${-50 * scale} ${-50 * scale} ${700 * scale} ${600 * scale}`
})

const nodeDetail = computed(() => {
  if (!selectedNode.value) return null
  return rawData.value.nodes.find(n => n.id === selectedNode.value) || null
})

const nodeConnections = computed(() => {
  if (!selectedNode.value) return []
  return filteredEdges.value
    .filter(e => e.id.includes(selectedNode.value!))
    .map(e => {
      const parts = e.id.split('->')
      const isSource = parts[0] === selectedNode.value
      const otherId = isSource ? parts[1] : parts[0]
      const otherNode = rawData.value.nodes.find(n => n.id === otherId)
      return {
        ...e,
        is_source: isSource,
        content: otherNode?.content || otherId,
      }
    })
})

// ── Methods ────────────────────────────────────────────
function nodeRadius(node: NodeLayout): number {
  return 12 + Math.min(node.importance * 20, 18)
}

function truncate(text: string, maxLen: number): string {
  if (!text) return ''
  return text.length > maxLen ? text.slice(0, maxLen) + '...' : text
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('zh-CN')
  } catch {
    return iso
  }
}

function toggleType(type: string) {
  const idx = selectedTypes.value.indexOf(type)
  if (idx >= 0) {
    selectedTypes.value = selectedTypes.value.filter(t => t !== type)
  } else {
    selectedTypes.value = [...selectedTypes.value, type]
  }
}

function selectNode(id: string) {
  selectedNode.value = selectedNode.value === id ? null : id
}

// 拖拽平移
function startDrag(e: MouseEvent) {
  dragState.value = { dragging: true, startX: e.clientX, startY: e.clientY }
}

function onDrag(e: MouseEvent) {
  if (!dragState.value.dragging) return
  panOffset.value = {
    x: panOffset.value.x + (e.clientX - dragState.value.startX),
    y: panOffset.value.y + (e.clientY - dragState.value.startY),
  }
  dragState.value.startX = e.clientX
  dragState.value.startY = e.clientY
}

function endDrag() {
  dragState.value.dragging = false
}

function onZoom(e: WheelEvent) {
  const delta = e.deltaY > 0 ? -0.1 : 0.1
  zoom.value = Math.max(0.3, Math.min(3, zoom.value + delta))
}

async function fetchGraphData() {
  loading.value = true
  try {
    const base = props.apiBase || '/api/v1'
    const [graphRes, statsRes] = await Promise.all([
      fetch(`${base}/memory/graph-data?min_importance=${minImportance.value / 100}`),
      fetch(`${base}/memory/graph-stats`),
    ])
    const graphJson = await graphRes.json()
    const statsJson = await statsRes.json()

    rawData.value = {
      nodes: graphJson.nodes || [],
      edges: graphJson.edges || [],
    }
    stats.value = statsJson.stats || statsJson
  } catch (e) {
    console.error('Failed to load memory graph:', e)
  } finally {
    loading.value = false
  }
}

onMounted(fetchGraphData)
watch([minImportance, selectedTypes], () => {
  fetchGraphData()
}, { deep: true })
</script>

<style scoped>
.memory-graph-panel {
  @apply bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-700 overflow-hidden;
}

/* Header */
.panel-header {
  @apply flex items-center justify-between px-4 py-3 border-b border-gray-200 dark:border-gray-700;
}

.panel-title {
  @apply flex items-center gap-2 text-sm font-semibold text-gray-900 dark:text-gray-100;
}

.title-icon {
  @apply text-indigo-500;
}

.header-actions {
  @apply flex items-center gap-2 text-xs;
}

.type-chip {
  @apply px-2 py-0.5 rounded-full border transition-colors cursor-pointer;
  @apply border-gray-300 dark:border-gray-600 text-[var(--color-ide-text-dim)] dark:text-[var(--color-ide-text-dim)];
}
.type-chip:hover {
  @apply bg-gray-100 dark:bg-gray-700;
}
.type-chip.active {
  @apply bg-indigo-50 dark:bg-indigo-900/30 border-indigo-300 dark:border-indigo-600 text-indigo-700 dark:text-indigo-300;
}

.separator {
  @apply text-[var(--color-ide-text)] dark:text-[var(--color-ide-text-dim)] mx-1;
}

.filter-label {
  @apply flex items-center gap-1 text-[var(--color-ide-text-dim)] dark:text-[var(--color-ide-text-dim)];
}

.importance-slider {
  @apply w-16 h-1 accent-indigo-500;
}

.filter-value {
  @apply text-gray-700 dark:text-[var(--color-ide-text)] font-mono w-8;
}

.refresh-btn {
  @apply p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-[var(--color-ide-text-dim)] dark:text-[var(--color-ide-text-dim)];
}

.refresh-btn:disabled {
  @apply opacity-50 cursor-not-allowed;
}

/* Stats Bar */
.stats-bar {
  @apply flex gap-4 px-4 py-2 border-b border-gray-100 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50;
}

.stat-item {
  @apply flex flex-col items-center;
}

.stat-value {
  @apply text-sm font-bold text-gray-900 dark:text-gray-100;
}

.stat-label {
  @apply text-[10px] text-[var(--color-ide-text-dim)] dark:text-[var(--color-ide-text-dim)] uppercase tracking-wide;
}

/* Graph Canvas */
.graph-canvas {
  @apply relative h-[400px] overflow-hidden;
  @apply bg-gray-50 dark:bg-gray-950 bg-[radial-gradient(circle,#e5e7eb_1px,transparent_1px)] bg-[size:20px_20px];
}

.graph-canvas.loading,
.loading-state {
  @apply flex items-center justify-center;
}

.loading-state {
  @apply flex-col gap-2 text-[var(--color-ide-text-dim)] dark:text-[var(--color-ide-text-dim)];
}

.empty-state {
  @apply flex flex-col items-center justify-center h-full gap-2 text-[var(--color-ide-text-dim)] dark:text-[var(--color-ide-text-dim)];
}

.empty-icon {
  @apply opacity-50;
}

.empty-hint {
  @apply text-xs;
}

/* SVG */
.graph-svg {
  @apply w-full h-full cursor-grab;
}

.graph-svg:active {
  @apply cursor-grabbing;
}

/* Edges */
.graph-edge {
  @apply stroke-gray-300 dark:stroke-gray-600 opacity-60;
}
.graph-edge.depends_on {
  @apply stroke-amber-400 opacity-70;
}
.graph-edge.enhances {
  @apply stroke-green-400 opacity-70;
}
.graph-edge.contradicts {
  @apply stroke-red-400 opacity-70;
}
.graph-edge.derived_from {
  @apply stroke-indigo-400 opacity-70;
}

/* Nodes */
.graph-node {
  @apply cursor-pointer transition-transform;
}
.graph-node:hover {
  transform: scale(1.15);
}

.node-circle {
  @apply fill-gray-400 dark:fill-gray-500 stroke-white dark:stroke-gray-900 stroke-2;
}
.node-circle.code {
  @apply fill-blue-500;
}
.node-circle.conversation {
  @apply fill-emerald-500;
}
.node-circle.decision {
  @apply fill-amber-500;
}
.node-circle.lesson {
  @apply fill-red-500;
}
.node-circle.fact {
  @apply fill-indigo-500;
}
.node-circle.pattern {
  @apply fill-purple-500;
}
.node-circle.preference {
  @apply fill-pink-500;
}

.graph-node.selected .node-circle {
  @apply stroke-indigo-400 stroke-[3px] ring-4;
}

.node-label {
  @apply fill-gray-700 dark:fill-gray-300 text-[10px] pointer-events-none;
}

/* Detail Panel */
.detail-panel {
  @apply absolute top-0 right-0 w-72 h-full bg-white dark:bg-gray-900 border-l border-gray-200 dark:border-gray-700 overflow-y-auto shadow-lg z-10 transition-transform;
}

.detail-header {
  @apply flex items-center justify-between p-3 border-b border-gray-200 dark:border-gray-700;
}

.detail-type {
  @apply px-2 py-0.5 rounded-full text-xs font-medium text-white;
}
.detail-type.code { @apply bg-blue-500; }
.detail-type.conversation { @apply bg-emerald-500; }
.detail-type.decision { @apply bg-amber-500; }
.detail-type.lesson { @apply bg-red-500; }
.detail-type.fact { @apply bg-indigo-500; }
.detail-type.pattern { @apply bg-purple-500; }

.close-btn {
  @apply text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text-dim)] dark:hover:text-[var(--color-ide-text)] text-lg leading-none;
}

.detail-body {
  @apply p-3 space-y-3;
}

.detail-content {
  @apply text-sm text-gray-700 dark:text-[var(--color-ide-text)] leading-relaxed;
}

.detail-meta {
  @apply space-y-1.5;
}

.meta-row {
  @apply flex justify-between text-xs;
}

.meta-label {
  @apply text-[var(--color-ide-text-dim)] dark:text-[var(--color-ide-text-dim)];
}

.meta-value {
  @apply text-gray-700 dark:text-[var(--color-ide-text)] font-medium;
}

.tag-badge {
  @apply inline-block px-1.5 py-0.5 mr-1 rounded bg-gray-100 dark:bg-gray-700 text-[var(--color-ide-text-dim)] dark:text-[var(--color-ide-text-dim)] text-[10px];
}

.connections {
  @apply pt-2 border-t border-gray-100 dark:border-gray-800;
}

.connections-title {
  @apply text-xs font-medium text-[var(--color-ide-text-dim)] dark:text-[var(--color-ide-text-dim)] mb-2;
}

.connection-item {
  @apply flex items-center gap-1.5 text-xs py-1;
}

.conn-arrow {
  @apply text-[var(--color-ide-text-dim)] dark:text-[var(--color-ide-text-dim)];
}
.conn-arrow.depends_on { @apply text-amber-500; }
.conn-arrow.enhances { @apply text-green-500; }
.conn-arrow.contradicts { @apply text-red-500; }

.conn-type {
  @apply text-[10px] px-1 rounded bg-gray-100 dark:bg-gray-800 text-[var(--color-ide-text-dim)] dark:text-[var(--color-ide-text-dim)];
}

.conn-content {
  @apply text-[var(--color-ide-text-dim)] dark:text-[var(--color-ide-text)] truncate;
}

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
</style>
