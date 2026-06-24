<script setup lang="ts">/** IDE — Terminal Emulator (Figma design) */
import { ref, computed, nextTick } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'

const store = useIDEStore()
const inputRef = ref<HTMLInputElement | null>(null)
const scrollRef = ref<HTMLDivElement | null>(null)
const currentInput = ref('')
const activeTerminal = computed(() => store.terminalSessions.find(t => t.id === store.activeTerminalId))

function sb(): void { nextTick(() => { if (scrollRef.value) scrollRef.value.scrollTop = scrollRef.value.scrollHeight }) }

function execute(): void {
  const cmd = currentInput.value.trim(); if (!cmd) return
  store.addTerminalLine(`\n  ➜ ${activeTerminal?.cwd ?? '~/projects/ai-app'}`, 'input')
  store.addTerminalLine(cmd, 'input')
  setTimeout(() => {
    if (cmd.startsWith('echo ')) store.addTerminalLine(cmd.slice(5), 'output')
    else if (cmd === 'cls' || cmd === 'clear') { const t = store.terminalSessions.find(t => t.active); if (t) t.lines = []; return }
    else if (cmd === 'pwd') store.addTerminalLine(activeTerminal?.cwd ?? '~/projects/ai-app', 'output')
    else if (cmd === 'ls' || cmd === 'dir') store.addTerminalLine('\n  drwxr-xr-x   ai_models/\n  drwxr-xr-x   backend/\n  -rw-r--r--  package.json\n  -rw-r--r--  README.md', 'output')
    else if (cmd === 'git status') store.addTerminalLine('On branch main\nChanges not staged:\n  modified: App.vue', 'info')
    else if (cmd.startsWith('pnpm ') || cmd.startsWith('npm ') || cmd.startsWith('npm run')) {
      store.addTerminalLine('', 'output')
      store.addTerminalLine('> ai-app@1.0.0 dev', 'info')
      store.addTerminalLine('> vite', 'info')
      let step = 0; const iv = setInterval(() => {
        step++; const s = ['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏'][step % 10]
        store.terminalSessions.find(t => t.active)?.lines.pop()
        store.addTerminalLine(`  ${s} VITE ready in ${420 + step * 10} ms`, 'info'); sb()
        if (step > 5) { clearInterval(iv)
          store.addTerminalLine('', 'output')
          store.addTerminalLine('  ➜ Local: http://localhost:5173/', 'success')
          store.addTerminalLine('  ➜ Network: use --host to expose', 'output')
          sb()
        }
      }, 200)
    } else store.addTerminalLine(`${cmd}: command not found`, 'error')
    store.addTerminalLine('', 'output'); sb()
  }, 150); currentInput.value = ''
}
</script>

<template>
  <div class="h-full flex flex-col font-mono text-[12px]" style="background:var(--color-terminal-bg);">
    <!-- Header (Figma: #262A35 bg) -->
    <div class="flex items-center justify-between px-4 h-9 shrink-0" style="background:#262A35; border-bottom:1px solid var(--color-ide-border);">
      <div class="flex gap-0">
        <button
          v-for="term in store.terminalSessions" :key="term.id"
          class="flex items-center gap-1 px-3 py-1 rounded text-[12px] transition-colors"
          :class="term.active ? 'text-white' : 'hover:bg-white/5'"
          style="font-family:'WenQuanYi Zen Hei',sans-serif; font-weight:500;"
          @click="store.terminalSessions.forEach(t=>t.active=t.id===term.id);sb();nextTick(()=>inputRef.value?.focus())"
        >{{ term.title }}</button>
      </div>
      <div class="flex items-center gap-2">
        <button class="p-1 rounded hover:bg-white/5 transition-colors" style="color:#908FA0;" title="清除"><svg width="9" height="9" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M11 3L3 11M3 3l8 8"/></svg></button>
        <button class="p-1 rounded hover:bg-white/5 transition-colors" style="color:#908FA0;" title="分割"><svg width="11" height="12" viewBox="0 0 16 18" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="10" height="12" rx="1"/><path d="M8 3v12"/></svg></button>
        <button class="p-1 rounded hover:bg-white/5 transition-colors" style="color:#908FA0;" title="关闭终端"><svg width="9" height="9" viewBox="0 0 14 14" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M11 3L3 11M3 3l8 8"/></svg></button>
      </div>
    </div>

    <!-- Output Area -->
    <div ref="scrollRef" class="flex-1 overflow-y-auto p-3 space-y-0">
      <template v-if="activeTerminal">
        <div
          v-for="line in activeTerminal.lines" :key="line.id"
          class="whitespace-pre-wrap break-all text-xs leading-relaxed"
          :style="{ color: line.type === 'success' ? '#10B981' : line.type === 'error' ? '#E06C75' : line.type === 'info' ? '#FBBF24' : line.type === 'input' ? '#60A5FA' : '#DFE2F1' }"
        >{{ line.text }}</div>
      </template>

      <!-- Input Prompt (Figma style: ➜ path) -->
      <div class="flex items-center pt-1">
        <span class="mr-2 shrink-0" style="color:#C0C1FF;">➜</span>
        <span class="shrink-0 mr-2 text-xs" style="font-family:'JetBrains Mono',monospace;color:#908FA0;">{{ activeTerminal?.cwd ?? '~/projects/ai-app' }}</span>
        <input
          ref="inputRef" v-model="currentInput" type="text"
          class="flex-1 bg-transparent outline-none text-xs"
          style="caret-color:#C0C1FF;color:#DFE2F1;font-family:'JetBrains Mono',monospace;"
          spellcheck="false" autocomplete="off" autofocus
          @keydown.enter="execute" @focus="sb"
        />
      </div>
    </div>
  </div>
</template>
