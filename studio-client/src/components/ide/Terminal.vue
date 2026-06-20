<script setup lang="ts">/** IDE — Terminal Emulator */
import { ref, computed, nextTick, onMounted } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { Plus, Trash2, Play, RotateCcw } from 'lucide-vue-next'

const store = useIDEStore(); const inputRef = ref<HTMLInputElement | null>(null); const scrollRef = ref<HTMLDivElement | null>(null)
const currentInput = ref('')
const activeTerminal = computed(() => store.terminalSessions.find(t => t.id === store.activeTerminalId))

function sb(): void { nextTick(() => { if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight }) }

function execute(): void {
  const cmd = currentInput.value.trim(); if (!cmd) return
  store.addTerminalLine(`\nPS D:\\code\\ai-fullstack-platform> ${cmd}`, 'input')
  setTimeout(() => {
    if (cmd.startsWith('echo ')) store.addTerminalLine(cmd.slice(5), 'output')
    else if (cmd === 'cls' || cmd === 'clear') { const t = store.terminalSessions.find(t => t.active); if (t) t.lines = []; return }
    else if (cmd === 'pwd') store.addTerminalLine(`D:\\code\\ai-fullstack-platform`, 'output')
    else if (cmd === 'ls' || cmd === 'dir') store.addTerminalLine('\n    Mode                 LastWriteTime         Length Name\n----                 -------------         ------ ----\nd-----        2026/6/20     10:30                ai_models\nd-----        2026/6/20     10:15                backend\n...', 'output')
    else if (cmd === 'git status') store.addTerminalLine('On branch main\nYour branch is up to date.\n\nChanges not staged for commit:\n  modified:   backend/app/api/main.py', 'info')
    else if (cmd.startsWith('pnpm ') || cmd.startsWith('npm ')) {
      store.addTerminalLine('', 'output'); store.addTerminalLine('  ⠋ 正在解析依赖...', 'info')
      let step = 0; const iv = setInterval(() => {
        step++; const s = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏'][step % 10]
        store.terminalSessions.find(t => t.active)?.lines.pop(); store.addTerminalLine(`  ${s} ${['下载依赖','解析元数据','链接包','构建'][Math.floor(step/2)%4]}...`, 'info'); sb()
        if (step > 8) { clearInterval(iv); store.addTerminalLine('\n✓ 完成，耗时 3.2s', 'success') }; sb()
      }, 300)
    } else store.addTerminalLine(`${cmd}: command not found`, 'error')
    store.addTerminalLine('', 'output'); sb()
  }, 150); currentInput.value = ''
}
function createNew(): void {
  store.terminalSessions.forEach(t => t.active = false)
  store.terminalSessions.push({ id:`t_${Date.now()}`, title:`终端 ${store.terminalSessions.length+1}`, shellType:'powershell' as const, lines:[{id:`l_${Date.now()}`,text:'Windows PowerShell',type:'info',timestamp:Date.now()}], active:true, cwd:'D:\\code\\ai-fullstack-platform' }); nextTick(() => inputRef.value?.focus())
}
onMounted(() => sb())
</script>

<template>
  <div class="h-full flex flex-col bg-[var(--color-terminal-bg)] font-mono text-[12px]">
    <div class="h-7 flex items-center justify-between px-2 border-b border-[var(--color-ide-border)] bg-[var(--color-ide-surface)] shrink-0">
      <div class="flex gap-0.5">
        <button v-for="term in store.terminalSessions" :key="term.id" class="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] transition-colors"
          :class="term.active ? 'bg-[var(--color-terminal-bg)] text-[var(--color-terminal-fg)]' : 'hover:bg-white/5 text-[var(--color-ide-text-dim)]'"
          @click="store.terminalSessions.forEach(t=>t.active=t.id===term.id);sb();nextTick(()=>inputRef.value?.focus())"><Play :size="10" />{{ term.title }}</button>
        <button class="p-0.5 rounded hover:bg-white/5 text-[var(--color-ide-text-dim)]" title="新建终端" @click="createNew"><Plus :size="14" /></button>
      </div>
      <div class="flex items-center gap-0.5">
        <button class="p-0.5 rounded hover:bg-white/5 text-[var(--color-ide-text-dim)]" @click="()=>{const t=store.terminalSessions.find(t=>t.active);if(t)t.lines=[]}"><RotateCcw :size="12" /></button>
        <button class="p-0.5 rounded hover:bg-white/5 text-[var(--color-ide-text-dim)]" @click="()=>{const i=store.terminalSessions.findIndex(t=>t.active);if(i>0){store.terminalSessions.splice(i,1);store.terminalSessions[store.terminalSessions.length-1].active=true}}"><Trash2 :size="12}]" /></button>
      </div>
    </div>
    <div ref="scrollRef" class="flex-1 overflow-y-auto p-2 space-y-0.5">
      <template v-if="activeTerminal">
        <div v-for="line in activeTerminal.lines" :key="line.id" class="whitespace-pre-wrap break-all"
          :class="{ 'text-[var(--color-terminal-fg)]':['output','input'].includes(line.type), 'text-[var(--color-terminal-red)]':line.type==='error', 'text-[var(--color-terminal-green)]':line.type==='success', 'text-[var(--color-terminal-yellow)]':line.type==='info', 'text-[var(--color-terminal-blue)]':line.type==='input' }">{{ line.text }}</div>
      </template>
      <div class="flex items-center text-[var(--color-terminal-fg)] pt-1">
        <span class="text-[var(--color-terminal-yellow)] mr-2 shrink-0">PS&gt;</span>
        <input ref="inputRef" v-model="currentInput" type="text" class="flex-1 bg-transparent outline-none text-[var(--color-terminal-fg)] caret-white" spellcheck="false" autocomplete="off" autofocus @keydown.enter="execute" @focus="sb"/>
      </div>
    </div>
  </div>
</template>
