<template>
  <Teleport to="body">
    <Transition name="command-palette">
      <div v-if="visible" class="fixed inset-0 z-[9999] flex items-start justify-center pt-20" @click.self="close">
        <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" />
        <div ref="panelRef" class="relative w-full max-w-xl bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded-lg shadow-2xl shadow-black/50 overflow-hidden" @click.stop>
          <div class="flex items-center px-4 py-3 border-b border-[var(--color-ide-border)]">
            <Search :size="16" class="text-[var(--color-ide-text-dim)] shrink-0 mr-3" />
            <input ref="inputRef" v-model="q" type="text" placeholder="输入命令或搜索..." class="flex-1 bg-transparent text-sm text-[var(--color-ide-text)] outline-none placeholder:text-[var(--color-ide-text-dim)] font-mono" @input="si(); selectedIdx=0" @keydown.down.prevent="sn()" @keydown.up.prevent="sp()" @keydown.enter="ex()" @keydown.escape="close"/>
            <kbd class="hidden sm:inline-flex items-center gap-1 text-xs text-[var(--color-ide-text-dim)] bg-[var(--color-ide-bg-tertiary)] px-1.5 py-0.5 rounded border border-[var(--color-ide-border)]">ESC</kbd>
          </div>
          <div v-if="cats.length>1 && !q" class="flex items-center gap-1 px-4 py-2 overflow-x-auto border-b border-[var(--color-ide-border)]">
            <button v-for="c in cats" :key="c" :class="['px-2.5 py-1 text-xs rounded-md whitespace-nowrap transition-colors', ac===c||(!ac&&c==='全部')?'bg-[var(--color-ide-accent)] text-white':'text-[var(--color-ide-text-secondary)] hover:bg-[var(--color-ide-hover)]']" @click="ac=c==='全部'?null:c;selectedIdx=0">{{ c }}</button>
          </div>
          <div ref="resultsRef" class="max-h-[400px] overflow-y-auto py-1">
            <div v-if="fr.length===0" class="px-4 py-8 text-center"><Inbox :size="32" class="mx-auto mb-2 opacity-30 text-[var(--color-ide-text-dim)]"/><p class="text-sm text-[var(--color-ide-text-dim)]">{{ q ? `没有找到 "${q}"` : '输入搜索关键词...' }}</p></div>
            <button v-for="(item,idx) in fr" :key="item.id+item.category" :ref="(el:any)=>ir(idx,el)"
              :class="['w-full flex items-center px-4 py-2.5 transition-colors text-left group', selectedIdx===idx?'bg-[var(--color-ide-selection)]':'hover:bg-[var(--color-ide-hover)]']"
              @mouseenter="selectedIdx=idx" @click="exec(item)">
              <div class="w-8 h-8 mr-3 flex items-center justify-center rounded bg-[var(--color-ide-bg-tertiary)] shrink-0"><component :is="gi(item.icon)" :size="14" class="text-[var(--color-ide-text-secondary)]"/></div>
              <div class="flex-1 min-w-0"><div class="flex items-center gap-2"><span class="text-sm text-[var(--color-ide-text)]">{{ item.title }}</span><span v-if="item.score&&item.score>50&&q" class="text-[10px] px-1.5 py-0.5 rounded-full bg-[var(--color-ide-accent)]/10 text-[var(--color-ide-accent)]">{{ Math.round(item.score) }}%</span></div><span class="text-xs text-[var(--color-ide-text-dim)] truncate block mt-0.5">{{ item.category }} · {{ item.id }}</span></div>
              <kbd v-if="item.key" class="hidden sm:inline-flex items-center gap-0.5 text-[11px] text-[var(--color-ide-text-dim)] bg-[var(--color-ide-bg-tertiary)] px-1.5 py-0.5 rounded border border-[var(--color-ide-border)] ml-2 shrink-0">{{ fk(item.key) }}</kbd>
            </button>
            <div v-if="fr.length>0" class="sticky bottom-0 px-4 py-2 bg-[var(--color-ide-surface)] border-t border-[var(--color-ide-border)] text-xs text-[var(--color-ide-text-dim)] flex justify-between"><span>{{ fr.length }} 个命令</span><span>↑↓ 选择 · Enter 执行</span></div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useShortcuts, type CommandPaletteItem } from '@/composables/useShortcuts'
import { usePlugins } from '@/composables/usePlugins'
import { Search, Inbox, FilePlus, FolderOpen, Save, Undo2, Redo, Copy, ClipboardPaste, PanelLeftClose, PanelBottomClose, ZoomIn, ZoomOut, FileSearch, Terminal, MessageSquare, Settings, GitBranch, Code, Sparkles, Play, Square, Pause, ChevronsRight, ChevronRight, ChevronsLeft, SkipForward, CircleDot, Variable, Eye, Layers, Lightbulb, Wand2, TestTube2, Bug, Zap, FileText, Plus, Download, CheckCircle2, ArrowUpFromLine, ArrowDownToLine, GitBranchPlus, GitCommit, RotateCcw } from 'lucide-vue-next'

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<{ 'update:visible': [val: boolean]; 'execute': [cmdId: string] }>()
const { getFiltered, getCategories } = useShortcuts()
const { allCommands } = usePlugins()
const q = ref(''), selectedIdx = ref(0), ac = ref<string | null>(null)
const inputRef = ref<HTMLInputElement>(), panelRef = ref<HTMLDivElement>(), resultsRef = ref<HTMLDivElement>()
const irm = new Map<number, HTMLElement>()

const cats = computed(() => ['全部', ...getCategories()])
const fr = computed<CommandPaletteItem[]>(() => {
  const sc = getFiltered(q.value, ac.value)
  const pc: CommandPaletteItem[] = (allCommands.value||[]).map(c=>({id:c.id,title:c.title,category:c.category||'插件',key:'',icon:c.icon||'Puzzle',score:0,keywords:`${c.title} ${c.category}`.toLowerCase()}))
  let fp = pc
  if (q.value) { const ql=q.value.toLowerCase(); fp=pc.filter(p=>p.keywords.includes(ql)).map(p=>({...p,score:p.keywords.includes(ql)?80:40})) }
  return [...sc,...fp]
})

function close() { emit('update:visible',false) }; function si() { selectedIdx.value=0 }
function sn() { if(fr.value.length) { selectedIdx=(selectedIdx.value+1)%fr.value.length; ss() } }
function sp() { if(fr.value.length) { selectedIdx=selectedIdx.value<=0?fr.value.length-1:selectedIdx.value-1; ss() } }
function ex() { if(fr.value[selectedIdx.value]) exec(fr.value[selectedIdx.value]) }
function exec(item:CommandPaletteItem) { emit('execute',item.id); close() }
function ss() { nextTick(()=>{ const e=irm.get(selectedIdx.value); e?.scrollIntoView({block:'nearest',behavior:'smooth'}) }) }
function ir(i:number, el:any) { el ? irm.set(i,el) : irm.delete(i) }

function gi(icon?:string): any {
  const m:{[k:string]:any}={FilePlus,FolderOpen,Save,Undo2,Redo,Copy,ClipboardPaste,PanelLeftClose,PanelBottomClose,ZoomIn,ZoomOut,FileSearch,Terminal,MessageSquare,Settings,GitBranch,Code,Sparkles,Play,Square,Pause,ChevronsRight,ChevronRight,ChevronsLeft,SkipForward,CircleDot,Variable,Eye,Layers,Lightbulb,Wand2,TestTube2,Bug,Zap,FileText,Plus,Download,CheckCircle2,ArrowUpFromLine,ArrowDownToLine,GitBranchPlus,GitCommit,RotateCcw}
  return m[icon??'']||Search
}
function fk(k:string): string { return k.replace(/Ctrl/g,'\u2318').replace(/Shift/g,'\u21E7').replace(/Alt/g,'\u2325') }

watch(() => props.visible, (val: boolean) => { if(val) { q.value = ''; selectedIdx.value = 0; nextTick(() => inputRef.value?.focus()) } })
</script>

<style scoped>.command-palette-enter-active,.command-palette-leave-active{transition:all .15s ease}.command-palette-enter-from,.command-palette-leave-to{opacity:0;transform:translateY(-10px)}</style>
