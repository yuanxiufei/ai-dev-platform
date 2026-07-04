<script setup lang="ts">
/**
 * BottomOutputPanel — VSCode-style 输出面板 (底部面板)
 *
 * 参考 VSCode outputView.ts:
 *   - 多 channel 切换（下拉→子标签栏）
 *   - DOM 渲染 + 自动滚动到底部
 *   - scrollLock 机制（用户手动往上滚时暂停自动滚动）
 *   - 清除输出按钮
 *   - 日志级别颜色高亮（error/warning/debug/trace）
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { Lock, LockOpen, Trash2, Info, AlertTriangle, Bug, Terminal } from 'lucide-vue-next'

const store = useIDEStore()
const scrollRef = ref<HTMLDivElement | null>(null)

// ── 当前激活通道 ──
const activeChannel = computed(() =>
  store.outputChannels.find(c => c.id === store.activeOutputChannel)
)

// ── channel 切换 ──
function setChannel(id: string): void {
  store.activeOutputChannel = id
  nextTick(scrollToBottom)
}

// ── 清除输出 ──
function clearChannel(): void {
  const ch = activeChannel.value
  if (ch) ch.lines = []
}

// ── Scroll Lock（参考 VSCode smartScroll） ──
const scrollLocked = ref(false)
function onScroll(): void {
  const el = scrollRef.value
  if (!el) return
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30
  if (atBottom) {
    scrollLocked.value = false
  } else {
    scrollLocked.value = true
  }
}

function scrollToBottom(): void {
  const el = scrollRef.value
  if (!el) return
  el.scrollTop = el.scrollHeight
}

// ── 自动滚动（内容变化 + scrollLock 未锁定时） ──
watch(
  () => activeChannel.value?.lines?.length,
  () => {
    if (!scrollLocked.value) nextTick(scrollToBottom)
  }
)

// ── channel 切换时滚动到底部 ──
watch(() => store.activeOutputChannel, () => {
  scrollLocked.value = false
  nextTick(scrollToBottom)
})

// ── 日志级别检测（简单前缀正则） ──
const LOG_LEVEL_RE = /^\[(error|err|warn|warning|info|debug|trace|verbose)\]/i
const LEVEL_COLORS: Record<string, string> = {
  error: 'var(--output-color-error)',
  err: 'var(--output-color-error)',
  warn: 'var(--output-color-warning)',
  warning: 'var(--output-color-warning)',
  info: 'var(--output-color-info)',
  debug: 'var(--output-color-debug)',
  trace: 'var(--output-color-trace)',
  verbose: 'var(--output-color-trace)',
}

const LOG_ICONS: Record<string, any> = {
  error: AlertTriangle,
  err: AlertTriangle,
  warn: AlertTriangle,
  warning: AlertTriangle,
  info: Info,
  debug: Bug,
  trace: Terminal,
  verbose: Terminal,
}

function detectLevel(line: string): { level: string | null; displayLine: string } {
  const m = line.match(LOG_LEVEL_RE)
  if (m) {
    return { level: m[1].toLowerCase(), displayLine: line }
  }
  // 检测 ✓ / ✗ 前缀的简单状态行
  if (/^[✓✔]/.test(line.trim())) return { level: 'success', displayLine: line }
  if (/^[✗✘✕]/.test(line.trim())) return { level: 'error', displayLine: line }
  return { level: null, displayLine: line }
}

const CHANNEL_ICONS: Record<string, any> = {
  output: Terminal,
  problems: AlertTriangle,
  'debug-console': Bug,
}
</script>

<template>
  <div
    class="output-panel h-full flex flex-col text-[12px]"
    style="background: var(--color-ide-bg); color: var(--color-ide-text);"
  >
    <!-- ═══ Channel 子标签栏（VSCode 下拉菜单 → 我们的平铺标签） ═══ -->
    <div
      class="flex items-center h-[28px] px-2 gap-0.5 shrink-0"
      style="background: var(--color-ide-bg-secondary); border-bottom: 1px solid var(--color-ide-border);"
    >
      <button
        v-for="ch in store.outputChannels"
        :key="ch.id"
        class="flex items-center gap-1 px-3 py-1 text-[11px] rounded-sm transition-colors"
        :class="ch.id === store.activeOutputChannel
          ? 'text-[var(--color-ide-text)]'
          : 'text-[var(--color-ide-text-dim)] opacity-60 hover:opacity-100'"
        :style="ch.id === store.activeOutputChannel
          ? { background: 'var(--color-ide-surface)', fontWeight: 500 }
          : { background: 'transparent' }"
        @click="setChannel(ch.id)"
      >
        <component :is="CHANNEL_ICONS[ch.id] ?? Terminal" :size="11" />
        {{ ch.name }}
      </button>

      <div class="flex-1" />

      <!-- 自动滚动锁定指示 -->
      <button
        class="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
        :class="scrollLocked ? 'text-[var(--color-ide-warning)]' : 'text-[var(--color-ide-text-dim)]'"
        :title="scrollLocked ? '自动滚动已锁定（点击解锁）' : '自动滚动中'"
        @click="scrollLocked = !scrollLocked; if (!scrollLocked) scrollToBottom()"
      >
        <component :is="scrollLocked ? Lock : LockOpen" :size="10" />
      </button>

      <!-- 清除按钮 -->
      <button
        class="flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
        title="清除输出"
        @click="clearChannel()"
      >
        <Trash2 :size="10" />
      </button>
    </div>

    <!-- ═══ 输出内容区（DOM 渲染 + 自动滚动） ═══ -->
    <div
      ref="scrollRef"
      class="flex-1 overflow-y-auto font-mono text-[11px] leading-[18px]"
      @scroll="onScroll"
    >
      <template v-if="activeChannel && activeChannel.lines.length > 0">
        <div
          v-for="(line, i) in activeChannel.lines"
          :key="i"
          class="whitespace-pre-wrap break-all px-2 hover:bg-[var(--color-ide-surface-hover)]/30 min-h-[18px]"
          :class="detectLevel(line).level ? '' : 'text-[var(--color-ide-text-dim)]'"
        >
          <template v-if="detectLevel(line).level">
            <span class="inline-flex items-center gap-0.5 mr-1" :style="{ color: LEVEL_COLORS[detectLevel(line).level!] ?? 'inherit' }">
              <component :is="LOG_ICONS[detectLevel(line).level!]" :size="10" v-if="LOG_ICONS[detectLevel(line).level!]" />
              {{ line }}
            </span>
          </template>
          <template v-else>
            {{ line }}
          </template>
        </div>
      </template>
      <div
        v-else
        class="flex flex-col items-center justify-center h-full text-[var(--color-ide-text-dim)] opacity-40 select-none gap-1"
      >
        <component :is="CHANNEL_ICONS[store.activeOutputChannel] ?? Terminal" :size="20" />
        <span class="text-[11px]">暂无输出内容</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══ 输出面板日志级别颜色（组件级 CSS 变量） ═══ */
.output-panel {
  --output-color-error: #ef4444;
  --output-color-warning: #f59e0b;
  --output-color-info: #3b82f6;
  --output-color-debug: #8b5cf6;
  --output-color-trace: #6b7280;
}
</style>
