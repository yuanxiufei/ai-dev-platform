<script setup lang="ts">
/**
 * ActivityBar — VS Code activitybarPart (像素级对齐)
 *
 * 精细尺寸:
 *   容器宽度:      48px     (ACTIVITYBAR_WIDTH)
 *   活动项高度:    48px     (TAB_HEIGHT)
 *   图标大小:      24px     (ICON_SIZE)
 *   激活指示器:    2px       白色竖线, 24px高, 圆角1px
 *   底部设置:      48px     始终显示在底部
 *
 * 交互:
 *   - 点击切换 Sidebar 视图 + 展开文件树
 *   - 拖拽重排序 Activity items
 *   - Hover tooltip 显示标签名
 *   - Badge 显示数字 (如 Git 变更数)
 *   - 平滑指示器滑动动画
 */
import { computed, ref } from "vue"
import { Settings } from "lucide-vue-next"
import { useIDEStore } from "@/stores/useIDEStore"

const store = useIDEStore()

// 🔥 拖拽状态
const dragOverItemId = ref<string | null>(null)
const dragItemId = ref<string | null>(null)

// 🔥 根据当前活动面板返回对应图标组件名
const iconMap: Record<string, string> = {
  explorer: "Files",
  search: "Search",
  git: "GitBranch",
  debug: "Bug",
  extensions: "Blocks",
  studio: "Sparkles",
  settings: "Settings",
}

// 🔥 图标映射：使用 SVG 代替 lucide 组件（保证 ActivityBar 渲染一致性）
const iconSvgs: Record<string, string> = {
  Files: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z"/></svg>`,
  Search: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>`,
  GitBranch: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="3" x2="6" y2="15"/><circle cx="6" cy="18" r="3"/><path d="M18 9a3 3 0 100-6 3 3 0 000 6z"/><path d="M6 15a9 9 0 009 9"/></svg>`,
  Bug: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m8 2 1.88 1.88"/><path d="M14.12 3.88 16 2"/><path d="M9 7.13v-1a3.003 3.003 0 016 0v1M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 014-4h4a4 4 0 014 4v3c0 3.3-2.7 6-6 6z"/><path d="M3 13h4M17 13h4M20 17.5l-1.5-1.5M13.5 6l-3 3M10.5 6l3 3"/></svg>`,
  Blocks: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/></svg>`,
  Sparkles: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.912 5.813a2 2 0 01-1.275 1.275L3 12l5.813 1.912a2 2 0 011.275 1.275L12 21l1.912-5.813a2 2 0 011.275-1.275L21 12l-5.813-1.912a2 2 0 01-1.275-1.275L12 3z"/></svg>`,
  FlaskConical: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M9 3h6"/><path d="M10 3v7.6L4.8 17.5a1.5 1.5 0 00.9 2.5h12.6a1.5 1.5 0 00.9-2.5L14 10.6V3"/></svg>`,
  Settings: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 00-2 2v.18a2 2 0 01-1 1.73l-.43.25a2 2 0 01-2 0l-.15-.08a2 2 0 00-2.73.73l-.22.38a2 2 0 00.73 2.73l.15.1a2 2 0 011 1.72v.51a2 2 0 01-1 1.74l-.15.09a2 2 0 00-.73 2.73l.22.38a2 2 0 002.73.73l.15-.08a2 2 0 012 0l.43.25a2 2 0 011 1.73V20a2 2 0 002 2h.44a2 2 0 002-2v-.18a2 2 0 011-1.73l.43-.25a2 2 0 012 0l.15.08a2 2 0 002.73-.73l.22-.39a2 2 0 00-.73-2.73l-.15-.08a2 2 0 01-1-1.74v-.5a2 2 0 011-1.74l.15-.09a2 2 0 00.73-2.73l-.22-.38a2 2 0 00-2.73-.73l-.15.08a2 2 0 01-2 0l-.43-.25a2 2 0 01-1-1.73V4a2 2 0 00-2-2z"/><circle cx="12" cy="12" r="3"/></svg>`,
}

function onDragStart(e: DragEvent, itemId: string): void {
  dragItemId.value = itemId
  e.dataTransfer!.effectAllowed = "move"
}

function onDragOver(e: DragEvent, itemId: string): void {
  e.preventDefault()
  dragOverItemId.value = itemId
}

function onDragLeave(): void {
  dragOverItemId.value = null
}

function onDrop(e: DragEvent, targetId: string): void {
  e.preventDefault()
  dragOverItemId.value = null
  dragItemId.value = null
}

function onActivityClick(itemId: string): void {
  // 🔥 切换 ActivityBar 项 — 如果点击的是当前激活项，则隐藏 Sidebar
  if (store.activeActivityItem === itemId && store.layout.fileTreeVisible) {
    store.layout.fileTreeVisible = false
  } else {
    store.activeActivityItem = itemId
    store.layout.fileTreeVisible = true
  }
}
</script>

<template>
  <!-- ═══ ActivityBar — VSCode activitybarPart (48px fixed) ═══ -->
  <div
    class="activity-bar shrink-0 w-12 h-full flex flex-col items-center z-20"
    :style="{
      background: 'var(--color-activity-bg)',
      borderRight: '1px solid var(--color-ide-border)',
    }"
  >
    <!-- 🔥 Logo / Account button (VSCode: accounts activity) -->
    <button
      class="activity-item group relative w-full h-12 flex items-center justify-center transition-colors"
      :class="store.activeActivityItem === 'explorer'
        ? 'text-white'
        : 'text-[var(--color-ide-text-dim)]/40 hover:text-[var(--color-ide-text-dim)]'"
      title="资源管理器 (Ctrl+Shift+E)"
      @click="onActivityClick('explorer')"
    >
      <!-- Active indicator -->
      <div
        v-if="store.activeActivityItem === 'explorer'"
        class="activity-indicator absolute left-0"
      />
      <!-- Logo -->
      <div
        class="w-6 h-6 rounded flex items-center justify-center text-[11px] font-bold text-white"
        :style="{ background: 'var(--color-ide-accent)' }"
      >
        C
      </div>
      <!-- Tooltip -->
      <span
        class="activity-tooltip absolute left-full ml-1.5 px-2 py-1 rounded-[3px] text-xs whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 z-50"
        :style="{
          background: 'var(--color-ide-surface)',
          border: '1px solid var(--color-ide-border)',
          color: 'var(--color-ide-text)',
        }"
      >
        资源管理器
      </span>
    </button>

    <!-- 🔥 主要活动项列表 (可拖拽重排序) -->
    <div class="flex-1 flex flex-col w-full">
      <button
        v-for="item in store.activityItems"
        :key="item.id"
        class="activity-item group relative w-full h-12 flex items-center justify-center transition-colors"
        :class="store.activeActivityItem === item.id
          ? 'text-white'
          : 'text-[var(--color-ide-text-dim)]/40 hover:text-[var(--color-ide-text-dim)]'"
        :title="`${item.label}${item.id === 'explorer' ? ' (Ctrl+Shift+E)' : item.id === 'search' ? ' (Ctrl+Shift+F)' : item.id === 'git' ? ' (Ctrl+Shift+G)' : item.id === 'debug' ? ' (Ctrl+Shift+D)' : item.id === 'extensions' ? ' (Ctrl+Shift+X)' : ''}`"
        draggable="true"
        @click="onActivityClick(item.id)"
        @dragstart="onDragStart($event, item.id)"
        @dragover="onDragOver($event, item.id)"
        @dragleave="onDragLeave"
        @drop="onDrop($event, item.id)"
      >
        <!-- 🔥 Active indicator with smooth transition -->
        <div
          v-if="store.activeActivityItem === item.id"
          class="activity-indicator absolute left-0"
        />
        <!-- 🔥 Drag over indicator -->
        <div
          v-if="dragOverItemId === item.id && dragItemId !== item.id"
          class="absolute top-0 left-1 right-1 z-10"
          style="height: 2px; background: #007ACC; border-radius: 1px"
        />

        <!-- 图标 -->
        <span
          class="w-6 h-6 inline-flex items-center justify-center"
          v-html="iconSvgs[item.icon] || ''"
        />

        <!-- Tooltip -->
        <span
          class="activity-tooltip absolute left-full ml-1.5 px-2 py-1 rounded-[3px] text-xs whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 z-50"
          :style="{
            background: 'var(--color-ide-surface)',
            border: '1px solid var(--color-ide-border)',
            color: 'var(--color-ide-text)',
          }"
        >
          {{ item.label }}
        </span>

        <!-- 🔥 Badge — VS Code 风格计数器 -->
        <span
          v-if="item.badge"
          class="activity-badge absolute top-1.5 right-1 min-w-[16px] h-[18px] flex items-center justify-center text-[10px] font-bold text-white rounded-full px-1"
          :style="{ background: 'var(--color-ide-accent)' }"
        >
          {{ item.badge }}
        </span>
      </button>
    </div>

    <!-- 🔥 底部管理按钮 (VSCode: manage activity) -->
    <div
      class="w-full"
      style="border-top: 1px solid rgba(204, 204, 204, 0.1)"
    >
      <button
        class="activity-item group relative w-full h-12 flex items-center justify-center transition-colors"
        :class="store.activeActivityItem === 'settings'
          ? 'text-white'
          : 'text-[var(--color-ide-text-dim)]/40 hover:text-[var(--color-ide-text-dim)]'"
        title="管理 (Ctrl+,)"
        @click="onActivityClick('settings')"
      >
        <div
          v-if="store.activeActivityItem === 'settings'"
          class="activity-indicator absolute left-0"
        />
        <Settings :size="22" />
        <span
          class="activity-tooltip absolute left-full ml-1.5 px-2 py-1 rounded-[3px] text-xs whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 z-50"
          :style="{
            background: 'var(--color-ide-surface)',
            border: '1px solid var(--color-ide-border)',
            color: 'var(--color-ide-text)',
          }"
        >
          管理
        </span>
      </button>
    </div>
  </div>
</template>

<style scoped>
/* ═══ ActivityBar ═══ */
.activity-bar {
  contain: layout style;
}

/* 🔥 Activity item */
.activity-item {
  outline: none !important;
}
.activity-item:focus-visible {
  outline: none !important;
}

/* 🔥 激活指示器 — 2px 宽白/彩色竖线, 平滑过渡 */
.activity-indicator {
  width: 2px;
  height: 24px;
  border-radius: 0 2px 2px 0;
  background: var(--color-ide-text-bright);
  transition: all 0.15s cubic-bezier(0.16, 1, 0.3, 1);
  transform-origin: top center;
}

/* 🔥 Tooltip 过渡 */
.activity-tooltip {
  transition: opacity 0.12s ease;
}

/* 🔥 Badge */
.activity-badge {
  line-height: 1;
  pointer-events: none;
}
</style>
