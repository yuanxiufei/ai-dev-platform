<script setup lang="ts">
/**
 * Code Actions Menu — VSCode 风格灯泡菜单（快速修复/重构/源代码操作）
 *
 * Session 37: VSCode 功能对齐
 * 借鉴 VSCode codeActionWidget.ts + lightBulbWidget.ts
 * 当光标在有问题/可优化的代码行时显示灯泡，点击展示可用操作列表。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Lightbulb, Wrench, Sparkles, ArrowRight, X } from 'lucide-vue-next'

// ── 类型定义 ──

export interface CodeAction {
  id: string
  /** 操作标题 */
  title: string
  /** VSCode 风格分组: "quickfix" | "refactor" | "source" */
  kind: 'quickfix' | 'refactor' | 'source' | 'other'
  /** 是否已禁用 */
  disabled?: boolean
  /** 是否为优先操作（快捷键 Ctrl+. 可直接触发） */
  isPreferred?: boolean
}

const props = defineProps<{
  visible: boolean
  /** 弹出位置 (相对于视口的像素) */
  x: number
  y: number
  /** 可用操作列表 */
  actions: CodeAction[]
  /** 灯泡所在行的问题描述（显示在菜单标题） */
  diagnosticMessage?: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'action', action: CodeAction): void
  (e: 'apply-all', actions: CodeAction[]): void
}>()

// ── 键盘导航 ──
const focusedIndex = ref(0)
const menuRef = ref<HTMLElement | null>(null)

/** 重置选中索引 */
watch(() => props.visible, (v) => {
  if (v) {
    focusedIndex.value = 0
    nextTick(() => menuRef.value?.focus())
  }
})

/** 键盘处理 */
function onKeydown(e: KeyboardEvent) {
  const len = props.actions.length
  if (len === 0) return

  if (e.key === 'ArrowDown') {
    e.preventDefault()
    focusedIndex.value = (focusedIndex.value + 1) % len
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    focusedIndex.value = (focusedIndex.value - 1 + len) % len
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const a = props.actions[focusedIndex.value]
    if (a && !a.disabled) emit('action', a)
  } else if (e.key === 'Escape') {
    e.preventDefault()
    emit('close')
  }
}

/** 滚动选中项到可视区 */
watch(focusedIndex, () => {
  nextTick(() => {
    const items = menuRef.value?.querySelectorAll('.action-item')
    items?.[focusedIndex.value]?.scrollIntoView({ block: 'nearest' })
  })
})

// ── 分组计算 ──

interface ActionGroup {
  kind: string
  label: string
  icon: typeof Lightbulb
  actions: CodeAction[]
}

const groups = computed<ActionGroup[]>(() => {
  const map = new Map<string, CodeAction[]>()
  for (const a of props.actions) {
    const k = a.kind
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(a)
  }
  const icons: Record<string, typeof Lightbulb> = {
    quickfix: Lightbulb,
    refactor: Wrench,
    source: Sparkles,
    other: ArrowRight,
  }
  const labels: Record<string, string> = {
    quickfix: '快速修复',
    refactor: '重构',
    source: '源代码操作',
    other: '其他',
  }
  return Array.from(map.entries()).map(([kind, actions]) => ({
    kind,
    label: labels[kind] ?? kind,
    icon: icons[kind] ?? ArrowRight,
    actions,
  }))
})

// ── 关闭处理 ──

function onClose(e?: MouseEvent) {
  // 不拦截菜单内元素点击
  if (e && menuRef.value?.contains(e.target as Node)) return
  emit('close')
}

/** 全局点击外部关闭 */
function onClickOutside(e: MouseEvent) {
  if (!props.visible) return
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) {
    emit('close')
  }
}

onMounted(() => document.addEventListener('mousedown', onClickOutside))
onBeforeUnmount(() => document.removeEventListener('mousedown', onClickOutside))

// ── 位置微调：保持在视口内 ──
const adjustedStyle = computed(() => {
  const mx = Math.min(props.x, window.innerWidth - 300)
  const my = Math.min(props.y, window.innerHeight - 400)
  return {
    left: `${Math.max(0, mx)}px`,
    top: `${Math.max(0, my)}px`,
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="code-action-fade">
      <div
        v-if="visible && actions.length > 0"
        ref="menuRef"
        class="code-actions-menu"
        :style="adjustedStyle"
        tabindex="-1"
        role="menu"
        aria-label="代码操作"
        @keydown="onKeydown"
      >
        <!-- 标题栏：问题描述 + 关闭按钮 -->
        <div v-if="diagnosticMessage" class="menu-header">
          <Lightbulb :size="15" class="bulb-icon" />
          <span class="header-msg">{{ diagnosticMessage.slice(0, 60) }}</span>
          <button class="close-btn" @click="onClose" title="关闭 (Esc)">
            <X :size="13" />
          </button>
        </div>

        <!-- 分组操作列表 -->
        <div v-for="group in groups" :key="group.kind" class="action-group">
          <div class="group-label">
            <component :is="group.icon" :size="11" />
            <span>{{ group.label }}</span>
          </div>
          <div
            v-for="(action, i) in group.actions"
            :key="action.id"
            class="action-item"
            :class="{
              focused: focusedIndex === actions.indexOf(action),
              disabled: action.disabled,
              preferred: action.isPreferred,
            }"
            role="menuitem"
            @click="action.disabled ? undefined : emit('action', action)"
            @mouseenter="focusedIndex = actions.indexOf(action)"
          >
            <div class="action-bullet">
              <!-- 优先操作显示星标 -->
              <Sparkles v-if="action.isPreferred" :size="12" class="preferred-icon" />
            </div>
            <span class="action-title">{{ action.title }}</span>
            <span v-if="action.isPreferred" class="action-hint">Ctrl+.</span>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-if="actions.length === 0" class="empty-state">
          <span>没有可用的代码操作</span>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* ═══ 菜单容器 ═══ */
.code-actions-menu {
  position: fixed;
  z-index: 200;
  width: 280px;
  max-height: 400px;
  overflow-y: auto;
  background: var(--color-ide-bg, #1e1e1e);
  border: 1px solid var(--color-ide-border, #3c3c3c);
  border-radius: 8px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45), 0 2px 8px rgba(0, 0, 0, 0.25);
  outline: none;
  font-size: 12px;
  color: var(--color-ide-text, #cccccc);
}

/* ── 菜单标题栏 ── */
.menu-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--color-ide-border, #3c3c3c);
  background: rgba(255, 255, 255, 0.02);
}
.bulb-icon {
  color: #ffcc00;
  flex-shrink: 0;
}
.header-msg {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--color-ide-text-dim, #858585);
  font-size: 11.5px;
}
.close-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--color-ide-text-dim, #858585);
  cursor: pointer;
  flex-shrink: 0;
}
.close-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--color-ide-text, #cccccc);
}

/* ── 操作分组 ── */
.action-group {
  padding: 4px 0;
}
.action-group + .action-group {
  border-top: 1px solid rgba(255, 255, 255, 0.04);
}
.group-label {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px 2px;
  font-size: 10.5px;
  font-weight: 600;
  color: var(--color-ide-text-dim, #858585);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* ── 操作项 ── */
.action-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  cursor: pointer;
  transition: background 0.1s;
  border-radius: 3px;
  margin: 0 4px;
}
.action-item:hover,
.action-item.focused {
  background: rgba(0, 122, 204, 0.12);
}
.action-item.disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.action-item.disabled:hover {
  background: transparent;
}

.action-bullet {
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.preferred-icon {
  color: #ffcc00;
}

.action-title {
  flex: 1;
  line-height: 1.4;
}
.action-hint {
  font-size: 10px;
  color: var(--color-ide-text-dim, #858585);
  padding: 0 4px;
  background: rgba(255, 255, 255, 0.05);
  border-radius: 3px;
}

/* ── 空状态 ── */
.empty-state {
  padding: 16px;
  text-align: center;
  color: var(--color-ide-text-dim, #858585);
}

/* ── 入场/离场动画 ── */
.code-action-fade-enter-active {
  transition: opacity 0.12s ease, transform 0.12s cubic-bezier(0.16, 1, 0.3, 1);
}
.code-action-fade-leave-active {
  transition: opacity 0.08s ease, transform 0.08s ease;
}
.code-action-fade-enter-from {
  opacity: 0;
  transform: translateY(-4px) scale(0.96);
}
.code-action-fade-leave-to {
  opacity: 0;
  transform: translateY(-2px) scale(0.98);
}
</style>
