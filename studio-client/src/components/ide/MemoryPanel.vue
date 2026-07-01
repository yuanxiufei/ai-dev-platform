<script setup lang="ts">
/**
 * CodeBuddy IDE — Memory Panel (Hermes-Enhanced)
 * 3-column memory editing: My Notes | User Profile | Soul
 */
import { computed, onMounted, ref } from "vue"
import { BookOpen, RefreshCw, Save, User, X } from "lucide-vue-next"
import apiClient from "@/api/client"

interface MemorySection {
  key: string
  icon: any
  title: string
  placeholder: string
}

const sections: MemorySection[] = [
  { key: 'memory', icon: BookOpen, title: '我的笔记', placeholder: '暂无笔记...' },
  { key: 'user', icon: User, title: '用户画像', placeholder: '暂无画像...' },
  { key: 'soul', icon: RefreshCw, title: '灵魂', placeholder: '暂无灵魂...' },
]

interface MemoryState {
  content: string
  mtime: number | null
  loading: boolean
  editing: boolean
  editContent: string
  saving: boolean
}

const memories = ref<Record<string, MemoryState>>({})
const globalLoading = ref(false)

function initMemoryState() {
  const state: Record<string, MemoryState> = {}
  for (const s of sections) {
    state[s.key] = { content: '', mtime: null, loading: false, editing: false, editContent: '', saving: false }
  }
  memories.value = state
}

async function fetchMemory() {
  globalLoading.value = true
  try {
    const resp = await apiClient.get('/memory/memory-data')
    const data = resp.data || {}
    for (const s of sections) {
      memories.value[s.key].content = (data[s.key] || '').replace(/§/g, '\n\n')
      memories.value[s.key].mtime = data[`${s.key}_mtime`] || null
    }
  } catch {
    // Offline — keep existing data
  } finally {
    globalLoading.value = false
  }
}

function formatMtime(ts: number | null): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  return `${String(d.getMonth()+1).padStart(2,'0')}/${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

function startEdit(key: string) {
  const m = memories.value[key]
  m.editContent = m.content
  m.editing = true
}

function cancelEdit(key: string) {
  memories.value[key].editing = false
}

async function saveEdit(key: string) {
  const m = memories.value[key]
  m.saving = true
  try {
    await apiClient.post('/memory/memory-data', {
      section: key,
      content: m.editContent,
    })
    m.content = m.editContent
    m.mtime = Math.floor(Date.now() / 1000)
    m.editing = false
  } catch {
    // Keep edit state on error
  } finally {
    m.saving = false
  }
}

function renderMarkdown(text: string): string {
  if (!text) return ''
  return text
    .replace(/^### (.+)$/gm, '<h4 class="text-[11px] font-semibold text-[var(--color-ide-text-bright)] mt-3 mb-1">$1</h4>')
    .replace(/^## (.+)$/gm, '<h3 class="text-[12px] font-semibold text-[var(--color-ide-text-bright)] mt-3 mb-1">$1</h3>')
    .replace(/^# (.+)$/gm, '<h2 class="text-[13px] font-bold text-[var(--color-ide-text-bright)] mt-3 mb-1">$1</h2>')
    .replace(/^- (.+)$/gm, '<li class="ml-3 text-[11px] text-[var(--color-ide-text-secondary)]">• $1</li>')
    .replace(/\*\*(.+?)\*\*/g, '<strong class="text-[var(--color-ide-text-bright)]">$1</strong>')
    .replace(/`([^`]+)`/g, '<code class="px-1 rounded text-[10px] font-mono" style="background:var(--color-ide-bg-tertiary);color:var(--color-ide-accent)">$1</code>')
    .replace(/\n/g, '<br/>')
}

onMounted(() => {
  initMemoryState()
  fetchMemory()
})
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden bg-[var(--color-ide-surface)]">
    <!-- Header -->
    <div class="flex items-center justify-between px-3 py-2 border-b border-[var(--color-ide-border)] shrink-0">
      <div class="flex items-center gap-2">
        <BookOpen :size="14" class="text-[var(--color-ide-accent)]" />
        <span class="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-ide-text)]">记忆管理</span>
      </div>
      <button class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]"
        @click="fetchMemory" :disabled="globalLoading" title="刷新">
        <RefreshCw :size="12" :class="{ 'animate-spin': globalLoading }" />
      </button>
    </div>

    <!-- Content: 3 columns -->
    <div class="flex-1 overflow-y-auto p-2 space-y-2">
      <div v-for="section in sections" :key="section.key"
        class="rounded-lg border border-[var(--color-ide-border)] overflow-hidden"
        style="background:var(--color-ide-bg-secondary)">
        <!-- Section Header -->
        <div class="flex items-center justify-between px-3 py-2 border-b border-[var(--color-ide-border)]/50">
          <div class="flex items-center gap-2">
            <component :is="section.icon" :size="12" class="text-[var(--color-ide-text-dim)]" />
            <span class="text-[11px] font-semibold text-[var(--color-ide-text)]">{{ section.title }}</span>
          </div>
          <div class="flex items-center gap-1">
            <span v-if="memories[section.key]?.mtime" class="text-[9px] text-[var(--color-ide-text-dim)]">
              {{ formatMtime(memories[section.key].mtime) }}
            </span>
            <button v-if="!memories[section.key]?.editing"
              class="text-[10px] px-2 py-0.5 rounded-md border border-[var(--color-ide-border)] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:border-[var(--color-ide-accent)]/50 transition-colors"
              @click="startEdit(section.key)">
              编辑
            </button>
          </div>
        </div>

        <!-- Content Area -->
        <div class="p-3">
          <!-- Edit Mode -->
          <template v-if="memories[section.key]?.editing">
            <textarea v-model="memories[section.key].editContent"
              class="w-full min-h-[100px] rounded-md border border-[var(--color-ide-border)] bg-[var(--color-editor-bg)] text-[11px] text-[var(--color-ide-text)] p-2 font-mono leading-relaxed resize-y focus:border-[var(--color-ide-accent)] focus:outline-none"
              :placeholder="section.placeholder"
              rows="6" />
            <div class="flex items-center justify-end gap-1.5 mt-2">
              <button class="text-[10px] px-2 py-1 rounded-md text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
                @click="cancelEdit(section.key)">
                <X :size="10" class="inline mr-0.5" />取消
              </button>
              <button class="text-[10px] px-2 py-1 rounded-md bg-[var(--color-ide-accent)] text-white hover:brightness-110 transition-colors"
                :disabled="memories[section.key]?.saving"
                @click="saveEdit(section.key)">
                <Save :size="10" class="inline mr-0.5" />{{ memories[section.key]?.saving ? '保存中...' : '保存' }}
              </button>
            </div>
          </template>

          <!-- View Mode -->
          <template v-else>
            <div v-if="memories[section.key]?.content"
              class="text-[11px] leading-relaxed text-[var(--color-ide-text-secondary)] prose-memory"
              v-html="renderMarkdown(memories[section.key].content)" />
            <div v-else class="text-[11px] text-[var(--color-ide-text-dim)] italic py-4 text-center">
              {{ section.placeholder }}
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.prose-memory :deep(li) { margin-top: 2px; }
.prose-memory :deep(strong) { font-weight: 600; }
</style>
