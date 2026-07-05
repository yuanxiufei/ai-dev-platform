<script setup lang="ts">
/**
 * CodeBuddy IDE — Status Bar (VSCode statusbarPart)
 * 精确尺寸: height=22px, font-size=12px, line-height=22px
 * Item padding: 0 10px, hover bg rgba(255,255,255,0.1)
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { useThemeStore } from '@/stores/useThemeStore'
import { useNotificationStore } from '@/stores/useNotificationStore'
import { useSystemStore } from '@/stores/useSystemStore'
import { GitBranch, AlertCircle, CheckCircle2, Bell, XCircle, Cpu, WifiOff, Braces, Sun, Moon, Check, Lock } from 'lucide-vue-next'
import LanguageStatusIndicator from './LanguageStatusIndicator.vue'
import { syncScrollActive, toggleSyncScroll } from '@/composables/useSyncScroll'

const store = useIDEStore()
const themeStore = useThemeStore()
const notifStore = useNotificationStore()
const systemStore = useSystemStore()

const posText = computed(() => `行 ${store.cursorPosition.line}, 列 ${store.cursorPosition.column}`)
const selectionText = computed(() => store.cursorPosition.selectedChars > 0 ? `已选择 ${store.cursorPosition.selectedChars}` : '')
const langDisplay = computed(() => {
  const tab = store.activeTab; if (!tab) return '纯文本'
  const m: Record<string, string> = { typescript:'TypeScript', javascript:'JavaScript', vue:'Vue', python:'Python', json:'JSON', markdown:'Markdown', html:'HTML', css:'CSS', go:'Go', rust:'Rust' }
  return m[tab.language ?? ''] ?? tab.language ?? '纯文本'
})
const branchLabel = computed(() => store.gitBranch || 'main')
const changedLabel = computed(() => String(store.gitChangedFiles || 0))

const activeModel = ref(''); const modelHealth = ref<'healthy'|'degraded'|'unavailable'>('healthy')
const notificationCount = ref(0); const contextMenu = ref<any>(null); const copied = ref<string|null>(null)
const showNotifications = ref(false)
/** Session 42: Language Status indicator clickable */
const showLangMenu = ref(false)

/** 可用语言列表 */
const langOptions = [
  { id: "plaintext", label: "纯文本", icon: "📄" },
  { id: "typescript", label: "TypeScript", icon: "🟦" },
  { id: "javascript", label: "JavaScript", icon: "🟨" },
  { id: "vue", label: "Vue", icon: "🟩" },
  { id: "python", label: "Python", icon: "🐍" },
  { id: "html", label: "HTML", icon: "🔴" },
  { id: "css", label: "CSS", icon: "🟪" },
  { id: "json", label: "JSON", icon: "📋" },
  { id: "markdown", label: "Markdown", icon: "📝" },
  { id: "go", label: "Go", icon: "🔵" },
  { id: "rust", label: "Rust", icon: "🦀" },
]

/** 获取当前语言的 Monaco 功能支持 */
const langFeatures = computed(() => {
  const lang = store.activeTab?.language ?? "plaintext"
  const map: Record<string, { format: boolean; definition: boolean; completion: boolean; refactor: boolean }> = {
    typescript: { format: true, definition: true, completion: true, refactor: true },
    javascript: { format: true, definition: true, completion: true, refactor: true },
    vue: { format: true, definition: true, completion: true, refactor: true },
    python: { format: false, definition: true, completion: true, refactor: false },
    html: { format: true, definition: false, completion: true, refactor: false },
    css: { format: true, definition: false, completion: true, refactor: false },
    json: { format: true, definition: false, completion: true, refactor: false },
    markdown: { format: false, definition: false, completion: true, refactor: false },
    go: { format: true, definition: true, completion: true, refactor: true },
    rust: { format: false, definition: true, completion: true, refactor: false },
  }
  return map[lang] ?? { format: false, definition: false, completion: true, refactor: false }
})

/** 切换当前编辑器的语言 */
function changeLanguage(langId: string): void {
  if (store.activeTab) {
    store.activeTab.language = langId
    // 触发 Monaco 重新设置语言
    const ed = (window as any).__monacoInstances?.[store.activeTab.id]
    if (ed) {
      const model = ed.getModel()
      if (model && (window as any).monaco) {
        (window as any).monaco.editor.setModelLanguage(model, langId)
      }
    }
  }
  showLangMenu.value = false
}

/** 点击其他地方关闭语言菜单 */
function closeLangMenu(e: MouseEvent) {
  if (showLangMenu.value) showLangMenu.value = false
}
onMounted(() => { document.addEventListener("click", closeLangMenu) })
onUnmounted(() => { document.removeEventListener("click", closeLangMenu) })

/** VSCode-style: cycle encoding on click */
const encodings = ['UTF-8', 'UTF-16', 'GBK', 'ISO-8859-1', 'Windows-1252']
const encodingIdx = ref(0)
function cycleEncoding() {
  encodingIdx.value = (encodingIdx.value + 1) % encodings.length
  store.cursorPosition.encoding = encodings[encodingIdx.value]
}

/** VSCode-style: toggle EOL on click */
const eolModes = ['\n', '\r\n']
const eolIdx = ref(0)
function cycleEol() {
  eolIdx.value = (eolIdx.value + 1) % eolModes.length
  store.cursorPosition.eol = eolModes[eolIdx.value]
}

function loadActiveModel() { try { const r = localStorage.getItem('active_model_name'); if (r) activeModel.value = r } catch {} }
loadActiveModel()

let healthTimer: any = null
let systemTimer: any = null
async function checkModelHealth() {
  try { const r = await fetch('/api/v1/system/models/providers'); modelHealth.value = r.ok ? 'healthy' : 'degraded' }
  catch { modelHealth.value = 'unavailable' }
}
onMounted(() => { checkModelHealth(); healthTimer = setInterval(checkModelHealth, 60_000); systemStore.refreshSystemInfo(); systemTimer = setInterval(() => systemStore.refreshSystemInfo(), 30_000); document.addEventListener('click', closeContextMenu) })
onUnmounted(() => { if (healthTimer) clearInterval(healthTimer); if (systemTimer) clearInterval(systemTimer); document.removeEventListener('click', closeContextMenu) })

const healthDotColor = computed(() => modelHealth.value==='healthy'?'var(--color-terminal-green)':modelHealth.value==='degraded'?'var(--color-terminal-yellow)':'var(--color-terminal-red)')
const modelLabel = computed(() => {
  if (!activeModel.value) return '自动'
  return activeModel.value.replace('qwen25-coder-7b','Qwen2.5-Coder-7B').replace('deepseek-r1','DeepSeek-R1').replace('deepseek-v3','DeepSeek-V3').replace('claude-sonnet','Claude-Sonnet').replace('gpt-4o','GPT-4o') || activeModel.value
})
/** System info: memory usage percentage display */
const memLabel = computed(() => {
  const m = systemStore.memoryUsage
  if (!m || m.totalMB <= 0) return ''
  const pct = Math.round((m.usedMB / m.totalMB) * 100)
  return `${pct}%`
})
const memColor = computed(() => {
  const m = systemStore.memoryUsage
  if (!m || m.totalMB <= 0) return 'var(--color-terminal-green)'
  const pct = m.usedMB / m.totalMB
  if (pct > 0.85) return 'var(--color-terminal-red)'
  if (pct > 0.65) return 'var(--color-terminal-yellow)'
  return 'var(--color-terminal-green)'
})

function showContextMenu(e: MouseEvent, items: Array<{label:string;action:()=>void;separator?:boolean}>) {
  e.preventDefault(); e.stopPropagation(); contextMenu.value = { x:e.clientX, y:e.clientY, items }
}
function closeContextMenu() { contextMenu.value = null }
function execMenu(item: any) { item.action(); contextMenu.value = null }
async function copyText(t: string) { try { await navigator.clipboard.writeText(t); copied.value=t; setTimeout(()=>copied.value=null,2000) } catch{} }
function copyPos() { copyText(`${posText.value} · ${langDisplay.value}`) }
function copyModelName() { copyText(modelLabel.value) }

function statusCtx(e: MouseEvent) {
  showContextMenu(e, [
    { label:'切换状态栏可见性', action:()=>{store.layout.statusBarVisible=false} },
    { label:'复制全部信息', action:()=>copyText(`${branchLabel.value} | ${posText.value} | ${langDisplay.value} | ${modelLabel.value}`), separator:true },
  ])
}
</script>

<template>
  <footer class="flex items-center shrink-0 select-none" style="height:var(--statusbar-height); background:var(--color-statusbar-bg); color:var(--color-statusbar-text); font-size:12px; padding:0 6px;"
    @contextmenu="statusCtx">
    <!-- Left -->
    <div class="flex items-center">
      <button class="statusbar-item hover:bg-white/10" style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px" title="工作区 — 点击复制"
        @click="copyText(store.workspaceRoot||'workspace')"
        @contextmenu="showContextMenu($event,[{label:'复制路径',action:()=>copyText(store.workspaceRoot||'')},{label:'在文件管理器中打开',action:()=>{}}])">
        <span style="max-width:100px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">{{ store.workspaceRoot?.split(/[/\\]/).pop() || 'workspace' }}</span>
      </button>
      <button class="statusbar-item hover:bg-white/10" style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px" title="Git分支 — 点击刷新状态+提交记录" @click="store.refreshGitStatus(); store.gitGetLog(10)">
        <GitBranch :size="12" style="flex-shrink:0" />
        <span>{{ branchLabel }}</span>
        <span v-if="store.gitAhead>0" style="color:var(--color-ide-info)">{{ '\u2191'+store.gitAhead }}</span>
        <span v-if="store.gitBehind>0" style="color:var(--color-terminal-yellow)">{{ '\u2193'+store.gitBehind }}</span>
        <!-- Recent commit tooltip -->
        <span v-if="store.commitLog.length>0" style="font-size:10px; opacity:0.6; max-width:120px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap" :title="store.commitLog.slice(0,5).map(c=>`${c.shortHash} ${c.message}`).join('\n')">
          {{ store.commitLog[0].shortHash }}
        </span>
      </button>
      <span style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px">
        <XCircle :size="12" style="color: var(--color-terminal-green)" /><span>0</span>
        <AlertCircle :size="12" style="color: var(--color-terminal-yellow); margin-left:4px" /><span>{{ changedLabel }}</span>
      </span>
    </div>
    <div class="flex-1" />
    <!-- Center-Right: editor status -->
    <div style="display:flex; align-items:center">
      <!-- Session 58: Sync Scroll / Locked Scrolling indicator -->
      <button
        v-if="syncScrollActive"
        class="statusbar-item hover:bg-white/10"
        style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px; color:var(--color-ide-accent)"
        title="已锁定同步滚动 — 点击取消"
        @click="toggleSyncScroll">
        <Lock :size="12" style="flex-shrink:0" />
        <span>锁定滚动</span>
      </button>
      <!-- Session 57: Language Status Indicator -->
      <LanguageStatusIndicator />
      <!-- VSCode: 多光标计数 (Alt+Click / Ctrl+D / Ctrl+Alt+Down) -->
      <button
        v-if="store.cursorPosition.multiCursorCount && store.cursorPosition.multiCursorCount > 1"
        class="statusbar-item hover:bg-white/10"
        style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px"
        title="多光标编辑模式">
        <Braces :size="12" style="opacity:0.7; color: var(--color-ide-accent);" />
        <span>{{ store.cursorPosition.multiCursorCount }} 个游标</span>
      </button>
      <button class="statusbar-item hover:bg-white/10" style="position:relative; display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px" :title="posText+' — 点击复制'" @click="copyPos">
        <Braces :size="12" style="opacity:0.5" />{{ posText }}
        <transition name="fade"><span v-if="copied?.includes(posText)" style="position:absolute; top:-20px; left:50%; transform:translateX(-50%); font-size:11px; background:var(--color-ide-accent); padding-left:6px; padding-right:6px; padding-top:2px; padding-bottom:2px; border-radius:4px; white-space:nowrap; z-index:50"><Check :size="11" style="display:inline; margin-right:2px"/>已复制</span></transition>
      </button>
      <button v-if="selectionText" class="statusbar-item hover:bg-white/10" style="padding-left:10px; padding-right:10px; border-radius:3px">{{ selectionText }}</button>
      <button class="statusbar-item hover:bg-white/10" style="padding-left:10px; padding-right:10px; border-radius:3px" title="缩进">空格: {{ store.cursorPosition.indentSize }}</button>
      <button class="statusbar-item hover:bg-white/10" style="padding-left:10px; padding-right:10px; border-radius:3px" title="编码 — 点击切换" @click="cycleEncoding">{{ store.cursorPosition.encoding }}</button>
      <button class="statusbar-item hover:bg-white/10" style="padding-left:10px; padding-right:10px; border-radius:3px" title="行尾序列 — 点击切换" @click="cycleEol">{{ store.cursorPosition.eol==='\n'?'LF':'CRLF' }}</button>
      <button class="statusbar-item hover:bg-white/10" style="padding-left:10px; padding-right:10px; border-radius:3px; cursor: pointer;" :title="'语言模式: ' + langDisplay + ' — 点击切换'" @click="showLangMenu = !showLangMenu" @click.stop>
        {{ langDisplay }}
        <!-- Session 42: 语言状态弹出菜单 -->
        <div v-if="showLangMenu" class="absolute bottom-full left-0 mb-1 min-w-[200px] py-1 rounded shadow-xl z-50" style="background: var(--color-ide-surface); border: 1px solid var(--color-ide-border);" @click.stop>
          <div class="px-3 py-1.5 text-[10px] font-semibold uppercase" style="color: var(--color-ide-text-dim);">切换语言模式</div>
          <button v-for="lang in langOptions" :key="lang.id"
            :class="['w-full text-left px-3 py-1 text-[11px] hover:bg-white/5 flex items-center gap-2', lang.id === (activeTab?.language ?? 'plaintext') ? 'text-[var(--color-ide-accent)]' : '']"
            :style="{ color: lang.id === (activeTab?.language ?? 'plaintext') ? 'var(--color-ide-accent)' : 'var(--color-ide-text)' }"
            @click="changeLanguage(lang.id)">
            <span class="text-xs">{{ lang.icon }}</span>{{ lang.label }}
          </button>
          <div class="border-t my-1" style="border-color: var(--color-ide-border); opacity: 0.3;" />
          <div class="px-3 py-1 text-[10px]" style="color: var(--color-ide-text-dim);">
            <div>格式化: {{ langFeatures.format ? '✅' : '—' }}</div>
            <div>转到定义: {{ langFeatures.definition ? '✅' : '—' }}</div>
            <div>自动完成: {{ langFeatures.completion ? '✅' : '—' }}</div>
            <div>重构: {{ langFeatures.refactor ? '✅' : '—' }}</div>
            <div class="mt-1 text-[9px] opacity-50">语言功能由 Monaco 内置提供</div>
          </div>
        </div>
      </button>
    </div>
    <!-- Right -->
    <div style="display:flex; align-items:center">
      <button class="statusbar-item hover:bg-white/10" style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px" :title="`模型: ${modelLabel}`" @click="copyModelName">
        <span style="position:relative"><Cpu :size="12" /><span style="position:absolute; bottom:-2px; right:-2px; width:6px; height:6px; border-radius:50%; border:1px solid" :style="{backgroundColor:healthDotColor,borderColor:'var(--color-statusbar-bg)'}" /></span>
        <span>{{ modelLabel }}</span>
      </button>
      <button class="statusbar-item hover:bg-white/10" style="position:relative; padding-left:10px; padding-right:10px; border-radius:3px" title="通知" @click="notifStore.showNotificationPanel=!notifStore.showNotificationPanel"><Bell :size="12" />
        <span v-if="notifStore.notifications.length>0||notifStore.historyCount>0" style="position:absolute; top:-2px; right:-2px; min-width:16px; height:16px; display:flex; align-items:center; justify-content:center; border-radius:50%; background:var(--color-ide-error); font-size:10px; font-weight:bold; padding-left:2px; padding-right:2px">{{ notifStore.notifications.length||notifStore.historyCount }}</span>
      </button>
      <button class="statusbar-item hover:bg-white/10" style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px" title="连接状态" @click="checkModelHealth">
        <CheckCircle2 :size="12" style="color:var(--color-terminal-green)" v-if="modelHealth==='healthy'" />
        <AlertCircle :size="12" style="color:var(--color-terminal-yellow)" v-else-if="modelHealth==='degraded'" />
        <WifiOff :size="12" style="color:var(--color-terminal-red)" v-else />
      </button>
      <!-- System info: CPU + Memory (Tauri-only, hidden when unavailable) -->
      <button v-if="systemStore.available" class="statusbar-item hover:bg-white/10" style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px" title="系统资源" @click="systemStore.refreshSystemInfo()">
        <Cpu :size="12" :style="{ color: memColor }" />
        <span v-if="memLabel" :style="{ color: memColor }">{{ memLabel }}</span>
      </button>
      <button class="statusbar-item hover:bg-white/10" style="padding-left:10px; padding-right:10px; border-radius:3px; opacity:0.6" title="反馈" @mouseenter="($el as HTMLElement).style.opacity='1'" @mouseleave="($el as HTMLElement).style.opacity='0.6'">👍</button>
      <button class="statusbar-item hover:bg-white/10" style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px" :title="`主题: ${themeStore.definition?.labelZh || themeStore.definition?.label || 'Dark'}`" @click="themeStore.cycleTheme()">
        <Sun :size="12" v-if="themeStore.appliedType==='light'" style="color:var(--color-terminal-yellow)"/>
        <Moon :size="12" v-else-if="themeStore.appliedType==='dark'" style="color:var(--color-ide-info)"/>
        <span v-else style="font-size:11px; font-weight:bold; color:var(--color-ide-accent)">HC</span>
        <span style="font-size:12px; max-width:80px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap" class="hidden sm:inline">{{ themeStore.definition?.labelZh || themeStore.definition?.label }}</span>
      </button>
    </div>
  </footer>

  <!-- Context Menu -->
  <Teleport to="body">
    <div v-if="contextMenu" class="fixed z-[500] min-w-[160px] py-1 text-xs"
      :style="{left:contextMenu.x+'px',top:contextMenu.y+'px',background:'var(--color-ide-surface)',border:'1px solid var(--color-ide-border)',borderRadius:'3px',boxShadow:'0 2px 8px rgba(0,0,0,0.36)'}" @click.stop>
      <template v-for="(item,i) in contextMenu.items" :key="i">
        <button class="w-full text-left px-3 py-1 hover:bg-[#094771] text-[var(--color-ide-text)] text-xs flex items-center justify-between" @click="execMenu(item)">
          <span>{{ item.label }}</span><kbd v-if="i===0" class="ml-3">⌘K ⌘S</kbd>
        </button>
        <div v-if="item.separator" class="my-1 border-t border-[var(--color-ide-border)] opacity-40" />
      </template>
    </div>
  </Teleport>
</template>

<style scoped>
.statusbar-item { height: 22px; line-height: 22px; white-space: nowrap; }
</style>
