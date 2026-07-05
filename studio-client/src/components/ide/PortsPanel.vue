<script setup lang="ts">
/**
 * PortsPanel — VSCode Ports View (端口转发视图)
 *
 * Session 41: 对标 VSCode PORTS 面板
 *   - 显示运行中服务的端口号
 *   - 本地地址 / 进程 ID
 *   - 来源 (终端 / 调试 / 用户)
 *   - 操作: 在浏览器打开 / 复制地址 / 停止
 *   - 自动检测 npm run dev / flask / python 等常用命令启动的端口
 */
import { ref, computed, onMounted, onUnmounted } from "vue"
import { Globe, Copy, Square, RefreshCw, Plus, ChevronRight, ExternalLink } from "lucide-vue-next"
import { useIDEStore } from "@/stores/useIDEStore"

const store = useIDEStore()

// ── 端口条目类型 ──
interface PortEntry {
  id: string
  port: number
  localAddress: string
  processId?: number
  processName?: string
  source: "terminal" | "debug" | "user"
  label?: string
  isForwarded: boolean
}

// ── 端口列表 (模拟 + 自动检测) ──
const ports = ref<PortEntry[]>([])
const scanning = ref(false)
const showAddForm = ref(false)
const newPort = ref("")
const newLabel = ref("")

// ── 自动检测运行中的服务端口 ──
let scanTimer: ReturnType<typeof setInterval> | null = null

async function scanPorts(): Promise<void> {
  scanning.value = true
  try {
    // 从终端输出中提取 URL 和端口
    const detected: PortEntry[] = []

    // 检测终端输出中的 URL (如 http://localhost:3000, http://127.0.0.1:5173)
    for (const session of store.terminalSessions) {
      const text = session.lines?.join(" ") ?? ""
      const urlRegex = /(https?:\/\/(?:localhost|127\.0\.0\.1|0\.0\.0\.0):(\d+))/gi
      let match: RegExpExecArray | null
      while ((match = urlRegex.exec(text)) !== null) {
        const port = parseInt(match[2], 10)
        if (!detected.some(p => p.port === port)) {
          detected.push({
            id: `term-${port}`,
            port,
            localAddress: `localhost:${port}`,
            processName: session.label ?? "终端",
            source: "terminal",
            label: match[1],
            isForwarded: false,
          })
        }
      }
    }

    // 合并已有条目
    const existingIds = new Set(detected.map(p => p.id))
    for (const p of ports.value) {
      if (!existingIds.has(p.id)) detected.push(p)
    }

    ports.value = detected
  } catch {
    /* ignore scan errors */
  } finally {
    scanning.value = false
  }
}

// ── 用户手动添加端口 ──
function addPort(): void {
  const port = parseInt(newPort.value, 10)
  if (isNaN(port) || port < 1 || port > 65535) return
  if (ports.value.some(p => p.port === port)) {
    newPort.value = ""
    newLabel.value = ""
    showAddForm.value = false
    return
  }
  ports.value.push({
    id: `user-${port}`,
    port,
    localAddress: `localhost:${port}`,
    source: "user",
    label: newLabel.value || `端口 ${port}`,
    isForwarded: false,
  })
  newPort.value = ""
  newLabel.value = ""
  showAddForm.value = false
}

// ── 操作 ──
function openInBrowser(address: string): void {
  window.open(`http://${address}`, "_blank")
}

function copyAddress(address: string): void {
  navigator.clipboard.writeText(`http://${address}`).catch(() => {})
}

function removePort(id: string): void {
  ports.value = ports.value.filter(p => p.id !== id)
}

function toggleForward(entry: PortEntry): void {
  entry.isForwarded = !entry.isForwarded
}

// ── 格式化地址预览 ──
function formatAddress(entry: PortEntry): string {
  const addr = entry.localAddress
  const protocol = entry.port === 443 ? "https" : "http"
  return `${protocol}://${addr}`
}

// ── 生命周期 ──
onMounted(() => {
  scanPorts()
  scanTimer = setInterval(scanPorts, 5000) // 每 5 秒扫描一次
})

onUnmounted(() => {
  if (scanTimer) clearInterval(scanTimer)
})

// ── 统计 ──
const forwardedCount = computed(() => ports.value.filter(p => p.isForwarded).length)
const hasPorts = computed(() => ports.value.length > 0)
</script>

<template>
  <div class="ports-panel flex flex-col h-full text-[13px]"
    style="color: var(--color-ide-text); background: var(--color-ide-surface);">

    <!-- ═══ 标题栏 ═══ -->
    <div class="flex items-center shrink-0 justify-between px-3"
      style="height: var(--panel-title-height); border-bottom: 1px solid var(--color-ide-border);">
      <span class="font-semibold text-[11px] uppercase tracking-wider"
        style="color: var(--color-ide-text-dim);">
        端口{{ forwardedCount > 0 ? ` (${forwardedCount} 已转发)` : '' }}
      </span>
      <div class="flex items-center gap-1">
        <button
          class="w-6 h-6 flex items-center justify-center rounded-[3px] transition-colors"
          style="color: var(--color-ide-text-dim);"
          title="添加端口"
          @click="showAddForm = !showAddForm">
          <Plus :size="14" />
        </button>
        <button
          class="w-6 h-6 flex items-center justify-center rounded-[3px] transition-colors"
          style="color: var(--color-ide-text-dim);"
          title="刷新"
          :class="{ 'animate-spin': scanning }"
          @click="scanPorts">
          <RefreshCw :size="14" />
        </button>
      </div>
    </div>

    <!-- ═══ 添加端口表单 ═══ -->
    <div v-if="showAddForm" class="shrink-0 px-3 py-2 space-y-2"
      style="border-bottom: 1px solid var(--color-ide-border);">
      <input
        v-model="newPort"
        type="number"
        placeholder="端口号 (e.g. 8080)"
        min="1" max="65535"
        class="w-full px-2 py-1 text-[12px] rounded-[3px] outline-none"
        style="background: var(--color-ide-bg-secondary); color: var(--color-ide-text); border: 1px solid var(--color-ide-border);"
        @keyup.enter="addPort"
        @keyup.escape="showAddForm = false" />
      <input
        v-model="newLabel"
        placeholder="标签 (可选)"
        class="w-full px-2 py-1 text-[12px] rounded-[3px] outline-none"
        style="background: var(--color-ide-bg-secondary); color: var(--color-ide-text); border: 1px solid var(--color-ide-border);"
        @keyup.enter="addPort"
        @keyup.escape="showAddForm = false" />
      <div class="flex gap-2">
        <button
          class="px-3 py-1 text-[11px] rounded-[3px] font-medium"
          style="background: var(--color-ide-accent); color: #fff;"
          @click="addPort">添加</button>
        <button
          class="px-3 py-1 text-[11px] rounded-[3px]"
          style="background: transparent; color: var(--color-ide-text-dim);"
          @click="showAddForm = false">取消</button>
      </div>
    </div>

    <!-- ═══ 端口列表 ═══ -->
    <div class="flex-1 overflow-y-auto">
      <!-- 空状态 -->
      <div v-if="!hasPorts && !scanning" class="flex flex-col items-center justify-center h-full gap-3 px-6 text-center">
        <Globe :size="32" style="color: var(--color-ide-text-dim); opacity: 0.4;" />
        <div style="color: var(--color-ide-text-dim);">
          <p class="text-[12px] mb-1">未检测到转发端口</p>
          <p class="text-[11px]" style="opacity: 0.7;">
            启动开发服务器 (如 npm run dev) 后会自动显示在此处。<br />
            也可手动添加端口进行转发。
          </p>
        </div>
      </div>

      <!-- 扫描中 -->
      <div v-if="scanning && !hasPorts" class="flex items-center justify-center h-full"
        style="color: var(--color-ide-text-dim);">
        <RefreshCw :size="16" class="animate-spin mr-2" />
        <span class="text-[12px]">正在扫描端口...</span>
      </div>

      <!-- 端口卡片列表 -->
      <div v-if="hasPorts" class="py-1">
        <div
          v-for="entry in ports" :key="entry.id"
          class="port-item flex items-center gap-2 px-3 py-2 mx-1 rounded-[3px] cursor-pointer group transition-colors"
          style="--hover-bg: var(--color-ide-surface-hover);"
          @mouseenter="(e) => { (e.currentTarget as HTMLElement).style.background = 'var(--color-ide-surface-hover)' }"
          @mouseleave="(e) => { (e.currentTarget as HTMLElement).style.background = 'transparent' }">
          <!-- 转发状态指示器 -->
          <div class="w-2 h-2 rounded-full shrink-0"
            :style="{ background: entry.isForwarded ? 'var(--color-ide-success, #4ec9b0)' : 'var(--color-ide-text-dim)', opacity: entry.isForwarded ? 1 : 0.5 }"
            :title="entry.isForwarded ? '已转发' : '未转发'" />

          <!-- 信息区 -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="font-mono text-[13px] font-medium"
                style="color: var(--color-ide-text);">
                :{{ entry.port }}
              </span>
              <span v-if="entry.label" class="text-[11px] truncate"
                style="color: var(--color-ide-text-dim);">
                {{ entry.label }}
              </span>
            </div>
            <div class="flex items-center gap-2 mt-0.5 text-[10px]"
              style="color: var(--color-ide-text-dim); opacity: 0.7;">
              <code class="font-mono">{{ formatAddress(entry) }}</code>
              <span v-if="entry.processName" class="px-1.5 py-px rounded-[2px] text-[9px]"
                style="background: var(--color-ide-bg-secondary);">
                {{ entry.source === "terminal" ? "终端" : entry.source === "debug" ? "调试" : "手动" }}
                {{ entry.processId ? `· PID ${entry.processId}` : "" }}
              </span>
            </div>
          </div>

          <!-- 操作按钮 (hover 显示) -->
          <div class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              class="w-6 h-6 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-active)]"
              title="在浏览器中打开"
              @click.stop="openInBrowser(entry.localAddress)">
              <ExternalLink :size="13" />
            </button>
            <button
              class="w-6 h-6 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-active)]"
              title="复制地址"
              @click.stop="copyAddress(entry.localAddress)">
              <Copy :size="13" />
            </button>
            <button
              v-if="entry.source === 'user'"
              class="w-6 h-6 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-error)] hover:bg-opacity-20 hover:text-[var(--color-ide-error)]"
              title="移除端口"
              @click.stop="removePort(entry.id)">
              <Square :size="12" />
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ 底部信息栏 ═══ -->
    <div v-if="hasPorts" class="shrink-0 flex items-center gap-2 px-3 py-1.5 text-[10px]"
      style="border-top: 1px solid var(--color-ide-border); color: var(--color-ide-text-dim);">
      <Globe :size="10" />
      <span>{{ ports.length }} 个端口</span>
      <span v-if="forwardedCount > 0">· {{ forwardedCount }} 已转发</span>
    </div>
  </div>
</template>
