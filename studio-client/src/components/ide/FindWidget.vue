<script setup lang="ts">
/**
 * FindWidget.vue — VSCode Inline Find/Replace 查找栏
 * 
 * 借鉴: VSCode editor/contrib/find/browser/findWidget.ts
 * 
 * 能力:
 *   - Ctrl+F 当前编辑器内联查找
 *   - Ctrl+H 查找+替换
 *   - 大小写敏感 / 全词匹配 / 正则
 *   - 范围内查找 / 保留大小写
 *   - 查找计数 (第N个/共M个)
 *   - 键盘: Enter找下一个, Shift+Enter找上一个, Esc关闭
 */
import { Search, Replace, X, ChevronUp, ChevronDown, CaseSensitive, WholeWord, Regex, Filter, ArrowUpDown } from 'lucide-vue-next'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'

const props = defineProps<{
  visible: boolean
  showReplace: boolean
}>()
const emit = defineEmits<{
  (e: 'close'): void
  (e: 'find', query: string, options: FindOptions): void
  (e: 'replace', query: string, replacement: string, options: FindOptions): void
  (e: 'replace-all', query: string, replacement: string, options: FindOptions): void
  (e: 'toggle-replace'): void
}>()

export interface FindMatch {
  range: { startLine: number; startCol: number; endLine: number; endCol: number }
  text: string
}

export interface FindOptions {
  caseSensitive: boolean
  wholeWord: boolean
  useRegex: boolean
  inSelection: boolean
  preserveCase: boolean
}

const query = ref('')
const replacement = ref('')
const caseSensitive = ref(false)
const wholeWord = ref(false)
const useRegex = ref(false)
const inSelection = ref(false)
const preserveCase = ref(false)
const matchCount = ref(0)
const currentMatch = ref(0)
const inputRef = ref<HTMLInputElement | null>(null)
const replaceInputRef = ref<HTMLInputElement | null>(null)

const options = computed<FindOptions>(() => ({
  caseSensitive: caseSensitive.value,
  wholeWord: wholeWord.value,
  useRegex: useRegex.value,
  inSelection: inSelection.value,
  preserveCase: preserveCase.value,
}))

const countLabel = computed(() => {
  if (!query.value) return ''
  if (matchCount.value === 0) return '无结果'
  return `${Math.min(currentMatch.value, matchCount.value)} / ${matchCount.value}`
})

function doFind(): void {
  if (!query.value) { matchCount.value = 0; currentMatch.value = 0; return }
  emit('find', query.value, options.value)
}

function doReplace(): void {
  if (!query.value) return
  emit('replace', query.value, replacement.value, options.value)
}

function doReplaceAll(): void {
  if (!query.value) return
  emit('replace-all', query.value, replacement.value, options.value)
}

function findNext(): void {
  if (!query.value) return
  emit('find', query.value, { ...options.value, /* direction: next */ })
}

function findPrev(): void {
  if (!query.value) return
  emit('find', query.value, { ...options.value, /* direction: prev */ })
}

function handleClose(): void { emit('close') }
function toggleReplace(): void { emit('toggle-replace') }

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter') {
    e.preventDefault()
    if (e.shiftKey) findPrev()
    else findNext()
  } else if (e.key === 'Escape') {
    e.preventDefault()
    handleClose()
  }
}

watch(() => props.visible, (v) => {
  if (v) nextTick(() => inputRef.value?.focus())
})

watch(query, () => {
  const q = query.value
  if (q) emit('find', q, options.value)
  else { matchCount.value = 0; currentMatch.value = 0 }
})

defineExpose({ setMatch: (idx: number, total: number) => { currentMatch.value = idx; matchCount.value = total } })

onMounted(() => { if (props.visible) nextTick(() => inputRef.value?.focus()) })
onUnmounted(() => {})
</script>

<template>
  <div v-if="visible" class="find-widget flex flex-col" style="background:var(--color-ide-surface); border:1px solid var(--color-ide-accent); border-radius:4px; box-shadow:0 2px 12px rgba(0,0,0,0.4)"
    @keydown="onKeydown">
    <!-- Find Row -->
    <div class="flex items-center gap-1 px-2 py-1.5">
      <Search :size="12" style="color:var(--color-ide-text-dim); flex-shrink:0" />
      <input ref="inputRef" v-model="query" type="text"
        class="find-input flex-1 h-6 bg-transparent text-[12px] outline-none"
        :style="{ color: 'var(--color-ide-text)' }"
        placeholder="查找" spellcheck="false"
      />
      <span v-if="countLabel" class="text-[10px] shrink-0 px-1" style="color:var(--color-ide-text-dim)">{{ countLabel }}</span>
      <!-- Toggle buttons -->
      <button class="find-toggle-btn" :class="{ active: caseSensitive }" title="区分大小写" @click="caseSensitive=!caseSensitive">
        <CaseSensitive :size="13" />
      </button>
      <button class="find-toggle-btn" :class="{ active: wholeWord }" title="全词匹配" @click="wholeWord=!wholeWord">
        <WholeWord :size="13" />
      </button>
      <button class="find-toggle-btn" :class="{ active: useRegex }" title="使用正则表达式" @click="useRegex=!useRegex">
        <Regex :size="13" />
      </button>
      <button class="find-toggle-btn" :class="{ active: inSelection }" title="在选定内容中查找" @click="inSelection=!inSelection">
        <Filter :size="13" />
      </button>
      <!-- Nav -->
      <button class="find-nav-btn" title="上一个 (Shift+Enter)" @click="findPrev">
        <ChevronUp :size="14" />
      </button>
      <button class="find-nav-btn" title="下一个 (Enter)" @click="findNext">
        <ChevronDown :size="14" />
      </button>
      <!-- Replace toggle -->
      <button class="find-nav-btn" :class="{ active: showReplace }" title="替换 (Ctrl+H)" @click="toggleReplace">
        <Replace :size="13" />
      </button>
      <button class="find-nav-btn" title="关闭 (Escape)" @click="handleClose">
        <X :size="14" />
      </button>
    </div>
    <!-- Replace Row -->
    <div v-if="showReplace" class="flex items-center gap-1 px-2 pb-1.5 border-t" style="border-color:var(--color-ide-border)">
      <Replace :size="12" style="color:var(--color-ide-text-dim); flex-shrink:0" />
      <input ref="replaceInputRef" v-model="replacement" type="text"
        class="find-input flex-1 h-6 bg-transparent text-[12px] outline-none"
        :style="{ color: 'var(--color-ide-text)' }"
        placeholder="替换为" spellcheck="false"
      />
      <button class="find-toggle-btn" :class="{ active: preserveCase }" title="保留大小写" @click="preserveCase=!preserveCase">
        <ArrowUpDown :size="13" />
      </button>
      <button class="replace-btn" title="替换" @click="doReplace">替换</button>
      <button class="replace-btn" title="全部替换 (Ctrl+Alt+Enter)" @click="doReplaceAll">全部替换</button>
    </div>
  </div>
</template>

<style scoped>
.find-widget {
  position: absolute;
  top: 0;
  right: 50px;
  z-index: 100;
  min-width: 400px;
  max-width: 600px;
}
.find-input { border-bottom: 1px solid transparent; }
.find-input:focus { border-bottom-color: var(--color-ide-accent); }

.find-toggle-btn {
  display: flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; border-radius: 3px;
  color: var(--color-ide-text-dim); cursor: pointer;
  transition: all 0.1s;
}
.find-toggle-btn:hover { background: var(--color-ide-surface-hover); color: var(--color-ide-text); }
.find-toggle-btn.active { color: var(--color-ide-accent); background: color-mix(in srgb, var(--color-ide-accent) 15%, transparent); }

.find-nav-btn {
  display: flex; align-items: center; justify-content: center;
  width: 20px; height: 20px; border-radius: 3px;
  color: var(--color-ide-text-dim); cursor: pointer;
  transition: all 0.1s;
}
.find-nav-btn:hover { background: var(--color-ide-surface-hover); color: var(--color-ide-text); }
.find-nav-btn.active { color: var(--color-ide-accent); }

.replace-btn {
  font-size: 11px; padding: 2px 6px; border-radius: 3px;
  color: var(--color-ide-text); background: var(--color-ide-surface-hover);
  transition: all 0.1s;
}
.replace-btn:hover { background: var(--color-ide-accent); color: #fff; }
</style>
