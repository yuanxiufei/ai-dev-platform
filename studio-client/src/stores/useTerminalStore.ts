// ============================================
// Terminal Store — terminal sessions & output (Session 10: ANSI auto-parse)
// ============================================
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { OutputChannel, TerminalSession } from '@/types/ide'
import { hasAnsi, parseAnsi } from '@/utils/ansi'
import { uid } from './shared'

export const useTerminalStore = defineStore('terminal', () => {
  const terminalSessions = ref<TerminalSession[]>([
    {
      id: uid(),
      title: '终端',
      shellType: 'powershell',
      lines: [
        {
          id: uid(),
          text: '\n  ➜ ~/projects/ai-app',
          type: 'input',
          timestamp: Date.now(),
        },
        {
          id: uid(),
          text: 'npm run dev',
          type: 'input',
          timestamp: Date.now(),
        },
        { id: '', text: '', type: 'output', timestamp: Date.now() },
        {
          id: uid(),
          text: '> ai-app@1.0.0 dev\n> vite',
          type: 'output',
          timestamp: Date.now(),
        },
        {
          id: uid(),
          text: 'VITE v5.0.0 ready in 420 ms',
          type: 'success',
          timestamp: Date.now(),
        },
        {
          id: '',
          text: '➜ Local: http://localhost:5173/\n➜ Network: use --host to expose\n➜ press h + enter to show help',
          type: 'output',
          timestamp: Date.now(),
        },
      ],
      active: true,
      cwd: '~/projects/ai-app',
    },
  ])

  const activeTerminalId = computed(() => terminalSessions.value.find((t) => t.active)?.id ?? null)

  function addTerminalLine(
    text: string,
    type: TerminalSession['lines'][0]['type'] = 'output',
  ): void {
    const term = terminalSessions.value.find((t) => t.active)
    if (!term) return
    const line: TerminalSession['lines'][0] = {
      id: uid(),
      text,
      type,
      timestamp: Date.now(),
    }
    // Session 10: auto-detect ANSI and pre-parse segments
    if (hasAnsi(text)) {
      line.segments = parseAnsi(text)
    }
    term.lines.push(line)
  }

  const outputChannels = ref<OutputChannel[]>([
    { id: 'output', name: '输出', visible: true, lines: [] },
    { id: 'problems', name: '问题', visible: false, lines: [] },
    { id: 'debug-console', name: '调试控制台', visible: false, lines: [] },
  ])
  const activeOutputChannel = ref('output')

  function addOutputLine(msg: string, channelId: string = 'output'): void {
    const ch = outputChannels.value.find((c) => c.id === channelId)
    if (ch) ch.lines.push(msg)
  }

  return {
    terminalSessions,
    activeTerminalId,
    addTerminalLine,
    outputChannels,
    activeOutputChannel,
    addOutputLine,
  }
})
