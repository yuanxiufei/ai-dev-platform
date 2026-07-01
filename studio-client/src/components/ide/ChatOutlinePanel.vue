<script setup lang="ts">
/**
 * CodeBuddy IDE — Chat Session Outline Panel
 *
 * Session 26: 从 AI 回复中提取 H1-H3 标题，生成可点击跳转大纲
 * 借鉴: hermes-studio OutlinePanel.vue + VSCode chat outline
 */

import { ChevronDown, ChevronRight, ListTree, Hash, X } from "lucide-vue-next"
import { computed, ref } from "vue"

export interface OutlineHeading {
  id: string
  level: number
  text: string
  messageIndex: number
  elementId: string
}

const props = defineProps<{
  messages: Array<{ role: string; content: string; timestamp: number }>
  visible: boolean
}>()

const emit = defineEmits<{
  (e: "close"): void
  (e: "scroll-to", elementId: string): void
}>()

const activeHeadingId = ref<string | null>(null)
const collapsed = ref<Set<string>>(new Set())

/** 从 AI 消息中提取所有标题 */
const headings = computed<OutlineHeading[]>(() => {
  const result: OutlineHeading[] = []
  const headingRegex = /^(#{1,3})\s+(.+)$/gm

  props.messages.forEach((msg, mi) => {
    if (msg.role !== "assistant") return
    let match: RegExpExecArray | null
    headingRegex.lastIndex = 0
    let msgHCount = 0
    while ((match = headingRegex.exec(msg.content)) !== null) {
      msgHCount++
      const level = match[1].length
      const text = match[2].trim()
      const id = `chat-h-${mi}-${msgHCount}`
      result.push({ id, level, text, messageIndex: mi, elementId: id })
    }
  })

  return result
})

/** 计算每个标题的视觉缩进深度（基于 level 层级栈） */
function getVisualDepth(index: number): number {
  if (index === 0) return 0
  const h = headings.value[index]
  // 向前找最近的父级
  for (let i = index - 1; i >= 0; i--) {
    const p = headings.value[i]
    if (p.level < h.level) return getVisualDepth(i) + 1
  }
  return 0
}

/** 判断 heading 是否在某个折叠的父级下 */
function isHidden(index: number): boolean {
  if (index === 0) return false
  // 向前找所有 ≤ 当前 level 的祖先
  for (let i = index - 1; i >= 0; i--) {
    const p = headings.value[i]
    if (p.level < headings.value[index].level) {
      if (collapsed.value.has(p.id)) return true
    }
  }
  return false
}

function selectHeading(h: OutlineHeading): void {
  activeHeadingId.value = h.id
  emit("scroll-to", h.elementId)
}

function toggleCollapse(id: string): void {
  const s = new Set(collapsed.value)
  if (s.has(id)) s.delete(id)
  else s.add(id)
  collapsed.value = s
}

/** 检查是否有子标题（后面有级别更低/更深的标题） */
function hasChildren(index: number): boolean {
  const h = headings.value[index]
  for (let i = index + 1; i < headings.value.length; i++) {
    const n = headings.value[i]
    if (n.level <= h.level) return false
    if (n.level > h.level) return true
  }
  return false
}
</script>

<template>
  <div v-if="visible" class="flex flex-col h-full border-l border-[var(--color-ide-border)] bg-[var(--color-ide-bg-secondary)]" style="width: 220px;">
    <!-- Header -->
    <div class="flex items-center justify-between px-3 h-8 shrink-0 border-b border-[var(--color-ide-border)]">
      <div class="flex items-center gap-1.5">
        <ListTree :size="13" class="text-[var(--color-ide-text-dim)]" />
        <span class="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-ide-text-dim)]">
          大纲
        </span>
        <span v-if="headings.length" class="text-[10px] text-[var(--color-ide-text-dim)]/50 ml-1">
          {{ headings.length }}
        </span>
      </div>
      <button
        class="p-0.5 rounded hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] transition-colors"
        title="关闭大纲" @click="emit('close')">
        <X :size="13" />
      </button>
    </div>

    <!-- Heading List (Flat with visual indentation) -->
    <div class="flex-1 overflow-y-auto py-1">
      <div v-if="headings.length === 0" class="px-3 py-6 text-center text-[11px] text-[var(--color-ide-text-dim)]/50">
        AI 回复中暂无标题
      </div>

      <template v-else>
        <button
          v-for="(h, idx) in headings"
          :key="h.id"
          v-show="!isHidden(idx)"
          class="w-full text-left flex items-center gap-0.5 py-0.5 pr-2 transition-colors text-[11px] group"
          :class="[
            h.id === activeHeadingId
              ? 'bg-[var(--color-ide-accent)]/10 text-[var(--color-ide-accent)]'
              : 'text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]'
          ]"
          :style="{ paddingLeft: `${8 + getVisualDepth(idx) * 14}px` }"
          @click="selectHeading(h)"
        >
          <!-- Expand/Collapse toggle -->
          <button
            v-if="hasChildren(idx)"
            class="w-3 flex items-center justify-center shrink-0"
            @click.stop="toggleCollapse(h.id)"
          >
            <ChevronRight v-if="collapsed.has(h.id)" :size="10" class="opacity-50" />
            <ChevronDown v-else :size="10" class="opacity-50" />
          </button>
          <span v-else class="w-3 shrink-0" />

          <!-- Level indicator -->
          <Hash v-if="h.level === 1" :size="10" class="shrink-0 opacity-60" />
          <Hash v-else-if="h.level === 2" :size="9" class="shrink-0 opacity-50" />
          <Hash v-else :size="8" class="shrink-0 opacity-40" />

          <!-- Text -->
          <span class="truncate" :class="{
            'font-semibold text-[12px]': h.level === 1,
            'font-medium': h.level === 2,
          }">
            {{ h.text }}
          </span>
        </button>
      </template>
    </div>

    <!-- Footer -->
    <div class="px-3 py-1.5 border-t border-[var(--color-ide-border)]/50 text-[9px] text-[var(--color-ide-text-dim)]/40 text-center">
      点击跳转 · {{ headings.length }} 个章节
    </div>
  </div>
</template>
