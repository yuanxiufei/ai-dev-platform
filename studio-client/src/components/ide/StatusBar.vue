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
import { GitBranch, AlertCircle, CheckCircle2, Bell, XCircle, Cpu, WifiOff, Braces, Sun, Moon, Check } from 'lucide-vue-next'

const store = useIDEStore()
const themeStore = useThemeStore()
const notifStore = useNotificationStore()

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
async function checkModelHealth() {
  try { const r = await fetch('/api/v1/system/models/providers'); modelHealth.value = r.ok ? 'healthy' : 'degraded' }
  catch { modelHealth.value = 'unavailable' }
}
onMounted(() => { checkModelHealth(); healthTimer = setInterval(checkModelHealth, 60_000); document.addEventListener('click', closeContextMenu) })
onUnmounted(() => { if (healthTimer) clearInterval(healthTimer); document.removeEventListener('click', closeContextMenu) })

const healthDotColor = computed(() => modelHealth.value==='healthy'?'#4EC9B0':modelHealth.value==='degraded'?'#CCA700':'#F48771')
const modelLabel = computed(() => {
  if (!activeModel.value) return '自动'
  return activeModel.value.replace('qwen25-coder-7b','Qwen2.5-Coder-7B').replace('deepseek-r1','DeepSeek-R1').replace('deepseek-v3','DeepSeek-V3').replace('claude-sonnet','Claude-Sonnet').replace('gpt-4o','GPT-4o') || activeModel.value
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
  <footer class="flex items-center shrink-0 select-none" style="height:var(--statusbar-height); background:var(--color-statusbar-bg); color:var(--color-statusbar-text); font-size:14px; padding:0 6px;"
    @contextmenu="statusCtx">
    <!-- Left -->
    <div class="flex items-center">
      <button class="statusbar-item hover:bg-white/10" style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px" title="工作区 — 点击复制"
        @click="copyText(store.workspaceRoot||'workspace')"
        @contextmenu="showContextMenu($event,[{label:'复制路径',action:()=>copyText(store.workspaceRoot||'')},{label:'在文件管理器中打开',action:()=>{}}])">
        <span style="max-width:100px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">{{ store.workspaceRoot?.split(/[/\\]/).pop() || 'workspace' }}</span>
      </button>
      <button class="statusbar-item hover:bg-white/10" style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px" title="Git分支" @click="store.refreshGitStatus()">
        <GitBranch :size="14" style="flex-shrink:0" />
        <span>{{ branchLabel }}</span>
        <span v-if="store.gitAhead>0" style="color:#75BEFF">{{ '\u2191'+store.gitAhead }}</span>
        <span v-if="store.gitBehind>0" style="color:#FBBF24">{{ '\u2193'+store.gitBehind }}</span>
      </button>
      <span style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px">
        <XCircle :size="14" style="color:#4EC9B0" /><span>0</span>
        <AlertCircle :size="14" style="color:#CCA700; margin-left:4px" /><span>{{ changedLabel }}</span>
      </span>
    </div>
    <div class="flex-1" />
    <!-- Center-Right: editor status -->
    <div style="display:flex; align-items:center">
      <button class="statusbar-item hover:bg-white/10" style="position:relative; display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px" :title="posText+' — 点击复制'" @click="copyPos">
        <Braces :size="14" style="opacity:0.5" />{{ posText }}
        <transition name="fade"><span v-if="copied?.includes(posText)" style="position:absolute; top:-20px; left:50%; transform:translateX(-50%); font-size:11px; background:var(--color-ide-accent); padding-left:6px; padding-right:6px; padding-top:2px; padding-bottom:2px; border-radius:4px; white-space:nowrap; z-index:50"><Check :size="11" style="display:inline; margin-right:2px"/>已复制</span></transition>
      </button>
      <button v-if="selectionText" class="statusbar-item hover:bg-white/10" style="padding-left:10px; padding-right:10px; border-radius:3px">{{ selectionText }}</button>
      <button class="statusbar-item hover:bg-white/10" style="padding-left:10px; padding-right:10px; border-radius:3px" title="缩进">空格: {{ store.cursorPosition.indentSize }}</button>
      <button class="statusbar-item hover:bg-white/10" style="padding-left:10px; padding-right:10px; border-radius:3px" title="编码 — 点击切换" @click="cycleEncoding">{{ store.cursorPosition.encoding }}</button>
      <button class="statusbar-item hover:bg-white/10" style="padding-left:10px; padding-right:10px; border-radius:3px" title="行尾序列 — 点击切换" @click="cycleEol">{{ store.cursorPosition.eol==='\n'?'LF':'CRLF' }}</button>
      <button class="statusbar-item hover:bg-white/10" style="padding-left:10px; padding-right:10px; border-radius:3px" :title="langDisplay" @click="copyText(langDisplay)">{{ langDisplay }}</button>
    </div>
    <!-- Right -->
    <div style="display:flex; align-items:center">
      <button class="statusbar-item hover:bg-white/10" style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px" :title="`模型: ${modelLabel}`" @click="copyModelName">
        <span style="position:relative"><Cpu :size="14" /><span style="position:absolute; bottom:-2px; right:-2px; width:6px; height:6px; border-radius:50%; border:1px solid" :style="{backgroundColor:healthDotColor,borderColor:'var(--color-statusbar-bg)'}" /></span>
        <span>{{ modelLabel }}</span>
      </button>
      <button class="statusbar-item hover:bg-white/10" style="position:relative; padding-left:10px; padding-right:10px; border-radius:3px" title="通知" @click="notifStore.showNotificationPanel=!notifStore.showNotificationPanel"><Bell :size="14" />
        <span v-if="notifStore.notifications.length>0||notifStore.historyCount>0" style="position:absolute; top:-2px; right:-2px; min-width:16px; height:16px; display:flex; align-items:center; justify-content:center; border-radius:50%; background:#EF4444; font-size:10px; font-weight:bold; padding-left:2px; padding-right:2px">{{ notifStore.notifications.length||notifStore.historyCount }}</span>
      </button>
      <button class="statusbar-item hover:bg-white/10" style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px" title="连接状态" @click="checkModelHealth">
        <CheckCircle2 :size="14" style="color:#4EC9B0" v-if="modelHealth==='healthy'" />
        <AlertCircle :size="14" style="color:#CCA700" v-else-if="modelHealth==='degraded'" />
        <WifiOff :size="14" style="color:#F48771" v-else />
      </button>
      <button class="statusbar-item hover:bg-white/10" style="padding-left:10px; padding-right:10px; border-radius:3px; opacity:0.6" title="反馈" @mouseenter="($el as HTMLElement).style.opacity='1'" @mouseleave="($el as HTMLElement).style.opacity='0.6'">👍</button>
      <button class="statusbar-item hover:bg-white/10" style="display:flex; align-items:center; gap:4px; padding-left:10px; padding-right:10px; border-radius:3px" :title="`主题: ${themeStore.definition?.labelZh || themeStore.definition?.label || 'Dark'}`" @click="themeStore.cycleTheme()">
        <Sun :size="14" v-if="themeStore.appliedType==='light'" style="color:#FBBF24"/>
        <Moon :size="14" v-else-if="themeStore.appliedType==='dark'" style="color:#75BEFF"/>
        <span v-else style="font-size:11px; font-weight:bold; color:#1AEBFF">HC</span>
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
.statusbar-item { height: 28px; line-height: 28px; white-space: nowrap; } /* was 26px */
</style>
