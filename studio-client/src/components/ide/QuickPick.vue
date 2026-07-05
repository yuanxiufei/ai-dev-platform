<template>
  <Teleport to="body">
    <div v-if="visible" class="quickpick-overlay" @click.self="dismiss()">
      <div class="quickpick-dropdown" :style="dropdownStyle">
        <!-- 搜索框 -->
        <div class="quickpick-input-wrapper">
          <span class="quickpick-icon">{{ busy ? '⏳' : '🔍' }}</span>
          <input
            ref="inputRef"
            v-model="query"
            :placeholder="placeholder || 'Select...'"
            class="quickpick-input"
            @keydown="onKeydown"
            @input="onInput"
            autofocus
          />
          <span v-if="query" class="quickpick-clear" @click="query = ''">✕</span>
        </div>

        <!-- 列表 -->
        <div class="quickpick-list" ref="listRef">
          <div v-if="filteredItems.length === 0" class="quickpick-empty">
            {{ emptyText || 'No results found' }}
          </div>
          <div
            v-for="(item, idx) in filteredItems"
            :key="item.id ?? idx"
            ref="listRef"
            class="quickpick-item"
            :class="{ active: idx === activeIndex, disabled: item.disabled }"
            @click="select(item, idx)"
            @mouseenter="activeIndex = idx"
          >
            <span v-if="item.icon" class="quickpick-item-icon">{{ item.icon }}</span>
            <div class="quickpick-item-content">
              <div class="quickpick-item-label">
                <span
                  v-for="(part, pi) in highlightLabel(item.label)"
                  :key="pi"
                  :class="{ highlight: part.highlight }"
                >{{ part.text }}</span>
              </div>
              <div v-if="item.description" class="quickpick-item-desc">
                {{ item.description }}
              </div>
            </div>
            <span v-if="item.detail" class="quickpick-item-detail">{{ item.detail }}</span>
            <span v-if="item.shortcut" class="quickpick-item-shortcut">{{ item.shortcut }}</span>
          </div>
        </div>

        <!-- 底部提示 -->
        <div v-if="footerHint" class="quickpick-footer">{{ footerHint }}</div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
/**
 * QuickPick — VS Code 风格下拉选择器
 *
 * 对标: vscode/src/vs/platform/quickinput/
 *
 * 用法:
 *   const picker = useQuickPick()
 *   const result = await picker.show([
 *     { id: '1', label: 'Python', description: '/usr/bin/python3', icon: '🐍' },
 *     { id: '2', label: 'Node.js', description: '/usr/bin/node', shortcut: 'Ctrl+J' },
 *   ])
 */
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'

export interface QuickPickItem {
  id?: string
  label: string
  description?: string
  detail?: string
  icon?: string
  shortcut?: string
  disabled?: boolean
  data?: any
}

const visible = ref(false)
const query = ref('')
const busy = ref(false)
const activeIndex = ref(0)
const items = ref<QuickPickItem[]>([])
const placeholder = ref('')
const emptyText = ref('')
const footerHint = ref('')
const inputRef = ref<HTMLInputElement | null>(null)
const position = ref({ x: 0, y: 0, width: 400 })

let _resolve: ((value: QuickPickItem | undefined) => void) | null = null

const dropdownStyle = computed(() => ({
  position: 'fixed' as const,
  top: `${position.value.y}px`,
  left: `${position.value.x}px`,
  width: `${position.value.width}px`,
}))

const filteredItems = computed(() => {
  if (!query.value.trim()) return items.value
  const q = query.value.toLowerCase()
  return items.value.filter(
    i => i.label.toLowerCase().includes(q) || (i.description?.toLowerCase().includes(q))
  )
})

watch(filteredItems, () => {
  if (activeIndex.value >= filteredItems.value.length) {
    activeIndex.value = Math.max(0, filteredItems.value.length - 1)
  }
})

function highlightLabel(label: string) {
  if (!query.value.trim()) return [{ text: label, highlight: false }]
  const q = query.value.toLowerCase()
  const parts: { text: string; highlight: boolean }[] = []
  let remaining = label
  while (remaining.length > 0) {
    const idx = remaining.toLowerCase().indexOf(q)
    if (idx === -1) { parts.push({ text: remaining, highlight: false }); break }
    if (idx > 0) parts.push({ text: remaining.slice(0, idx), highlight: false })
    parts.push({ text: remaining.slice(idx, idx + q.length), highlight: true })
    remaining = remaining.slice(idx + q.length)
  }
  return parts
}

function show(
  pickItems: QuickPickItem[],
  opts?: {
    placeholder?: string
    emptyText?: string
    footerHint?: string
    x?: number; y?: number; width?: number
  }
): Promise<QuickPickItem | undefined> {
  items.value = pickItems
  placeholder.value = opts?.placeholder || 'Select...'
  emptyText.value = opts?.emptyText || ''
  footerHint.value = opts?.footerHint || ''
  query.value = ''
  activeIndex.value = 0
  position.value = {
    x: opts?.x ?? 0,
    y: opts?.y ?? 100,
    width: opts?.width ?? 400,
  }

  // 中心定位 (如果未指定)
  if (!opts?.x && !opts?.y) {
    position.value.x = Math.max(0, (window.innerWidth - 480) / 2)
    position.value.y = Math.max(40, window.innerHeight * 0.15)
    position.value.width = Math.min(480, window.innerWidth - 40)
  }

  visible.value = true
  nextTick(() => inputRef.value?.focus())

  return new Promise(resolve => {
    _resolve = resolve
  })
}

function dismiss() {
  visible.value = false
  _resolve?.(undefined)
  _resolve = null
}

function select(item: QuickPickItem, _idx: number) {
  if (item.disabled) return
  visible.value = false
  _resolve?.(item)
  _resolve = null
}

function onKeydown(e: KeyboardEvent) {
  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      activeIndex.value = Math.min(activeIndex.value + 1, filteredItems.value.length - 1)
      break
    case 'ArrowUp':
      e.preventDefault()
      activeIndex.value = Math.max(activeIndex.value - 1, 0)
      break
    case 'Enter':
      e.preventDefault()
      if (filteredItems.value[activeIndex.value]) {
        select(filteredItems.value[activeIndex.value], activeIndex.value)
      }
      break
    case 'Escape':
      e.preventDefault()
      dismiss()
      break
  }
}

function onInput() {
  activeIndex.value = 0
}

onMounted(() => document.addEventListener('keydown', onGlobalEscape))
onUnmounted(() => document.removeEventListener('keydown', onGlobalEscape))

function onGlobalEscape(e: KeyboardEvent) {
  if (e.key === 'Escape' && visible.value) {
    dismiss()
  }
}

defineExpose({ show, dismiss })
</script>

<style scoped>
.quickpick-overlay {
  position: fixed; inset: 0; z-index: 99999;
  background: rgba(0, 0, 0, 0.2);
}
.quickpick-dropdown {
  background: #1e1e2e;
  border: 1px solid #3b3b5c;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
  overflow: hidden;
}
.quickpick-input-wrapper {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid #2e2e44;
}
.quickpick-icon { font-size: 14px; }
.quickpick-input {
  flex: 1; background: transparent; border: none; outline: none;
  color: #e0e0f0; font-size: 14px; font-family: inherit;
}
.quickpick-input::placeholder { color: #6e6e88; }
.quickpick-clear { cursor: pointer; color: #888; font-size: 14px; }
.quickpick-clear:hover { color: #fff; }
.quickpick-list { max-height: 300px; overflow-y: auto; padding: 4px 0; }
.quickpick-empty { padding: 24px; text-align: center; color: #6e6e88; font-size: 13px; }
.quickpick-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 14px; cursor: pointer; transition: background 0.1s;
}
.quickpick-item:hover { background: #2a2a44; }
.quickpick-item.active { background: #3b3b6e; }
.quickpick-item.disabled { opacity: 0.4; cursor: default; }
.quickpick-item-icon { font-size: 16px; flex-shrink: 0; }
.quickpick-item-content { flex: 1; min-width: 0; }
.quickpick-item-label { font-size: 14px; color: #d0d0e8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.quickpick-item-label .highlight { color: #62d4ff; font-weight: 600; }
.quickpick-item-desc { font-size: 12px; color: #8888a8; margin-top: 1px; }
.quickpick-item-detail { font-size: 12px; color: #6e6e88; flex-shrink: 0; }
.quickpick-item-shortcut {
  font-size: 11px; color: #6e6e88;
  background: #2a2a44; padding: 2px 6px; border-radius: 4px;
}
.quickpick-footer { padding: 6px 14px; font-size: 11px; color: #6e6e88; border-top: 1px solid #2e2e44; }
</style>
