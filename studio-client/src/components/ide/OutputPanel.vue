<script setup lang="ts">/** IDE — Output Panel Viewer */
import { computed, ref, nextTick } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { Filter, X, AlertTriangle, Error, Info } from 'lucide-vue-next'

const store = useIDEStore(); const os = ref<HTMLDivElement | null>(null)
const ac = computed(() => store.outputChannels.find(c => c.id === store.activeOutputChannel))
function setChannel(id: string): void { store.activeOutputChannel = id; store.outputChannels.forEach(c => c.visible = c.id === id); nextTick(() => { if (os.value) os.value.scrollTop = 99999 }) }
function clear(): void { if (ac.value) ac.value.lines = [] }
const icons: Record<string, any> = { output: Info, problems: AlertTriangle, 'debug-console': Error }
</script>

<template>
  <div class="h-full flex flex-col bg-[var(--color-ide-bg)] text-[12px]">
    <div class="h-7 flex items-center justify-between px-2 border-b border-[var(--color-ide-border)] shrink-0">
      <div class="flex gap-0.5">
        <button v-for="ch in store.outputChannels" :key="ch.id" class="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] transition-colors"
          :class="ch.id===store.activeOutputChannel ? 'bg-[var(--color-ide-surface-active)] text-[var(--color-ide-text)]' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]'" @click="setChannel(ch.id)">
          <component :is="icons[ch.id]??Info" :size="12" />{{ ch.name }}
        </button>
      </div>
      <button class="p-0.5 rounded hover:bg-white/5 text-[var(--color-ide-text-dim)]" title="清除输出" @click="clear"><X :size="12" /></button>
    </div>
    <div ref="os" class="flex-1 overflow-y-auto p-2 font-mono text-[11px] space-y-0.5">
      <div v-if="ac" v-for="(line,i) in ac.lines" :key="i" class="whitespace-pre-wrap break-all text-[var(--color-ide-text-dim)]">{{ line }}</div>
      <div v-else class="text-center text-[var(--color-ide-text-dim)] mt-8">选择一个通道查看输出</div>
    </div>
  </div>
</template>
