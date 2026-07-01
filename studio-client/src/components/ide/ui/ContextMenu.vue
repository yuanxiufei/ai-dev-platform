<script setup lang="ts">
/**
 * Unified Context Menu — VSCode-style right-click menu
 * Reusable across TabBar, FileTree, StatusBar, Editor, etc.
 *
 * Usage:
 *   <ContextMenu :items="menuItems" :x="x" :y="y" @close="show=false" />
 */
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue'

export interface ContextMenuItem {
  id: string
  label: string
  shortcut?: string
  icon?: string
  disabled?: boolean
  danger?: boolean
  separator?: boolean
  children?: ContextMenuItem[]
  action?: () => void
}

const props = defineProps<{
  items: ContextMenuItem[]
  x: number
  y: number
  visible: boolean
}>()

const emit = defineEmits<(e: 'close') => void>()

const menuRef = ref<HTMLDivElement | null>(null)
const adjustedX = ref(0)
const adjustedY = ref(0)

// Adjust position to stay within viewport
watch(() => [props.x, props.y, props.visible], () => {
  if (!props.visible) return
  nextTick(() => {
    const el = menuRef.value
    if (!el) return
    const rect = el.getBoundingClientRect()
    let ax = props.x, ay = props.y
    if (ax + rect.width > window.innerWidth) ax = window.innerWidth - rect.width - 8
    if (ay + rect.height > window.innerHeight) ay = window.innerHeight - rect.height - 8
    adjustedX.value = ax
    adjustedY.value = ay
  })
})

function handleClick(item: ContextMenuItem) {
  if (item.disabled || item.separator) return
  if (item.children?.length) return // submenu
  item.action?.()
  emit('close')
}

function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    emit('close')
  }
}

onMounted(() => {
  document.addEventListener('keydown', handleKeydown)
  document.addEventListener('click', onOutsideClick)
})
onUnmounted(() => {
  document.removeEventListener('keydown', handleKeydown)
  document.removeEventListener('click', onOutsideClick)
})

function onOutsideClick(e: MouseEvent) {
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) {
    emit('close')
  }
}

const submenuOpen = ref<string | null>(null)
let submenuTimer: any = null

function openSubmenu(id: string) {
  clearTimeout(submenuTimer)
  submenuOpen.value = id
}
function closeSubmenu() {
  submenuTimer = setTimeout(() => { submenuOpen.value = null }, 150)
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      ref="menuRef"
      class="context-menu"
      :style="{ left: adjustedX + 'px', top: adjustedY + 'px' }"
      @click.stop
    >
      <template v-for="item in items" :key="item.id">
        <!-- Separator -->
        <div v-if="item.separator" class="context-menu-separator" />

        <!-- Menu item -->
        <button
          v-else
          class="context-menu-item"
          :class="{ danger: item.danger, disabled: item.disabled, 'has-submenu': item.children?.length }"
          :disabled="item.disabled"
          @click="handleClick(item)"
          @mouseenter="item.children?.length ? openSubmenu(item.id) : closeSubmenu()"
          @mouseleave="item.children?.length ? undefined : undefined"
        >
          <span class="context-menu-item-icon" v-if="item.icon"></span>
          <span class="context-menu-item-label">{{ item.label }}</span>
          <span class="context-menu-item-shortcut" v-if="item.shortcut">{{ item.shortcut }}</span>
          <span class="context-menu-item-arrow" v-if="item.children?.length">▶</span>

          <!-- Submenu -->
          <div
            v-if="item.children?.length && submenuOpen === item.id"
            class="context-submenu"
          >
            <button
              v-for="child in item.children"
              :key="child.id"
              class="context-menu-item"
              :class="{ danger: child.danger, disabled: child.disabled }"
              @click.stop="handleClick(child)"
            >
              <span class="context-menu-item-label">{{ child.label }}</span>
              <span class="context-menu-item-shortcut" v-if="child.shortcut">{{ child.shortcut }}</span>
            </button>
          </div>
        </button>
      </template>
    </div>
  </Teleport>
</template>

<style scoped>
.context-menu {
  position: fixed;
  z-index: 9999;
  min-width: 180px;
  max-width: 280px;
  background: var(--color-ide-surface, #252526);
  border: 1px solid var(--color-ide-border, #3e3e42);
  border-radius: 6px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.48), 0 0 1px rgba(0, 0, 0, 0.6);
  padding: 4px;
  overflow: hidden;
  animation: context-menu-enter 0.08s ease-out;
}

@keyframes context-menu-enter {
  from { opacity: 0; transform: scale(0.96); }
  to { opacity: 1; transform: scale(1); }
}

.context-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 5px 10px;
  border: none;
  background: transparent;
  color: var(--color-ide-text, #cccccc);
  font-size: 12px;
  font-family: inherit;
  text-align: left;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.08s;
  position: relative;
  white-space: nowrap;
}
.context-menu-item:hover:not(.disabled) {
  background: var(--color-ide-accent, #007acc);
  color: #fff;
}
.context-menu-item.disabled {
  opacity: 0.4;
  cursor: default;
}
.context-menu-item.danger:hover:not(.disabled) {
  background: var(--color-ide-error, #f44747);
}
.context-menu-item.has-submenu {
  padding-right: 24px;
}

.context-menu-item-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.context-menu-item-shortcut {
  flex-shrink: 0;
  opacity: 0.5;
  font-size: 11px;
  font-family: 'Consolas', 'Courier New', monospace;
  margin-left: 16px;
}
.context-menu-item-arrow {
  position: absolute;
  right: 6px;
  font-size: 9px;
  opacity: 0.5;
}

.context-menu-separator {
  height: 1px;
  margin: 4px 8px;
  background: var(--color-ide-border, #3e3e42);
  opacity: 0.5;
}

.context-submenu {
  position: absolute;
  left: calc(100% + 4px);
  top: -4px;
  min-width: 180px;
  background: var(--color-ide-surface, #252526);
  border: 1px solid var(--color-ide-border, #3e3e42);
  border-radius: 6px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.48);
  padding: 4px;
  z-index: 10000;
}
</style>
