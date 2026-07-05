<script setup lang="ts">
/**
 * Session 57: Language Status Indicator — 对标 VSCode languageStatus service
 * 状态栏中显示当前文件语言及其功能支持状态的面板。
 *
 * 功能:
 *   - 显示当前语言名称 (可点击切换)
 *   - 语言功能支持矩阵 (格式化/跳转定义/自动完成/重构/文档悬停)
 *   - LSP 诊断状态 (错误/警告/信息计数)
 *   - 点击弹出详情面板
 */
import { computed, ref } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import {
  Code2, AlertCircle, AlertTriangle, Info, CheckCircle2,
  ArrowRightLeft, SearchCode, Wand2, FileCode, BookOpen,
} from 'lucide-vue-next'

const store = useIDEStore()

const showDetails = ref(false)

// ── 语言显示名称 ──
const langDisplay = computed(() => {
  const tab = store.activeTab
  if (!tab) return '纯文本'
  const m: Record<string, string> = {
    typescript:'TypeScript', javascript:'JavaScript', vue:'Vue',
    python:'Python', json:'JSON', markdown:'Markdown', html:'HTML',
    css:'CSS', go:'Go', rust:'Rust', java:'Java', cpp:'C++',
    yaml:'YAML', xml:'XML', sql:'SQL', shell:'Shell Script',
  }
  return m[tab.language ?? ''] ?? tab.language ?? '纯文本'
})

// ── 语言功能支持矩阵 ──
interface LangFeatures {
  format: boolean; definition: boolean; completion: boolean
  refactor: boolean; hover: boolean; diagnostics: boolean
}

const langFeatures = computed<LangFeatures>(() => {
  const lang = store.activeTab?.language ?? 'plaintext'
  const map: Record<string, LangFeatures> = {
    typescript: { format:true, definition:true, completion:true, refactor:true, hover:true, diagnostics:true },
    javascript: { format:true, definition:true, completion:true, refactor:true, hover:true, diagnostics:true },
    vue:        { format:true, definition:true, completion:true, refactor:true, hover:true, diagnostics:true },
    python:     { format:false, definition:true, completion:true, refactor:false, hover:true, diagnostics:true },
    html:       { format:true, definition:false, completion:true, refactor:false, hover:true, diagnostics:false },
    css:        { format:true, definition:false, completion:true, refactor:false, hover:true, diagnostics:true },
    json:       { format:true, definition:false, completion:true, refactor:false, hover:true, diagnostics:true },
    markdown:   { format:false, definition:false, completion:true, refactor:false, hover:false, diagnostics:false },
    go:         { format:true, definition:true, completion:true, refactor:true, hover:true, diagnostics:true },
    rust:       { format:false, definition:true, completion:true, refactor:false, hover:true, diagnostics:false },
  }
  return map[lang] ?? { format:false, definition:false, completion:true, refactor:false, hover:false, diagnostics:false }
})

// ── 诊断统计 ──
const diagnostics = computed(() => ({
  errors: store.problems?.filter((p: any) => p.severity === 'error').length ?? 0,
  warnings: store.problems?.filter((p: any) => p.severity === 'warning').length ?? 0,
  infos: store.problems?.filter((p: any) => p.severity === 'info').length ?? 0,
  total: store.problems?.length ?? 0,
}))

type FeatureKey = 'format' | 'definition' | 'completion' | 'refactor' | 'hover' | 'diagnostics'
type FeatureDef = { key: FeatureKey; label: string; icon: any; desc: string }

function formatLabel(key: FeatureKey): FeatureDef {
  const defs: FeatureDef[] = [
    { key:'format', label:'格式化', icon: ArrowRightLeft, desc:'代码格式化 (Alt+Shift+F)' },
    { key:'definition', label:'转到定义', icon: SearchCode, desc:'跳转到符号定义 (F12)' },
    { key:'completion', label:'自动完成', icon: Code2, desc:'智能代码补全 (Ctrl+Space)' },
    { key:'refactor', label:'重构', icon: Wand2, desc:'代码重构 (F2 重命名 / 提取函数等)' },
    { key:'hover', label:'悬停提示', icon: BookOpen, desc:'悬停显示类型信息与文档' },
    { key:'diagnostics', label:'诊断', icon: AlertCircle, desc:'实时错误/警告检测' },
  ]
  return defs.find(d => d.key === key)!
}

const featureKeys: FeatureKey[] = ['definition', 'completion', 'hover', 'format', 'refactor', 'diagnostics']

function toggleDetails(e: MouseEvent) {
  e.stopPropagation()
  showDetails.value = !showDetails.value
}

function closeDetails(e: MouseEvent) {
  if (showDetails.value) showDetails.value = false
}
</script>

<template>
  <div class="relative" @click="toggleDetails" @click.stop>
    <!-- 语言名称按钮 -->
    <button
      class="statusbar-item hover:bg-white/10 flex items-center gap-1.5"
      style="padding-left:10px; padding-right:10px; border-radius:3px; height:22px; line-height:22px;"
      title="语言模式 — 点击查看详情"
    >
      <Code2 :size="11" style="opacity:0.7" />
      <span>{{ langDisplay }}</span>
      <!-- 诊断计数徽章 -->
      <span v-if="diagnostics.errors > 0"
        class="flex items-center gap-0.5"
        style="color: var(--color-ide-error); font-size:10px; font-weight:600">
        <AlertCircle :size="10" />
        {{ diagnostics.errors }}
      </span>
      <span v-if="diagnostics.warnings > 0"
        class="flex items-center gap-0.5"
        style="color: var(--color-ide-warning); font-size:10px; font-weight:600; margin-left:4px">
        <AlertTriangle :size="10" />
        {{ diagnostics.warnings }}
      </span>
    </button>

    <!-- 弹出详情面板 -->
    <Teleport to="body">
      <div
        v-if="showDetails"
        class="fixed z-[500] min-w-[220px] rounded shadow-2xl"
        style="background: var(--color-ide-surface); border: 1px solid var(--color-ide-border);"
        :style="{ bottom: '28px', right: '200px' }"
        @click.stop
      >
        <!-- 标题 -->
        <div class="px-3 py-2 flex items-center justify-between border-b"
          style="border-color: var(--color-ide-border);">
          <span class="text-xs font-semibold" style="color: var(--color-ide-text);">
            <Code2 :size="12" class="inline mr-1" />
            {{ langDisplay }}
          </span>
          <button
            class="p-0.5 rounded hover:bg-white/5"
            style="color: var(--color-ide-text-dim);"
            @click="showDetails = false">
            ✕
          </button>
        </div>

        <!-- 诊断摘要 -->
        <div v-if="diagnostics.total > 0" class="px-3 py-2 border-b"
          style="border-color: var(--color-ide-border);">
          <div class="text-[10px] uppercase font-semibold mb-1" style="color: var(--color-ide-text-dim);">诊断</div>
          <div class="flex items-center gap-2 text-[11px]">
            <span v-if="diagnostics.errors > 0" style="color: var(--color-ide-error);">
              <AlertCircle :size="12" class="inline mr-1" />{{ diagnostics.errors }} 错误
            </span>
            <span v-if="diagnostics.warnings > 0" style="color: var(--color-ide-warning);">
              <AlertTriangle :size="12" class="inline mr-1" />{{ diagnostics.warnings }} 警告
            </span>
            <span v-if="diagnostics.infos > 0" style="color: var(--color-ide-info);">
              <Info :size="12" class="inline mr-1" />{{ diagnostics.infos }} 信息
            </span>
            <span v-if="diagnostics.total === 0" style="color: var(--color-ide-success);">
              <CheckCircle2 :size="12" class="inline mr-1" />无问题
            </span>
          </div>
        </div>

        <!-- 功能支持矩阵 -->
        <div class="px-3 py-2">
          <div class="text-[10px] uppercase font-semibold mb-1.5" style="color: var(--color-ide-text-dim);">语言功能</div>
          <div v-for="key in featureKeys" :key="key" class="flex items-center justify-between py-0.5 text-[11px]">
            <div class="flex items-center gap-1.5" :style="{ color: langFeatures[key] ? 'var(--color-ide-text)' : 'var(--color-ide-text-dim)' }">
              <component :is="formatLabel(key).icon" :size="12" :style="{ opacity: langFeatures[key] ? 1 : 0.3 }" />
              <span>{{ formatLabel(key).label }}</span>
            </div>
            <span v-if="langFeatures[key]" style="color: var(--color-ide-success); font-size:10px">✅</span>
            <span v-else style="color: var(--color-ide-text-dim); font-size:10px; opacity:0.4">—</span>
          </div>
        </div>

        <!-- 底部提示 -->
        <div class="px-3 py-1.5 border-t text-[9px]"
          style="border-color: var(--color-ide-border); color: var(--color-ide-text-dim); opacity:0.6;">
          语言功能由 Monaco Editor 内置提供
        </div>
      </div>
      <!-- 点击外部关闭 -->
      <div v-if="showDetails" class="fixed inset-0 z-[499]" @click="closeDetails" />
    </Teleport>
  </div>
</template>

<style scoped>
.statusbar-item { height: 22px; line-height: 22px; white-space: nowrap; }
</style>
