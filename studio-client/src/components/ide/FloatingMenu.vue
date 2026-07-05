<script setup lang="ts">
/**
 * FloatingMenu.vue — 通用浮动菜单/工具栏
 *
 * 对标 VSCode editor/contrib/floatingMenu/ + 上下文菜单弹出层
 * 支持: 命令列表、分组、快捷键提示、禁用态、危险操作标记
 * Session 55: 从 FloatingDebugToolbar 泛化为通用浮动菜单组件
 */
import { ref, computed, watch, onMounted, onUnmounted } from "vue"
import {
  Lightbulb, Wand2, Search, Copy, Scissors, ClipboardPaste,
  Undo2, Redo2, MessageSquareText, Bug, Link2, Trash2,
  type LucideIcon,
} from "lucide-vue-next"

// ── Token 常量 ──
const BG = "var(--color-ide-bg-secondary)"
const BORDER = "var(--color-ide-border)"
const TEXT = "var(--color-ide-text)"
const TEXT_DIM = "var(--color-ide-text-dim)"
const ACCENT = "var(--color-ide-accent)"
const ERROR = "var(--color-ide-error)"
const SURFACE_HOVER = "var(--color-ide-surface-hover)"
const SHADOW = "0 4px 16px rgba(0,0,0,0.25)"

// ── Types ──

export interface FloatingMenuAction {
  id: string
  label: string
  icon?: string
  shortcut?: string
  disabled?: boolean
  dangerous?: boolean
  active?: boolean
  separator?: boolean  // 分组分隔线
  group?: string       // 分组标题
  action: () => void
}

export interface FloatingMenuProps {
  visible: boolean
  x: number
  y: number
  actions: FloatingMenuAction[]
  /** 菜单对齐: top-left | top-right | bottom-left | bottom-right | auto */
  align?: "top-left" | "top-right" | "bottom-left" | "bottom-right" | "auto"
  /** 最大高度（超出滚动） */
  maxHeight?: number
  /** 最小宽度 */
  minWidth?: number
}

const props = withDefaults(defineProps<FloatingMenuProps>(), {
  align: "auto",
  maxHeight: 400,
  minWidth: 200,
})

const emit = defineEmits<{
  close: []
  action: [id: string]
}>()

// ── 状态 ──

const menuRef = ref<HTMLElement | null>(null)
const activeIndex = ref(-1)

// ── 分组后的操作列表 ──

interface ActionGroup {
  label?: string
  items: FloatingMenuAction[]
}

const groups = computed<ActionGroup[]>(() => {
  const result: ActionGroup[] = []
  let current: ActionGroup = { items: [] }

  for (const a of props.actions) {
    if (a.separator) {
      if (current.items.length > 0) result.push(current)
      current = { items: [] }
    } else if (a.group) {
      if (current.items.length > 0) result.push(current)
      current = { label: a.group, items: [] }
    } else {
      current.items.push(a)
    }
  }
  if (current.items.length > 0) result.push(current)
  return result
})

// ── 定位 ──

const menuStyle = computed(() => {
  const style: Record<string, string> = {
    position: "fixed",
    zIndex: "9999",
    background: BG,
    border: `1px solid ${BORDER}`,
    borderRadius: "8px",
    boxShadow: SHADOW,
    padding: "4px",
    minWidth: `${props.minWidth}px`,
    maxHeight: `${props.maxHeight}px`,
    overflowY: "auto",
  }

  const vh = window.innerHeight
  const vw = window.innerWidth
  const menuH = Math.min(props.maxHeight, props.actions.length * 36 + 20)

  let left = props.x
  let top = props.y

  if (props.align === "auto") {
    // 自动选择最佳方向
    const fitsRight = vw - props.x > 220
    const fitsDown = vh - props.y > menuH + 20

    if (fitsRight) {
      style.left = `${left}px`
    } else {
      style.left = `${Math.max(0, left - (props.minWidth ?? 200))}px`
    }

    if (fitsDown) {
      style.top = `${top}px`
    } else {
      style.top = `${Math.max(0, top - menuH)}px`
      style.transformOrigin = "bottom left"
    }
  } else {
    if (props.align.includes("left")) style.left = `${left}px`
    else style.right = `${vw - left}px`

    if (props.align.includes("top")) style.top = `${top}px`
    else style.bottom = `${vh - top}px`
  }

  return style
})

// ── 图标映射 ──

const iconMap: Record<string, LucideIcon> = {
  lightbulb: Lightbulb,
  wand: Wand2,
  search: Search,
  copy: Copy,
  cut: Scissors,
  paste: ClipboardPaste,
  undo: Undo2,
  redo: Redo2,
  comment: MessageSquareText,
  debug: Bug,
  link: Link2,
  delete: Trash2,
}

function getIcon(name?: string): LucideIcon | null {
  if (!name) return null
  return iconMap[name] ?? null
}

// ── 键盘导航 ──

const flatActions = computed(() =>
  groups.value.flatMap(g => g.items)
)

function navigateUp() {
  if (activeIndex.value <= 0) {
    activeIndex.value = flatActions.value.length - 1
  } else {
    activeIndex.value--
  }
  scrollToActive()
}

function navigateDown() {
  if (activeIndex.value >= flatActions.value.length - 1) {
    activeIndex.value = 0
  } else {
    activeIndex.value++
  }
  scrollToActive()
}

function executeActive() {
  const item = flatActions.value[activeIndex.value]
  if (item && !item.disabled) {
    item.action()
    emit("action", item.id)
    emit("close")
  }
}

function scrollToActive() {
  requestAnimationFrame(() => {
    const el = menuRef.value?.querySelector('[data-active="true"]')
    el?.scrollIntoView({ block: "nearest" })
  })
}

function onKeydown(e: KeyboardEvent) {
  switch (e.key) {
    case "ArrowUp":
      e.preventDefault()
      navigateUp()
      break
    case "ArrowDown":
    case "Tab":
      e.preventDefault()
      navigateDown()
      break
    case "Enter":
      e.preventDefault()
      executeActive()
      break
    case "Escape":
      e.preventDefault()
      emit("close")
      break
  }
}

// ── 点击外部关闭 ──

function onOutsideClick(e: MouseEvent) {
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) {
    emit("close")
  }
}

// ── 生命周期 ──

watch(() => props.visible, (v) => {
  if (v) {
    activeIndex.value = -1
    requestAnimationFrame(() => {
      document.addEventListener("click", onOutsideClick, true)
      document.addEventListener("keydown", onKeydown)
    })
  } else {
    document.removeEventListener("click", onOutsideClick, true)
    document.removeEventListener("keydown", onKeydown)
  }
})

onUnmounted(() => {
  document.removeEventListener("click", onOutsideClick, true)
  document.removeEventListener("keydown", onKeydown)
})

// ── 暴露方法 ──

defineExpose({ navigateUp, navigateDown, executeActive })
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      ref="menuRef"
      class="floating-menu"
      :style="menuStyle"
      role="menu"
      aria-label="浮动菜单"
    >
      <template v-for="(group, gi) in groups" :key="gi">
        <div
          v-if="group.label"
          class="floating-menu-group-label"
          :style="{
            padding: '4px 12px 2px',
            fontSize: '11px',
            fontWeight: 600,
            color: TEXT_DIM,
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
          }"
        >
          {{ group.label }}
        </div>
        <button
          v-for="action in group.items"
          :key="action.id"
          :data-active="flatActions.indexOf(action) === activeIndex"
          class="floating-menu-item"
          role="menuitem"
          :disabled="action.disabled"
          :style="{
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            width: '100%',
            padding: '6px 10px',
            border: 'none',
            borderRadius: '4px',
            background: flatActions.indexOf(action) === activeIndex ? SURFACE_HOVER : 'transparent',
            color: action.dangerous ? ERROR : action.disabled ? TEXT_DIM : TEXT,
            cursor: action.disabled ? 'not-allowed' : 'pointer',
            opacity: action.disabled ? 0.5 : 1,
            fontSize: '13px',
            textAlign: 'left',
            transition: 'background 0.1s',
          }"
          @click="action.disabled ? undefined : action.action(); emit('action', action.id); emit('close')"
          @mouseenter="activeIndex = flatActions.indexOf(action)"
        >
          <!-- 图标 -->
          <component
            :is="getIcon(action.icon)"
            v-if="action.icon && getIcon(action.icon)"
            :size="16"
            :style="{ flexShrink: '0' }"
          />
          <span v-else :style="{ width: '16px', flexShrink: '0' }" />

          <!-- 标签 -->
          <span style="flex: 1;">{{ action.label }}</span>

          <!-- 快捷键 -->
          <span
            v-if="action.shortcut"
            :style="{
              fontSize: '11px',
              color: TEXT_DIM,
              marginLeft: '16px',
              fontFamily: 'var(--font-mono)',
            }"
          >
            {{ action.shortcut }}
          </span>

          <!-- 勾选标记 (active) -->
          <span
            v-if="action.active"
            :style="{ color: ACCENT, fontSize: '12px', marginLeft: action.shortcut ? '0' : 'auto' }"
          >✓</span>
        </button>

        <!-- 分组的间隔线 -->
        <div
          v-if="gi < groups.length - 1"
          :style="{
            height: '1px',
            margin: '3px 8px',
            background: BORDER,
          }"
        />
      </template>
    </div>
  </Teleport>
</template>

<style scoped>
.floating-menu {
  user-select: none;
  -webkit-user-select: none;
}

.floating-menu-item:hover:not(:disabled) {
  background: v-bind(SURFACE_HOVER) !important;
}

.floating-menu::-webkit-scrollbar {
  width: 6px;
}
.floating-menu::-webkit-scrollbar-thumb {
  background: var(--color-ide-scrollbar-thumb, #555);
  border-radius: 3px;
}
.floating-menu::-webkit-scrollbar-track {
  background: transparent;
}
</style>
