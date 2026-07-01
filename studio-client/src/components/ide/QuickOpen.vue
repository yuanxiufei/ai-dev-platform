<script setup lang="ts">
/**
 * Quick Open (Ctrl+P) — VSCode-style file picker
 * Fuzzy-match workspace files with instant preview
 */
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { FileSearch, File, Folder, CornerDownLeft } from 'lucide-vue-next'

defineProps<{ visible: boolean }>()
const emit = defineEmits<(e: 'close') => void>()

const store = useIDEStore()
const inputRef = ref<HTMLInputElement | null>(null)
const listRef = ref<HTMLDivElement | null>(null)
const query = ref('')
const selectedIdx = ref(0)

/** Collect all files from file tree (recursive) */
function collectFiles(nodes: any[], prefix = ''): { name: string; path: string; isDir: boolean }[] {
  const result: { name: string; path: string; isDir: boolean }[] = []
  for (const node of nodes) {
    const fullPath = prefix ? `${prefix}/${node.name}` : node.name
    if (node.isDir && node.children) {
      result.push(...collectFiles(node.children, fullPath))
    } else if (!node.isDir) {
      result.push({ name: node.name, path: fullPath, isDir: false })
    }
  }
  return result
}

const allFiles = computed(() => collectFiles(store.fileTree))

/** Fuzzy match score (VSCode-style: consecutive chars > scattered) */
function fuzzyScore(path: string, q: string): number {
  if (!q) return 1
  const lower = path.toLowerCase()
  const qLower = q.toLowerCase()
  let score = 0
  let qi = 0
  let consecutive = 0
  for (let i = 0; i < lower.length && qi < qLower.length; i++) {
    if (lower[i] === qLower[qi]) {
      score += consecutive > 0 ? 10 + consecutive : 20
      consecutive++
      qi++
    } else {
      consecutive = 0
      score -= 1
    }
  }
  return qi === qLower.length ? score : -1
}

const filteredFiles = computed(() => {
  if (!query.value.trim()) {
    // Empty: show recent files (last 10 opened tabs)
    return store.tabs.slice(0, 10).map(t => ({
      name: t.label,
      path: t.filePath || t.label,
      isDir: false,
      recent: true,
    }))
  }
  const q = query.value.trim()
  const scored = allFiles.value
    .map(f => ({ ...f, score: fuzzyScore(f.path, q), recent: false }))
    .filter(f => f.score > 0)
    .sort((a: any, b: any) => b.score - a.score)
    .slice(0, 20)
  return scored
})

watch(() => query.value, () => { selectedIdx.value = 0 })

function openFile(path: string) {
  store.openFile(path)
  emit('close')
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') { e.preventDefault(); emit('close') }
  else if (e.key === 'ArrowDown') { e.preventDefault(); selectedIdx.value = Math.min(selectedIdx.value + 1, filteredFiles.value.length - 1); scrollToSelected() }
  else if (e.key === 'ArrowUp') { e.preventDefault(); selectedIdx.value = Math.max(selectedIdx.value - 1, 0); scrollToSelected() }
  else if (e.key === 'Enter') {
    e.preventDefault()
    if (filteredFiles.value[selectedIdx.value]) {
      openFile(filteredFiles.value[selectedIdx.value].path)
    }
  }
}

function scrollToSelected() {
  nextTick(() => {
    const el = listRef.value?.querySelector('.quick-open-item.selected') as HTMLElement
    el?.scrollIntoView({ block: 'nearest' })
  })
}

function highlightPath(path: string, q: string): { pre: string; hi: string; post: string } {
  if (!q) return { pre: '', hi: '', post: path }
  const idx = path.toLowerCase().indexOf(q.toLowerCase())
  if (idx === -1) return { pre: path, hi: '', post: '' }
  return {
    pre: path.slice(0, idx),
    hi: path.slice(idx, idx + q.length),
    post: path.slice(idx + q.length),
  }
}

function getFileIcon(name: string, isDir: boolean) {
  if (isDir) return Folder
  const ext = name.split('.').pop()?.toLowerCase()
  return File
}

// Auto-focus on show
watch(() => (arguments as any)[0]?.visible ?? false, (v: boolean) => {
  if (v) {
    query.value = ''
    selectedIdx.value = 0
    nextTick(() => inputRef.value?.focus())
  }
})

onMounted(() => {
  document.addEventListener('keydown', globalKeyHandler)
})
onUnmounted(() => {
  document.removeEventListener('keydown', globalKeyHandler)
})

function globalKeyHandler(e: KeyboardEvent) {
  if (((e.ctrlKey || e.metaKey) && e.key === 'p') && !e.shiftKey) {
    e.preventDefault()
    query.value = ''
    selectedIdx.value = 0
    nextTick(() => inputRef.value?.focus())
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="visible" class="fixed inset-0 z-[210] flex flex-col" @keydown="onKeydown">
        <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" @click.self="emit('close')" />
        <div class="mx-auto mt-[15vh] w-[600px] max-w-[92vw] bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded-lg shadow-2xl flex flex-col overflow-hidden z-10">
          <!-- Search input -->
          <div class="flex items-center gap-2 px-3 py-3 border-b border-[var(--color-ide-border)]">
            <FileSearch :size="18" class="text-[var(--color-ide-accent)] shrink-0" />
            <input
              ref="inputRef"
              v-model="query"
              type="text"
              placeholder="输入文件名以快速打开..."
              class="flex-1 bg-transparent outline-none text-[14px] text-[var(--color-ide-text)] placeholder:text-[var(--color-ide-text-dim)] font-medium"
              @keydown="onKeydown"
            />
            <kbd class="px-1.5 py-0.5 text-[10px] bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)] rounded font-mono border border-[var(--color-ide-border)]">Esc</kbd>
          </div>

          <!-- File list -->
          <div ref="listRef" class="flex-1 overflow-y-auto max-h-[340px]">
            <div v-if="filteredFiles.length === 0 && query" class="flex flex-col items-center justify-center py-10 text-[var(--color-ide-text-dim)] text-[12px]">
              <File :size="24" class="mb-2 opacity-30" />
              <p>找不到匹配的文件</p>
            </div>
            <div v-else>
              <div
                v-for="(file, idx) in filteredFiles"
                :key="file.path"
                class="quick-open-item flex items-center gap-2.5 px-3 py-2 cursor-pointer transition-colors"
                :class="{ selected: idx === selectedIdx }"
                :style="{
                  background: idx === selectedIdx ? 'var(--color-ide-surface-active)' : 'transparent',
                  borderLeft: idx === selectedIdx ? '2px solid var(--color-ide-accent)' : '2px solid transparent',
                }"
                @click="openFile(file.path)"
                @mouseenter="selectedIdx = idx"
              >
                <!-- File icon -->
                <component :is="getFileIcon(file.name, (file as any).isDir)" :size="16" class="shrink-0"
                  :style="{ color: (file as any).isDir ? 'var(--color-ide-accent)' : 'var(--color-ide-text-dim)' }" />
                <!-- File name -->
                <div class="flex-1 min-w-0 flex items-center gap-1.5">
                  <template v-if="query">
                    <span class="text-[13px] font-medium text-[var(--color-ide-text)] truncate">
                      <span style="opacity:0.5">{{ highlightPath(file.name, query).pre }}</span>
                      <span style="color:var(--color-ide-accent);font-weight:600">{{ highlightPath(file.name, query).hi }}</span>
                      <span style="opacity:0.5">{{ highlightPath(file.name, query).post }}</span>
                    </span>
                    <span class="text-[11px] text-[var(--color-ide-text-dim)] opacity-40 truncate ml-2">
                      {{ file.path.split('/').slice(0, -1).join('/') || '📁 根目录' }}
                    </span>
                  </template>
                  <template v-else>
                    <span class="text-[13px] font-medium text-[var(--color-ide-accent)]">{{ file.name }}</span>
                    <span class="text-[11px] text-[var(--color-ide-text-dim)] opacity-40 truncate ml-1">{{ file.path }}</span>
                  </template>
                </div>
                <!-- Recent badge -->
                <span v-if="(file as any).recent" class="text-[9px] px-1.5 py-0.5 rounded bg-[var(--color-ide-accent)]/10 text-[var(--color-ide-accent)] shrink-0">最近</span>
              </div>
            </div>
          </div>

          <!-- Footer hint -->
          <div class="flex items-center gap-4 px-3 py-2 border-t border-[var(--color-ide-border)] text-[10px] text-[var(--color-ide-text-dim)] bg-[var(--color-ide-bg)]/50">
            <span class="flex items-center gap-1"><CornerDownLeft :size="10"/> 打开</span>
            <span>↑↓ 导航</span>
            <span>Esc 关闭</span>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
.quick-open-item {
  border-radius: 2px;
}
</style>
