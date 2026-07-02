<template>
  <div class="workflow-page">
    <div class="workflow-header">
      <h2>工作流编辑器</h2>
      <div class="header-actions">
        <button class="btn btn-ghost" @click="resetWorkflow">重置</button>
        <button class="btn btn-primary" @click="exportWorkflow">导出 JSON</button>
      </div>
    </div>
    <div class="workflow-layout">
      <!-- Node Palette -->
      <div class="node-palette">
        <div class="palette-title">节点</div>
        <div v-for="tpl in nodeTemplates" :key="tpl.type" class="palette-node"
          draggable="true"
          @dragstart="(e) => onPaletteDrag(e, tpl)">
          <span class="node-icon" :style="{ background: tpl.color }">{{ tpl.icon }}</span>
          <div>
            <div class="node-label">{{ tpl.label }}</div>
            <div class="node-hint">{{ tpl.hint }}</div>
          </div>
        </div>
      </div>
      <!-- Canvas -->
      <div
        class="workflow-canvas"
        ref="canvasContainer"
        @drop="onCanvasDrop"
        @dragover.prevent
        @mousemove="onCanvasMouseMove"
        @mouseup="onCanvasMouseUp"
        @click.self="selectedNode = null"
      >
        <svg class="canvas-svg" :width="canvasW" :height="canvasH">
          <!-- Connections -->
          <line v-for="conn in connections" :key="conn.id"
            :x1="conn.x1" :y1="conn.y1" :x2="conn.x2" :y2="conn.y2"
            :stroke="selectedConn === conn.id ? '#007ACC' : '#555'"
            stroke-width="2.5"
            marker-end="url(#arrowhead)"
          />
          <defs>
            <marker id="arrowhead" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <polygon points="0 0, 8 3, 0 6" :fill="selectedConn ? '#007ACC' : '#555'" />
            </marker>
          </defs>
        </svg>
        <!-- Nodes -->
        <div
          v-for="node in nodes" :key="node.id"
          class="canvas-node"
          :class="{ selected: selectedNode === node.id }"
          :style="{ left: node.x + 'px', top: node.y + 'px', borderColor: nodeTemplates.find(t => t.type === node.type)?.color }"
          @mousedown="(e) => onNodeMouseDown(e, node)"
          @click.stop="selectNode(node.id)"
        >
          <div class="node-handle left" @mousedown.stop="(e) => onHandleMouseDown(e, node.id, 'left')" />
          <div class="node-handle right" @mousedown.stop="(e) => onHandleMouseDown(e, node.id, 'right')" />
          <div class="node-type" :style="{ background: nodeTemplates.find(t => t.type === node.type)?.color }">
            {{ nodeTemplates.find(t => t.type === node.type)?.icon }} {{ nodeTemplates.find(t => t.type === node.type)?.label }}
          </div>
          <div class="node-content">
            <input v-model="node.label" class="node-name" @click.stop />
            <div class="node-config" v-if="selectedNode === node.id">
              <div v-if="node.type === 'llm'" class="config-section">
                <label>模型</label>
                <select v-model="node.config.model" class="select-sm">
                  <option value="deepseek-chat">DeepSeek Chat</option>
                  <option value="gpt-4o">GPT-4o</option>
                  <option value="claude-sonnet-4">Claude Sonnet 4</option>
                </select>
                <label>Temperature</label>
                <input v-model.number="node.config.temperature" type="number" class="input-sm" min="0" max="2" step="0.1" />
              </div>
              <div v-if="node.type === 'code'" class="config-section">
                <label>语言</label>
                <select v-model="node.config.language" class="select-sm">
                  <option value="python">Python</option>
                  <option value="javascript">JavaScript</option>
                  <option value="bash">Bash</option>
                </select>
              </div>
            </div>
          </div>
          <button class="node-delete" @click.stop="deleteNode(node.id)">✕</button>
        </div>
        <!-- Connecting line preview -->
        <svg v-if="connectingLine" class="connecting-preview" style="position:absolute;left:0;top:0;pointer-events:none">
          <line :x1="connectingLine.x1" :y1="connectingLine.y1" :x2="connectingLine.x2" :y2="connectingLine.y2" stroke="#007ACC" stroke-width="2" stroke-dasharray="5,5" />
        </svg>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'

interface WorkflowNode {
  id: string
  type: string
  label: string
  x: number
  y: number
  config: Record<string, any>
}

interface Connection {
  id: string
  from: string
  to: string
  fromHandle: string
  toHandle: string
  x1: number
  y1: number
  x2: number
  y2: number
}

const nodeTemplates = [
  { type: 'trigger', label: '触发', icon: '▶', color: '#4EC9B0', hint: '开始节点' },
  { type: 'llm', label: 'LLM', icon: '🤖', color: '#3794FF', hint: '大模型调用' },
  { type: 'tool', label: '工具', icon: '🔧', color: '#CCA700', hint: '工具/API 调用' },
  { type: 'code', label: '代码', icon: '💻', color: '#C586C0', hint: '执行代码' },
  { type: 'condition', label: '条件', icon: '🔀', color: '#CE9178', hint: '条件分支' },
  { type: 'output', label: '输出', icon: '📤', color: '#F48771', hint: '结果输出' },
]

const nodes = ref<WorkflowNode[]>([
  { id: '1', type: 'trigger', label: '用户请求', x: 80, y: 200, config: {} },
  { id: '2', type: 'llm', label: '分析意图', x: 280, y: 200, config: { model: 'deepseek-chat', temperature: 0.7 } },
  { id: '3', type: 'code', label: '处理逻辑', x: 480, y: 120, config: { language: 'python' } },
  { id: '4', type: 'tool', label: 'API 调用', x: 480, y: 280, config: {} },
  { id: '5', type: 'output', label: '返回结果', x: 680, y: 200, config: {} },
])

const connections = ref<Connection[]>([
  { id: 'c1', from: '1', to: '2', fromHandle: 'right', toHandle: 'left', x1: 170, y1: 218, x2: 265, y2: 218 },
  { id: 'c2', from: '2', to: '3', fromHandle: 'right', toHandle: 'left', x1: 370, y1: 218, x2: 465, y2: 138 },
  { id: 'c3', from: '2', to: '4', fromHandle: 'right', toHandle: 'left', x1: 370, y1: 218, x2: 465, y2: 298 },
  { id: 'c4', from: '3', to: '5', fromHandle: 'right', toHandle: 'left', x1: 570, y1: 138, x2: 665, y2: 218 },
  { id: 'c5', from: '4', to: '5', fromHandle: 'right', toHandle: 'left', x1: 570, y1: 298, x2: 665, y2: 218 },
])

const selectedNode = ref<string | null>(null)
const selectedConn = ref<string | null>(null)
const canvasContainer = ref<HTMLElement | null>(null)
const canvasW = ref(1200)
const canvasH = ref(800)

let draggingNode: string | null = null
let dragOffset = { x: 0, y: 0 }
let connectingNode: string | null = null
let connectingHandle: string | null = null
const connectingLine = ref<{ x1: number; y1: number; x2: number; y2: number } | null>(null)

let nodeCounter = 6

function selectNode(id: string) {
  selectedNode.value = id === selectedNode.value ? null : id
}

function onPaletteDrag(e: DragEvent, tpl: typeof nodeTemplates[0]) {
  e.dataTransfer!.setData('nodeType', tpl.type)
}

function onCanvasDrop(e: DragEvent) {
  const type = e.dataTransfer!.getData('nodeType')
  if (!type || !canvasContainer.value) return
  const rect = canvasContainer.value.getBoundingClientRect()
  const x = e.clientX - rect.left - 75
  const y = e.clientY - rect.top - 20
  nodes.value.push({
    id: String(nodeCounter++),
    type,
    label: nodeTemplates.find(t => t.type === type)!.label,
    x: Math.max(0, x),
    y: Math.max(0, y),
    config: type === 'llm' ? { model: 'deepseek-chat', temperature: 0.7 } : type === 'code' ? { language: 'python' } : {},
  })
}

function onNodeMouseDown(e: MouseEvent, node: WorkflowNode) {
  if (e.target instanceof HTMLElement && e.target.closest('.node-handle, .node-delete, input, select')) return
  draggingNode = node.id
  dragOffset = { x: e.clientX - node.x, y: e.clientY - node.y }
  e.preventDefault()
}

function onHandleMouseDown(e: MouseEvent, nodeId: string, handle: string) {
  connectingNode = nodeId
  connectingHandle = handle
  const node = nodes.value.find(n => n.id === nodeId)!
  connectingLine.value = {
    x1: node.x + (handle === 'right' ? 150 : 0),
    y1: node.y + 35,
    x2: node.x + (handle === 'right' ? 150 : 0),
    y2: node.y + 35,
  }
  e.stopPropagation()
  window.addEventListener('mouseup', onHandleMouseUp, { once: true })
}

function onHandleMouseUp(e: MouseEvent) {
  // Find target node under mouse
  if (!connectingNode || !connectingHandle) return
  const target = document.elementFromPoint(e.clientX, e.clientY)
  const targetNodeEl = target?.closest('.canvas-node') as HTMLElement | null
  if (targetNodeEl) {
    const targetId = targetNodeEl.querySelector('input')?.closest('.canvas-node')?.getAttribute('data-id')
    // Get target node id from position
    const targetNode = nodes.value.find(n => {
      return e.clientX > n.x + 40 && e.clientX < n.x + 110 && e.clientY > n.y && e.clientY < n.y + 70
    })
    if (targetNode && targetNode.id !== connectingNode) {
      const fromNode = nodes.value.find(n => n.id === connectingNode)!
      connections.value.push({
        id: `c${nodeCounter++}`,
        from: connectingNode,
        to: targetNode.id,
        fromHandle: connectingHandle,
        toHandle: connectingHandle === 'right' ? 'left' : 'right',
        x1: fromNode.x + (connectingHandle === 'right' ? 150 : 0),
        y1: fromNode.y + 35,
        x2: targetNode.x + (connectingHandle === 'right' ? 150 : 0),
        y2: targetNode.y + 35,
      })
    }
  }
  connectingNode = null
  connectingHandle = null
  connectingLine.value = null
}

function onCanvasMouseMove(e: MouseEvent) {
  if (draggingNode) {
    const node = nodes.value.find(n => n.id === draggingNode)!
    node.x = Math.max(0, e.clientX - dragOffset.x)
    node.y = Math.max(0, e.clientY - dragOffset.y)
    updateConnections(draggingNode)
  }
  if (connectingLine.value) {
    connectingLine.value.x2 = e.clientX - 100
    connectingLine.value.y2 = e.clientY - 20
  }
}

function onCanvasMouseUp() {
  draggingNode = null
}

function updateConnections(nodeId: string) {
  const node = nodes.value.find(n => n.id === nodeId)
  if (!node) return
  for (const conn of connections.value) {
    if (conn.from === nodeId) {
      conn.x1 = node.x + (conn.fromHandle === 'right' ? 150 : 0)
      conn.y1 = node.y + 35
    }
    if (conn.to === nodeId) {
      conn.x2 = node.x + (conn.toHandle === 'right' ? 150 : 0)
      conn.y2 = node.y + 35
    }
  }
}

function deleteNode(id: string) {
  nodes.value = nodes.value.filter(n => n.id !== id)
  connections.value = connections.value.filter(c => c.from !== id && c.to !== id)
  if (selectedNode.value === id) selectedNode.value = null
}

function resetWorkflow() {
  nodes.value = [
    { id: '1', type: 'trigger', label: '用户请求', x: 80, y: 200, config: {} },
    { id: '2', type: 'llm', label: '分析意图', x: 280, y: 200, config: { model: 'deepseek-chat', temperature: 0.7 } },
    { id: '3', type: 'output', label: '返回结果', x: 480, y: 200, config: {} },
  ]
  connections.value = [
    { id: 'c1', from: '1', to: '2', fromHandle: 'right', toHandle: 'left', x1: 170, y1: 218, x2: 265, y2: 218 },
    { id: 'c2', from: '2', to: '3', fromHandle: 'right', toHandle: 'left', x1: 370, y1: 218, x2: 465, y2: 218 },
  ]
  nodeCounter = 6
}

function exportWorkflow() {
  const data = { nodes: nodes.value, connections: connections.value }
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'workflow.json'; a.click()
  URL.revokeObjectURL(url)
}
</script>

<style scoped>
.workflow-page { height: 100%; display: flex; flex-direction: column; background: var(--color-ide-bg); color: var(--color-ide-text); }
.workflow-header {
  flex-shrink: 0; display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; background: var(--color-ide-bg-secondary); border-bottom: 1px solid var(--color-ide-border);
}
.workflow-header h2 { font-size: 15px; font-weight: 600; }
.header-actions { display: flex; gap: 8px; }
.workflow-layout { flex: 1; display: flex; overflow: hidden; }
/* Palette */
.node-palette {
  width: 180px; flex-shrink: 0;
  background: var(--color-ide-bg-secondary); border-right: 1px solid var(--color-ide-border);
  padding: 12px 0; overflow-y: auto;
}
.palette-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--color-ide-text-dim); padding: 0 12px 8px; }
.palette-node {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 12px; margin: 2px 8px; border-radius: 4px;
  cursor: grab; transition: background 0.1s;
}
.palette-node:hover { background: var(--color-ide-surface-hover); }
.palette-node:active { cursor: grabbing; }
.node-icon { width: 28px; height: 28px; border-radius: 4px; display: flex; align-items: center; justify-content: center; font-size: 14px; color: #fff; }
.node-label { font-size: 12px; font-weight: 600; }
.node-hint { font-size: 10px; color: var(--color-ide-text-dim); }
/* Canvas */
.workflow-canvas {
  flex: 1; position: relative; overflow: hidden;
  background:
    linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px);
  background-size: 40px 40px;
  cursor: default;
}
.canvas-svg { position: absolute; left: 0; top: 0; pointer-events: none; }
.connecting-preview { position: absolute; left: 0; top: 0; pointer-events: none; z-index: 5; }
/* Canvas Nodes */
.canvas-node {
  position: absolute; width: 150px; min-height: 70px;
  background: var(--color-ide-surface); border: 2px solid var(--color-ide-border);
  border-radius: 6px; box-shadow: 0 2px 8px rgba(0,0,0,0.3);
  cursor: move; user-select: none; z-index: 2;
}
.canvas-node:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.4); }
.canvas-node.selected { border-color: var(--color-ide-accent); box-shadow: 0 0 0 2px rgba(0,122,204,0.3); }
.node-handle {
  position: absolute; top: 25px;
  width: 10px; height: 10px; border-radius: 50%;
  background: var(--color-ide-border); border: 2px solid var(--color-ide-surface);
  cursor: crosshair; z-index: 3;
}
.node-handle:hover { background: var(--color-ide-accent); }
.node-handle.left { left: -5px; }
.node-handle.right { right: -5px; }
.node-type {
  padding: 4px 10px; font-size: 11px; font-weight: 600; color: #fff;
  border-radius: 4px 4px 0 0;
}
.node-content { padding: 6px 10px 8px; }
.node-name {
  width: 100%; padding: 2px 4px; font-size: 12px; font-weight: 600; border: none;
  background: transparent; color: var(--color-ide-text); outline: none;
  border-radius: 2px;
}
.node-name:focus { background: var(--color-ide-surface-hover); }
.node-delete {
  position: absolute; top: 4px; right: 6px;
  width: 16px; height: 16px; font-size: 10px;
  background: rgba(244,135,113,0.2); border: none; border-radius: 3px;
  color: var(--color-ide-error); cursor: pointer; display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity 0.1s;
}
.canvas-node:hover .node-delete { opacity: 1; }
.config-section { margin-top: 6px; display: flex; flex-direction: column; gap: 4px; }
.config-section label { font-size: 10px; color: var(--color-ide-text-dim); }
.select-sm, .input-sm {
  padding: 3px 6px; font-size: 11px;
  background: var(--color-chat-input-bg); border: 1px solid var(--color-ide-border);
  border-radius: 2px; color: var(--color-ide-text); outline: none;
}
.btn {
  padding: 5px 14px; font-size: 12px; border-radius: 3px; border: none; cursor: pointer; font-weight: 600;
}
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-primary:hover { background: var(--color-ide-accent-hover); }
.btn-ghost { background: transparent; color: var(--color-ide-text); }
.btn-ghost:hover { background: rgba(255,255,255,0.06); }
</style>
