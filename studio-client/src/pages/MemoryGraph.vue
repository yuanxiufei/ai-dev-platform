<script setup lang="ts">
/**
 * MemoryGraph — Agent 记忆关系图谱可视化
 * 纯 Canvas 力导向图，零外部依赖
 */
import { ref, onMounted, onUnmounted, watch, nextTick, computed } from "vue"
import { memoryGraphApi, type MemoryGraphNode, type MemoryGraphEdge, type MemoryGraphStats } from "@/api/model-features"
import { Search, RotateCcw, ZoomIn, ZoomOut, Maximize, Loader2, Info } from "lucide-vue-next"

// ── 状态 ──
const loading = ref(false)
const nodes = ref<MemoryGraphNode[]>([])
const edges = ref<MemoryGraphEdge[]>([])
const stats = ref<MemoryGraphStats | null>(null)
const filterType = ref("")
const filterImportance = ref(0)
const error = ref("")
const hoveredNode = ref<MemoryGraphNode | null>(null)
const hoverPos = ref({ x: 0, y: 0 })

// ── Canvas 力导向布局 ──
const canvasRef = ref<HTMLCanvasElement | null>(null)
const containerRef = ref<HTMLDivElement | null>(null)

interface LayoutNode {
  id: string
  x: number
  y: number
  vx: number
  vy: number
  data: MemoryGraphNode
}

interface LayoutEdge {
  source: LayoutNode
  target: LayoutNode
  data: MemoryGraphEdge
}

let layoutNodes: LayoutNode[] = []
let layoutEdges: LayoutEdge[] = []
let animFrameId = 0
let zoom = 1
let panX = 0
let panY = 0
let isDragging = false
let dragNode: LayoutNode | null = null
let lastMouseX = 0
let lastMouseY = 0
let simulationRunning = true

const NODE_RADIUS_BASE = 6
const NODE_RADIUS_MAX = 18
const REPULSION = 1200
const ATTRACTION = 0.005
const DAMPING = 0.85
const MAX_VELOCITY = 8
const CENTER_FORCE = 0.002

// ── 颜色映射 ──
const TYPE_COLORS: Record<string, string> = {
  fact: "#3b82f6",
  preference: "#a855f7",
  experience: "#22c55e",
  decision: "#f59e0b",
  code_pattern: "#06b6d4",
  project_context: "#ec4899",
  user_info: "#f97316",
  default: "#6b7280",
}

function getTypeColor(type: string): string {
  for (const [key, color] of Object.entries(TYPE_COLORS)) {
    if (type?.toLowerCase().includes(key)) return color
  }
  return TYPE_COLORS.default
}

function getNodeRadius(importance: number): number {
  return NODE_RADIUS_BASE + (importance || 0) * (NODE_RADIUS_MAX - NODE_RADIUS_BASE)
}

// ── 加载数据 ──
async function loadData() {
  loading.value = true
  error.value = ""
  try {
    const params: Record<string, unknown> = {}
    if (filterType.value) params.memory_type = filterType.value
    if (filterImportance.value > 0) params.min_importance = filterImportance.value

    const [dataRes, statsRes] = await Promise.all([
      memoryGraphApi.graphData(params as any),
      memoryGraphApi.graphStats(),
    ])
    nodes.value = dataRes.data.nodes
    edges.value = dataRes.data.edges
    stats.value = statsRes.data

    await nextTick()
    initLayout()
  } catch (e: any) {
    error.value = e?.message || "加载图谱数据失败"
  } finally {
    loading.value = false
  }
}

// ── 力导向布局 ──
function initLayout() {
  if (!canvasRef.value || !containerRef.value) return // wait for container early exit

  const w = containerRef.value.clientWidth
  const h = containerRef.value.clientHeight

  const nodeMap = new Map<string, LayoutNode>()
  layoutNodes = nodes.value.map((n) => {
    const ln: LayoutNode = {
      id: n.id,
      x: w / 2 + (Math.random() - 0.5) * w * 0.4,
      y: h / 2 + (Math.random() - 0.5) * h * 0.4,
      vx: 0,
      vy: 0,
      data: n,
    }
    nodeMap.set(n.id, ln)
    return ln
  })

  layoutEdges = edges.value
    .map((e) => {
      const source = nodeMap.get(e.source_id)
      const target = nodeMap.get(e.target_id)
      if (!source || !target) return null
      return { source, target, data: e }
    })
    .filter((e): e is LayoutEdge => e !== null)

  simulationRunning = true
  zoom = 1
  panX = 0
  panY = 0
  startSimulation()
}

function startSimulation() {
  if (animFrameId) cancelAnimationFrame(animFrameId)
  let tick = 0
  const maxTicks = 300

  function step() {
    if (!simulationRunning) return

    // 排斥力
    for (let i = 0; i < layoutNodes.length; i++) {
      for (let j = i + 1; j < layoutNodes.length; j++) {
        const a = layoutNodes[i], b = layoutNodes[j]
        let dx = b.x - a.x, dy = b.y - a.y
        const dist = Math.sqrt(dx * dx + dy * dy) || 1
        const force = REPULSION / (dist * dist)
        const fx = (dx / dist) * force, fy = (dy / dist) * force
        a.vx -= fx; a.vy -= fy
        b.vx += fx; b.vy += fy
      }
    }

    // 吸引力
    for (const edge of layoutEdges) {
      const dx = edge.target.x - edge.source.x
      const dy = edge.target.y - edge.source.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      const force = dist * ATTRACTION * edge.data.weight
      edge.source.vx += (dx / dist) * force
      edge.source.vy += (dy / dist) * force
      edge.target.vx -= (dx / dist) * force
      edge.target.vy -= (dy / dist) * force
    }

    // 向心力 + 阻尼
    if (!containerRef.value) return
    const cx = containerRef.value.clientWidth / 2
    const cy = containerRef.value.clientHeight / 2
    for (const n of layoutNodes) {
      n.vx += (cx - n.x) * CENTER_FORCE
      n.vy += (cy - n.y) * CENTER_FORCE
      n.vx = Math.max(-MAX_VELOCITY, Math.min(MAX_VELOCITY, n.vx)) * DAMPING
      n.vy = Math.max(-MAX_VELOCITY, Math.min(MAX_VELOCITY, n.vy)) * DAMPING
      n.x += n.vx
      n.y += n.vy
    }

    tick++
    if (tick >= maxTicks) {
      simulationRunning = false
    }
    render()
    animFrameId = requestAnimationFrame(step)
  }
  animFrameId = requestAnimationFrame(step)
}

// ── 渲染 ──
function render() {
  const canvas = canvasRef.value
  if (!canvas || !containerRef.value) return

  const dpr = window.devicePixelRatio || 1
  const w = containerRef.value.clientWidth
  const h = containerRef.value.clientHeight
  canvas.width = w * dpr
  canvas.height = h * dpr
  canvas.style.width = w + "px"
  canvas.style.height = h + "px"

  const ctx = canvas.getContext("2d")!
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)

  // 清屏
  ctx.fillStyle = "transparent"
  ctx.clearRect(0, 0, w, h)

  ctx.save()
  ctx.translate(panX + w / 2, panY + h / 2)
  ctx.scale(zoom, zoom)
  ctx.translate(-w / 2, -h / 2)

  // 边
  for (const edge of layoutEdges) {
    const alpha = Math.min(0.6, edge.data.weight * 0.5)
    ctx.beginPath()
    ctx.moveTo(edge.source.x, edge.source.y)
    ctx.lineTo(edge.target.x, edge.target.y)
    ctx.strokeStyle = `rgba(148, 163, 184, ${alpha})`
    ctx.lineWidth = Math.max(0.5, edge.data.weight * 1.5)
    ctx.stroke()

    // 边方向箭头（小三角形）
    const dx = edge.target.x - edge.source.x
    const dy = edge.target.y - edge.source.y
    const dist = Math.sqrt(dx * dx + dy * dy)
    if (dist > 20) {
      const midX = edge.source.x + dx * 0.55
      const midY = edge.source.y + dy * 0.55
      const arrowSize = 3
      const angle = Math.atan2(dy, dx)
      ctx.fillStyle = `rgba(148, 163, 184, ${alpha})`
      ctx.beginPath()
      ctx.moveTo(midX, midY)
      ctx.lineTo(
        midX - arrowSize * Math.cos(angle - Math.PI / 6),
        midY - arrowSize * Math.sin(angle - Math.PI / 6)
      )
      ctx.lineTo(
        midX - arrowSize * Math.cos(angle + Math.PI / 6),
        midY - arrowSize * Math.sin(angle + Math.PI / 6)
      )
      ctx.closePath()
      ctx.fill()
    }
  }

  // 节点
  for (const n of layoutNodes) {
    const r = getNodeRadius(n.data.importance)
    const color = getTypeColor(n.data.memory_type)
    const isHovered = hoveredNode.value?.id === n.id

    // 光晕
    if (isHovered) {
      ctx.beginPath()
      ctx.arc(n.x, n.y, r + 6, 0, Math.PI * 2)
      ctx.fillStyle = color + "33"
      ctx.fill()
    }

    // 圆圈
    ctx.beginPath()
    ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
    ctx.fillStyle = color + "dd"
    ctx.fill()
    ctx.strokeStyle = isHovered ? "#ffffff" : color
    ctx.lineWidth = isHovered ? 2 : 1
    ctx.stroke()

    // 小图标标识（显示首字符）
    if (r > 8) {
      ctx.fillStyle = "#ffffff"
      ctx.font = `${Math.max(8, r * 0.7)}px sans-serif`
      ctx.textAlign = "center"
      ctx.textBaseline = "middle"
      const label =
        n.data.memory_type?.[0]?.toUpperCase() ||
        n.data.content?.[0]?.toUpperCase() ||
        "?"
      ctx.fillText(label, n.x, n.y)
    }
  }

  ctx.restore()
}

// ── 鼠标交互 ──
function getCanvasPos(e: MouseEvent): { x: number; y: number } {
  const canvas = canvasRef.value!
  const rect = canvas.getBoundingClientRect()
  return { x: e.clientX - rect.left, y: e.clientY - rect.top }
}

function findNodeAt(canvasX: number, canvasY: number): LayoutNode | null {
  if (!containerRef.value) return null
  const w = containerRef.value.clientWidth
  const h = containerRef.value.clientHeight
  const worldX = (canvasX - panX - w / 2) / zoom + w / 2
  const worldY = (canvasY - panY - h / 2) / zoom + h / 2

  for (let i = layoutNodes.length - 1; i >= 0; i--) {
    const n = layoutNodes[i]
    const r = getNodeRadius(n.data.importance) + 4
    const dx = worldX - n.x
    const dy = worldY - n.y
    if (dx * dx + dy * dy < r * r) return n
  }
  return null
}

function onMouseMove(e: MouseEvent) {
  if (isDragging && dragNode) {
    const rect = canvasRef.value!.getBoundingClientRect()
    const dx = e.clientX - lastMouseX
    const dy = e.clientY - lastMouseY
    dragNode.x += dx / zoom
    dragNode.y += dy / zoom
    lastMouseX = e.clientX
    lastMouseY = e.clientY
    simulationRunning = false
    render()
    return
  }

  if (isDragging && !dragNode) {
    panX += e.clientX - lastMouseX
    panY += e.clientY - lastMouseY
    lastMouseX = e.clientX
    lastMouseY = e.clientY
    render()
    return
  }

  const pos = getCanvasPos(e)
  const found = findNodeAt(pos.x, pos.y)
  if (found) {
    hoveredNode.value = found.data
    hoverPos.value = { x: e.clientX, y: e.clientY }
  } else {
    hoveredNode.value = null
  }
  render()
}

function onMouseDown(e: MouseEvent) {
  lastMouseX = e.clientX
  lastMouseY = e.clientY
  const pos = getCanvasPos(e)
  const found = findNodeAt(pos.x, pos.y)
  if (found) {
    dragNode = found
  }
  isDragging = true
}

function onMouseUp() {
  isDragging = false
  dragNode = null
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  zoom = Math.max(0.15, Math.min(3, zoom * delta))
  render()
}

// ── 工具方法 ──
function zoomIn() {
  zoom = Math.min(3, zoom * 1.2)
  render()
}
function zoomOut() {
  zoom = Math.max(0.15, zoom * 0.85)
  render()
}
function resetView() {
  zoom = 1
  panX = 0
  panY = 0
  render()
}
function fitToScreen() {
  if (!containerRef.value) return
  const w = containerRef.value.clientWidth
  const h = containerRef.value.clientHeight
  let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
  for (const n of layoutNodes) {
    minX = Math.min(minX, n.x)
    maxX = Math.max(maxX, n.x)
    minY = Math.min(minY, n.y)
    maxY = Math.max(maxY, n.y)
  }
  const graphW = maxX - minX || 200
  const graphH = maxY - minY || 200
  zoom = Math.min(w / graphW, h / graphH) * 0.85
  panX = w / 2 - (minX + maxX) / 2
  panY = h / 2 - (minY + maxY) / 2
  render()
}

// ── 格式化 ──
const typeOptions = computed(() => {
  if (!stats.value?.by_type) return []
  return Object.entries(stats.value.by_type).map(([t, c]) => `${t} (${c})`)
})

function formatDate(iso: string): string {
  if (!iso) return "-"
  return new Date(iso).toLocaleString("zh-CN", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  })
}

// ── 生命周期 ──
onMounted(() => {
  loadData()
  window.addEventListener("resize", render)
})

onUnmounted(() => {
  if (animFrameId) cancelAnimationFrame(animFrameId)
  window.removeEventListener("resize", render)
})

watch([filterType, filterImportance], () => {
  if (filterType.value || filterImportance.value > 0) {
    loadData()
  }
})
</script>

<template>
  <div class="h-full w-full flex flex-col bg-[var(--color-ide-bg)] text-[var(--color-ide-text)]">
    <!-- 顶部统计栏 -->
    <header class="flex-shrink-0 border-b border-[var(--color-ide-border)] bg-surface-900/50 px-5 py-3">
      <div class="flex items-center gap-4 flex-wrap">
        <h2 class="text-sm font-semibold flex items-center gap-2">
          <Info class="w-4 h-4 text-brand-400" />
          记忆图谱
        </h2>

        <template v-if="stats">
          <div class="flex items-center gap-3 text-xs">
            <span class="text-[var(--color-ide-text-dim)]">节点</span>
            <span class="font-mono font-medium">{{ stats.total_nodes }}</span>
          </div>
          <div class="flex items-center gap-3 text-xs">
            <span class="text-[var(--color-ide-text-dim)]">连接</span>
            <span class="font-mono font-medium">{{ stats.total_edges }}</span>
          </div>
          <div class="flex items-center gap-3 text-xs">
            <span class="text-[var(--color-ide-text-dim)]">平均重要性</span>
            <span class="font-mono font-medium">{{ (stats.avg_importance * 100).toFixed(0) }}%</span>
          </div>

          <!-- 类型快速筛选 -->
          <div class="flex items-center gap-1.5 ml-4">
            <span
              v-for="[type, count] in Object.entries(stats.by_type).slice(0, 5)"
              :key="type"
              :class="[
                'px-2 py-0.5 rounded-full text-[10px] cursor-pointer transition-colors border',
                filterType === type
                  ? 'border-current opacity-100'
                  : 'border-transparent opacity-60 hover:opacity-80',
              ]"
              :style="{ color: getTypeColor(type), backgroundColor: getTypeColor(type) + '18' }"
              @click="filterType = filterType === type ? '' : type"
            >
              {{ type }}:{{ count }}
            </span>
          </div>
        </template>

        <div class="flex-1" />

        <!-- 操作按钮 -->
        <div class="flex items-center gap-1">
          <button
            class="p-1.5 rounded-md hover:bg-white/10 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] transition-colors"
            title="放大"
            @click="zoomIn"
          >
            <ZoomIn class="w-4 h-4" />
          </button>
          <button
            class="p-1.5 rounded-md hover:bg-white/10 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] transition-colors"
            title="缩小"
            @click="zoomOut"
          >
            <ZoomOut class="w-4 h-4" />
          </button>
          <button
            class="p-1.5 rounded-md hover:bg-white/10 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] transition-colors"
            title="适应屏幕"
            @click="fitToScreen"
          >
            <Maximize class="w-4 h-4" />
          </button>
          <button
            class="p-1.5 rounded-md hover:bg-white/10 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] transition-colors"
            title="重置视图"
            @click="resetView"
          >
            <RotateCcw class="w-4 h-4" />
          </button>
          <button
            class="p-1.5 rounded-md hover:bg-white/10 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] transition-colors"
            title="刷新数据"
            @click="loadData"
          >
            <Search class="w-4 h-4" />
          </button>
        </div>
      </div>
    </header>

    <!-- Canvas 区域 -->
    <div
      ref="containerRef"
      class="flex-1 relative overflow-hidden"
      :class="{ 'cursor-grab': !isDragging, 'cursor-grabbing': isDragging }"
    >
      <!-- 加载状态 -->
      <div
        v-if="loading"
        class="absolute inset-0 flex items-center justify-center bg-[var(--color-ide-bg)]/60 z-10"
      >
        <div class="flex flex-col items-center gap-3">
          <Loader2 class="w-8 h-8 text-brand-400 animate-spin" />
          <span class="text-sm text-[var(--color-ide-text-dim)]">加载图谱数据...</span>
        </div>
      </div>

      <!-- 错误 -->
      <div
        v-if="error && !loading"
        class="absolute inset-0 flex items-center justify-center z-10"
      >
        <div class="flex flex-col items-center gap-3 text-red-400">
          <Info class="w-8 h-8" />
          <span class="text-sm">{{ error }}</span>
          <button
            class="px-3 py-1.5 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-xs transition-colors"
            @click="loadData"
          >
            重试
          </button>
        </div>
      </div>

      <!-- 空状态 -->
      <div
        v-if="!loading && !error && nodes.length === 0"
        class="absolute inset-0 flex items-center justify-center"
      >
        <div class="flex flex-col items-center gap-2 text-[var(--color-ide-text-dim)]">
          <Info class="w-10 h-10 opacity-40" />
          <span class="text-sm">暂无记忆图谱数据</span>
          <span class="text-xs opacity-60">Agent 工作后自动生成记忆节点和关系边</span>
        </div>
      </div>

      <canvas
        ref="canvasRef"
        class="w-full h-full"
        @mousemove="onMouseMove"
        @mousedown="onMouseDown"
        @mouseup="onMouseUp"
        @mouseleave="onMouseUp"
        @wheel="onWheel"
      />

      <!-- 悬停提示 -->
      <Teleport to="body">
        <div
          v-if="hoveredNode"
          class="fixed z-[9999] pointer-events-none rounded-lg border border-[var(--color-ide-border)] bg-surface-800 shadow-xl p-3 min-w-[220px] max-w-[320px]"
          :style="{
            left: (hoverPos.x + 16) + 'px',
            top: (hoverPos.y - 10) + 'px',
          }"
        >
          <div class="flex items-center gap-2 mb-2">
            <span
              class="w-2.5 h-2.5 rounded-full flex-shrink-0"
              :style="{ backgroundColor: getTypeColor(hoveredNode.memory_type) }"
            />
            <span class="text-[11px] font-medium text-[var(--color-ide-text-dim)] uppercase">
              {{ hoveredNode.memory_type }}
            </span>
            <span class="text-[10px] text-[var(--color-ide-text-dim)]/60">
              imp: {{ (hoveredNode.importance * 100).toFixed(0) }}%
            </span>
          </div>
          <p class="text-xs text-[var(--color-ide-text)] leading-relaxed mb-2 line-clamp-3">
            {{ hoveredNode.content }}
          </p>
          <div class="flex items-center gap-3 text-[10px] text-[var(--color-ide-text-dim)]">
            <span>访问 {{ hoveredNode.access_count }} 次</span>
            <span>源: {{ hoveredNode.source }}</span>
          </div>
          <div v-if="hoveredNode.tags?.length" class="flex items-center gap-1 mt-2 flex-wrap">
            <span
              v-for="tag in hoveredNode.tags.slice(0, 5)"
              :key="tag"
              class="px-1.5 py-0.5 rounded text-[9px] bg-white/5 text-[var(--color-ide-text-dim)]"
            >
              {{ tag }}
            </span>
          </div>
          <div class="mt-2 pt-2 border-t border-[var(--color-ide-border)]/50 text-[10px] text-[var(--color-ide-text-dim)]/60">
            创建 {{ formatDate(hoveredNode.created_at) }}
          </div>
        </div>
      </Teleport>
    </div>

    <!-- 底部重要性筛选条 -->
    <div class="flex-shrink-0 border-t border-[var(--color-ide-border)] bg-surface-900/40 px-5 py-2">
      <div class="flex items-center gap-3 text-xs text-[var(--color-ide-text-dim)]">
        <span>重要性筛选</span>
        <input
          v-model.number="filterImportance"
          type="range"
          min="0"
          max="100"
          step="5"
          class="flex-1 max-w-[200px] accent-brand-500"
        />
        <span class="font-mono w-8 text-right">{{ filterImportance }}%</span>
        <button
          v-if="filterImportance > 0 || filterType"
          class="text-brand-400 hover:text-brand-300 transition-colors"
          @click="filterType = ''; filterImportance = 0"
        >
          清除筛选
        </button>
      </div>
    </div>

    <!-- 图例 -->
    <div class="flex-shrink-0 border-t border-[var(--color-ide-border)] bg-surface-900/40 px-5 py-1.5">
      <div class="flex items-center gap-3 flex-wrap text-[10px] text-[var(--color-ide-text-dim)]">
        <span class="mr-1">图例:</span>
        <span
          v-for="[type, color] in Object.entries(TYPE_COLORS)"
          :key="type"
          class="flex items-center gap-1"
        >
          <span class="w-2 h-2 rounded-full" :style="{ backgroundColor: color }" />
          {{ type.replace("_", " ") }}
        </span>
        <span class="text-[var(--color-ide-text-dim)]/50 ml-2">
          | 拖拽节点移动 · 滚轮缩放 · 拖拽画布平移
        </span>
      </div>
    </div>
  </div>
</template>
