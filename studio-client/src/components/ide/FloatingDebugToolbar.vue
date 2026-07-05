<script setup lang="ts">
/**
 * FloatingDebugToolbar.vue — VSCode 浮动调试控制栏
 *
 * Session 36: 调试运行时在 EditorArea 顶部显示浮动控制栏，
 * 借鉴 VSCode src/vs/workbench/contrib/debug/browser/debugToolBar.ts
 *
 * 包含: 继续/暂停、单步跳过/进入/跳出、重启、停止、断开
 */

import { useDebugStore } from "@/stores/useDebugStore"
import {
  Play, Pause, SkipForward, ArrowDownToLine,
  ArrowUpFromLine, RotateCcw, Square,
} from "lucide-vue-next"

const debug = useDebugStore()

// ── 样式常量 ──
const BG = "var(--color-ide-bg-secondary)"
const BORDER = "var(--color-ide-border)"
const TEXT = "var(--color-ide-text)"
const TEXT_DIM = "var(--color-ide-text-dim)"
const ACCENT = "var(--color-ide-accent)"
const GREEN = "var(--color-terminal-green)"
const YELLOW = "var(--color-terminal-yellow)"
const ERROR = "var(--color-ide-error)"
const SURFACE_HOVER = "var(--color-ide-surface-hover)"

/** 获取按钮样式（复用 DebugPanel 相同逻辑） */
function btnStyle(color?: string): Record<string, string> {
  const base: Record<string, string> = {
    width: "32px",
    height: "32px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: "5px",
    border: "none",
    cursor: "pointer",
    color: TEXT_DIM,
    background: "transparent",
    transition: "background 0.15s, color 0.15s, opacity 0.15s",
  }
  if (color) {
    base.color = color
  }
  return base
}
</script>

<template>
  <!-- VSCode debugToolBar: 浮动在编辑区顶部的调试控制栏 -->
  <div
    v-if="debug.isRunning"
    class="floating-debug-toolbar flex items-center shrink-0 gap-1 px-2 select-none"
    :style="{
      position: 'absolute',
      top: '0',
      left: '50%',
      transform: 'translateX(-50%)',
      zIndex: '45',
      height: '38px',
      background: BG,
      border: `1px solid ${BORDER}`,
      borderTop: 'none',
      borderRadius: '0 0 6px 6px',
      boxShadow: '0 2px 8px rgba(0,0,0,0.25)',
    }"
  >
    <!-- 继续 / 暂停 -->
    <button
      v-if="debug.isPaused"
      class="debug-float-btn"
      :style="{ ...btnStyle(ACCENT), color: ACCENT }"
      title="继续 (F5)"
      @click="debug.resumeDebug()"
    >
      <Play :size="15" />
    </button>
    <button
      v-else
      class="debug-float-btn"
      :style="{ ...btnStyle(YELLOW), color: YELLOW }"
      title="暂停 (F6)"
      @click="debug.pauseDebug()"
    >
      <Pause :size="15" />
    </button>

    <!-- 分隔线 -->
    <div :style="{ width: '1px', height: '20px', background: BORDER, margin: '0 4px' }" />

    <!-- 单步跳过 -->
    <button
      class="debug-float-btn"
      :style="btnStyle()"
      title="单步跳过 (F10)"
      :disabled="!debug.isPaused"
      @click="debug.stepOver()"
    >
      <SkipForward :size="15" />
    </button>

    <!-- 单步进入 -->
    <button
      class="debug-float-btn"
      :style="btnStyle()"
      title="单步进入 (F11)"
      :disabled="!debug.isPaused"
      @click="debug.stepInto()"
    >
      <ArrowDownToLine :size="15" />
    </button>

    <!-- 单步跳出 -->
    <button
      class="debug-float-btn"
      :style="btnStyle()"
      title="单步跳出 (Shift+F11)"
      :disabled="!debug.isPaused"
      @click="debug.stepOut()"
    >
      <ArrowUpFromLine :size="15" />
    </button>

    <!-- 分隔线 -->
    <div :style="{ width: '1px', height: '20px', background: BORDER, margin: '0 4px' }" />

    <!-- 重新启动 -->
    <button
      class="debug-float-btn"
      :style="btnStyle()"
      title="重新启动 (Ctrl+Shift+F5)"
      @click="debug.restartDebug()"
    >
      <RotateCcw :size="14" />
    </button>

    <!-- 停止 -->
    <button
      class="debug-float-btn"
      :style="{ ...btnStyle(), color: ERROR }"
      title="停止 (Shift+F5)"
      @click="debug.stopDebug()"
    >
      <Square :size="12" />
    </button>

    <!-- 当前状态文字 -->
    <span
      class="text-[11px] font-medium whitespace-nowrap ml-1"
      :style="{ color: debug.isPaused ? YELLOW : GREEN }"
    >
      {{ debug.isPaused ? '⏸ 已暂停' : '▶ 运行中' }}
    </span>
  </div>
</template>

<style scoped>
.floating-debug-toolbar {
  pointer-events: auto;
}

.debug-float-btn:hover:not(:disabled) {
  background: var(--color-ide-surface-hover) !important;
  color: var(--color-ide-text) !important;
}

.debug-float-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.debug-float-btn:active:not(:disabled) {
  transform: scale(0.93);
}
</style>
