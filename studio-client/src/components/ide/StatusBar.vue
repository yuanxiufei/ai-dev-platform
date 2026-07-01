<script setup lang="ts">/** CodeBuddy IDE — Bottom Status Bar (VSCode 风格增强) */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { GitBranch, AlertCircle, CheckCircle2, Bell, XCircle, Cpu, WifiOff, HardDrive, Braces, Sun, Moon } from 'lucide-vue-next'
import { useThemeStore } from '@/stores/useThemeStore'

const store = useIDEStore()
const themeStore = useThemeStore()

// ── 状态 ──
const posText = computed(() => `行 ${store.cursorPosition.line}, 列 ${store.cursorPosition.column}`)
const selectionText = computed(() => store.cursorPosition.selectedChars > 0 ? `已选择 ${store.cursorPosition.selectedChars} 字符` : '')
const langDisplay = computed(() => {
  const tab = store.activeTab
  if (!tab) return '纯文本'
  const map: Record<string, string> = { typescript:'TypeScript', javascript:'JavaScript', typescriptreact:'TypeScript React', python:'Python', json:'JSON', markdown:'Markdown', html:'HTML', css:'CSS', shell:'Shell', yaml:'YAML', go:'Go', vue:'Vue' }
  return map[tab.language ?? ''] ?? tab.language ?? '纯文本'
})
const branchLabel = computed(() => store.gitBranch || 'main')
const changedLabel = computed(() => store.gitChangedFiles > 0 ? String(store.gitChangedFiles) : '0')

/** 🆕 VSCode 风格: 当前活跃模型 */
const activeModel = ref('')
const modelHealth = ref<'healthy' | 'degraded' | 'unavailable'>('healthy')
const notificationCount = ref(0)

/** 从 localStorage 读取上次选择的模型 */
function loadActiveModel() {
  try {
    const raw = localStorage.getItem('active_model_name')
    if (raw) activeModel.value = raw
  } catch { /* ignore */ }
}
loadActiveModel()

/** 🆕 定期检查模型健康状态 */
let healthTimer: ReturnType<typeof setInterval> | null = null
async function checkModelHealth() {
  try {
    const res = await fetch('/api/v1/system/models/providers')
    if (res.ok) modelHealth.value = 'healthy'
    else modelHealth.value = 'degraded'
  } catch {
    modelHealth.value = 'unavailable'
  }
}
onMounted(() => {
  checkModelHealth()
  healthTimer = setInterval(checkModelHealth, 60_000)
})
onUnmounted(() => {
  if (healthTimer) clearInterval(healthTimer)
})

/** 🆕 模型健康 dot 颜色 */
const healthDotColor = computed(() => {
  if (modelHealth.value === 'healthy') return '#4ADE80'
  if (modelHealth.value === 'degraded') return '#FBBF24'
  return '#EF4444'
})

/** 🆕 格式化模型名 */
const modelLabel = computed(() => {
  if (!activeModel.value) return '自动'
  const name = activeModel.value
  // 缩短常见模型名
  return name
    .replace('qwen25-coder-7b', 'Qwen2.5-Coder-7B')
    .replace('deepseek-r1', 'DeepSeek-R1')
    .replace('deepseek-v3', 'DeepSeek-V3')
    .replace('claude-sonnet', 'Claude-Sonnet')
    .replace('gpt-4o', 'GPT-4o')
    .replace('gemma4-31b', 'Gemma4-31B')
    .replace('qwen3-coder-30b', 'Qwen3-Coder-30B')
    || name
})
</script>

<template>
  <footer class="h-[var(--statusbar-height)] bg-[var(--statusbar-bg)] border-t border-[var(--color-ide-border)] flex items-center px-1.5 shrink-0 select-none text-xs">
    <!-- 🆕 左区: 工作区 + Git -->
    <div class="flex items-center divide-x divide-[#33334a]">
      <!-- 🆕 工作区名称 (VSCode 风格) -->
      <button class="flex items-center gap-1 px-2 py-1 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]" title="工作区根目录">
        <HardDrive :size="13" class="text-sky-400" />
        <span class="max-w-[100px] truncate">{{ store.workspaceRoot?.split(/[/\\]/).pop() || 'workspace' }}</span>
      </button>

      <!-- Git 分支 -->
      <button class="flex items-center gap-1 px-2 py-1 hover:bg-white/5 rounded" @click="store.refreshGitStatus()">
        <GitBranch :size="13" :class="[store.gitBranch ? 'text-sky-400' : 'text-[var(--color-statusbar-text)]']" />
        <span class="text-[var(--color-statusbar-text)]">{{ branchLabel }}</span>
        <span v-if="store.gitAhead > 0" class="text-green-400 ml-0.5">↑{{ store.gitAhead }}</span>
        <span v-if="store.gitBehind > 0" class="text-yellow-400 ml-0.5">↓{{ store.gitBehind }}</span>
      </button>

      <!-- 错误/变更 -->
      <span class="flex items-center gap-1 px-2 py-1">
        <XCircle :size="13" class="text-green-400" /><span class="text-[var(--color-statusbar-text)]">0</span>
        <AlertCircle :size="13" class="text-yellow-400 ml-1" /><span class="text-[var(--color-statusbar-text)]">{{ changedLabel }}</span>
      </span>
    </div>

    <div class="flex-1" />

    <!-- 🆕 中右区: 编辑器状态 -->
    <div class="flex items-center divide-x divide-[#33334a]">
      <!-- 光标位置 -->
      <button class="px-2 py-1 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]" :title="selectionText || posText">
        <Braces :size="11" class="inline mr-1 opacity-50" />{{ posText }}
      </button>
      <button v-if="selectionText" class="px-2 py-1 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]">{{ selectionText }}</button>
      <button class="px-2 py-1 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]">空格: {{ store.cursorPosition.indentSize }}</button>
      <button class="px-2 py-1 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]">{{ store.cursorPosition.encoding }}</button>
      <button class="px-2 py-1 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]">{{ store.cursorPosition.eol === '\n' ? 'LF' : 'CRLF' }}</button>
      <button class="px-2 py-1 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]">{{ langDisplay }}</button>
    </div>

    <!-- 🆕 右区: 模型状态 + 通知 + 反馈 -->
    <div class="flex items-center divide-x divide-[#33334a] ml-1">
      <!-- 🆕 模型健康指示器 (VSCode 风格) -->
      <button
        class="flex items-center gap-1.5 px-2 py-1 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]"
        :title="`活跃模型: ${modelLabel} (${modelHealth})`"
        @click="checkModelHealth()"
      >
        <span class="relative inline-flex">
          <Cpu :size="13" :class="modelHealth === 'unavailable' ? 'text-red-400' : 'text-[var(--color-statusbar-text)]'" />
          <span
            class="absolute -bottom-0.5 -right-0.5 w-1.5 h-1.5 rounded-full border border-[var(--statusbar-bg)]"
            :style="{ backgroundColor: healthDotColor }"
          />
        </span>
        <span>{{ modelLabel }}</span>
      </button>

      <!-- 通知 -->
      <button class="relative flex items-center gap-1 px-2 py-1 hover:bg-white/5 rounded">
        <Bell :size="13" class="text-[var(--color-statusbar-text)]" />
        <span
          v-if="notificationCount > 0"
          class="absolute -top-0.5 -right-0.5 min-w-[14px] h-[14px] flex items-center justify-center rounded-full bg-red-500 text-[9px] font-bold text-white px-0.5"
        >{{ notificationCount > 9 ? '9+' : notificationCount }}</span>
      </button>

      <!-- 连接状态 -->
      <button class="flex items-center gap-1 px-2 py-1 hover:bg-white/5 rounded">
        <CheckCircle2 :size="13" class="text-green-400" />
        <span class="text-[var(--color-statusbar-text)] text-[11px]">就绪</span>
      </button>

      <!-- 反馈 -->
      <button class="px-2 py-1 hover:bg-white/5 rounded text-[var(--color-statusbar-text)] opacity-60">
        <span class="hover:opacity-100">👍</span>
      </button>

      <!-- 🆕 主题快速切换 (Session 10) -->
      <button
        class="px-2 py-1 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]"
        :title="`切换主题: ${themeStore.definition.label}`"
        @click="themeStore.cycleTheme()"
      >
        <Sun :size="13" v-if="themeStore.active === 'light'" class="text-yellow-400" />
        <Moon :size="13" v-else-if="themeStore.active === 'dark'" class="text-indigo-300" />
        <span v-else class="text-[10px] font-bold text-green-400">HC</span>
      </button>
    </div>
  </footer>
</template>
