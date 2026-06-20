<script setup lang="ts">/** CodeBuddy IDE — Bottom Status Bar */
import { computed } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { GitBranch, AlertCircle, CheckCircle2, Bell, XCircle } from 'lucide-vue-next'

const store = useIDEStore()
const posText = computed(() => `行 ${store.cursorPosition.line}, 列 ${store.cursorPosition.column}`)
const selectionText = computed(() => store.cursorPosition.selectedChars > 0 ? `已选择 ${store.cursorPosition.selectedChars} 字符` : '')
const langDisplay = computed(() => {
  const tab = store.activeTab
  if (!tab) return '纯文本'
  const map: Record<string, string> = { typescript:'TypeScript', javascript:'JavaScript', typescriptreact:'TypeScript React', python:'Python', json:'JSON', markdown:'Markdown', html:'HTML', css:'CSS', shell:'Shell', yaml:'YAML', go:'Go' }
  return map[tab.language ?? ''] ?? tab.language ?? '纯文本'
})
</script>

<template>
  <footer class="h-[var(--statusbar-height)] bg-[var(--color-statusbar-bg)] border-t border-[var(--color-ide-border)] flex items-center px-1 shrink-0 select-none text-[11px]">
    <div class="flex items-center divide-x divide-[#33334a]">
      <button class="flex items-center gap-1 px-2 py-0.5 hover:bg-white/5 rounded"><GitBranch :size="13" class="text-[var(--color-statusbar-text)]" /><span class="text-[var(--color-statusbar-text)]">main</span></button>
      <button class="flex items-center gap-1 px-2 py-0.5 hover:bg-white/5 rounded"><XCircle :size="13" class="text-green-400" /><span class="text-[var(--color-statusbar-text)]">0</span><AlertCircle :size="13" class="text-yellow-400 ml-1" /><span class="text-[var(--color-statusbar-text)]">0</span></button>
      <button class="px-2 py-0.5 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]" :title="selectionText || posText">{{ posText }}</button>
      <button v-if="selectionText" class="px-2 py-0.5 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]">{{ selectionText }}</button>
      <button class="px-2 py-0.5 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]">空格: {{ store.cursorPosition.indentSize }}</button>
      <button class="px-2 py-0.5 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]">{{ store.cursorPosition.encoding }}</button>
      <button class="px-2 py-0.5 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]">{{ store.cursorPosition.eol === '\n' ? 'LF' : 'CRLF' }}</button>
      <button class="px-2 py-0.5 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]">{{ langDisplay }}</button>
    </div>
    <div class="flex-1" />
    <div class="flex items-center divide-x divide-[#33334a]">
      <button class="flex items-center gap-1 px-2 py-0.5 hover:bg-white/5 rounded"><Bell :size="13" class="text-[var(--color-statusbar-text)]" /></button>
      <button class="flex items-center gap-1 px-2 py-0.5 hover:bg-white/5 rounded"><CheckCircle2 :size="13" class="text-green-400" /><span class="text-[var(--color-statusbar-text)] text-[10px]">连接就绪</span></button>
      <button class="px-2 py-0.5 hover:bg-white/5 rounded text-[var(--color-statusbar-text)]"><span class="mr-1">👍</span><span class="mr-1">👎</span></button>
    </div>
  </footer>
</template>
