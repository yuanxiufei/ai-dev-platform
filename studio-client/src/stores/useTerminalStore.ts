// ============================================
// Terminal Store — real Tauri shell integration
// ============================================
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import type { OutputChannel, TerminalSession } from '@/types/ide'
import { hasAnsi, parseAnsi } from '@/utils/ansi'
import { isTauriEnv, uid } from './shared'
import { useFileTreeStore } from './useFileTreeStore'

export const useTerminalStore = defineStore('terminal', () => {
  const terminalSessions = ref<TerminalSession[]>([])
  const activeTerminalId = computed(() => terminalSessions.value.find((t) => t.active)?.id ?? null)

  let _unlisteners: (() => void)[] = []

  /** Register Tauri terminal events (once) */
  async function _ensureTauriEvents(): Promise<void> {
    if (_unlisteners.length > 0) return
    if (!isTauriEnv()) return
    const { listen } = await import('@tauri-apps/api/event')
    _unlisteners.push(
      await listen<TerminalTauriOutput>('terminal-output', (event) => {
        const { pid, data, isError } = event.payload
        const term = terminalSessions.value.find(t => t.processId === pid)
        if (!term) return
        const lineType = isError ? 'error' : 'output'
        _pushLine(term, data, lineType)
      }),
      await listen<{ pid: number }>('terminal-exit', (event) => {
        const term = terminalSessions.value.find(t => t.processId === event.payload.pid)
        if (term) {
          _pushLine(term, '\n  ➜ 进程已退出\r\n', 'info')
          term.processId = 0
        }
      }),
    )
  }

  function _pushLine(term: TerminalSession, text: string, type: TerminalSession['lines'][0]['type']): void {
    const line: TerminalSession['lines'][0] = { id: uid(), text, type, timestamp: Date.now() }
    if (hasAnsi(text)) line.segments = parseAnsi(text)
    term.lines.push(line)
  }

  /** Create a real Tauri terminal */
  async function createTerminal(
    shellType: TerminalSession['shellType'] = 'powershell',
  ): Promise<string> {
    await _ensureTauriEvents()

    // Deactivate all
    terminalSessions.value.forEach(t => (t.active = false))

    const id = uid()
    const cwd = useFileTreeStore().workspaceRoot || '.'

    if (isTauriEnv()) {
      try {
        const { invoke } = await import('@tauri-apps/api/core')
        const info: any = await invoke('spawn_shell', {
          config: { shell: shellType === 'bash' ? 'bash' : 'powershell.exe', cwd },
        })
        const term: TerminalSession = {
          id,
          title: `终端 (${terminalSessions.value.length + 1})`,
          shellType,
          lines: [{ id: uid(), text: `\n  ➜ ${cwd}\r\n`, type: 'info', timestamp: Date.now() }],
          active: true,
          cwd,
          processId: info.id,
          _shellConfig: { shell: shellType === 'bash' ? 'bash' : 'powershell.exe', cwd },
        }
        terminalSessions.value.push(term)
        return id
      } catch (e) {
        console.warn('[Terminal] spawn failed, using mock:', e)
      }
    }

    // Fallback: mock terminal
    const term: TerminalSession = {
      id,
      title: `终端 (${terminalSessions.value.length + 1})`,
      shellType,
      lines: [{ id: uid(), text: `\n  ➜ ${cwd} (仿真模式)\r\n`, type: 'info', timestamp: Date.now() }],
      active: true,
      cwd,
    }
    terminalSessions.value.push(term)
    return id
  }

  /** Close/kill terminal */
  async function closeTerminal(id: string): Promise<void> {
    const idx = terminalSessions.value.findIndex(t => t.id === id)
    if (idx === -1) return
    const term = terminalSessions.value[idx]
    const wasActive = term.active

    // Kill process
    if (term.processId && term.processId > 0 && isTauriEnv()) {
      try {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('kill_process', { pid: term.processId })
      } catch { /* ignore */ }
    }

    terminalSessions.value.splice(idx, 1)
    if (wasActive && terminalSessions.value.length > 0) {
      const newActive = terminalSessions.value[Math.min(idx, terminalSessions.value.length - 1)]
      newActive.active = true
    }
  }

  /** Switch active terminal */
  function switchToTerminal(id: string): void {
    terminalSessions.value.forEach(t => (t.active = t.id === id))
  }

  /** Duplicate terminal (spawns new real shell with same cwd) */
  async function duplicateTerminal(): Promise<string> {
    const term = terminalSessions.value.find(t => t.active)
    if (!term) return createTerminal()
    return createTerminal(term.shellType)
  }

  function renameTerminal(id: string, name: string): void {
    const term = terminalSessions.value.find(t => t.id === id)
    if (term) term.title = name
  }

  async function addTerminalLine(
    text: string,
    type: TerminalSession['lines'][0]['type'] = 'output',
  ): Promise<void> {
    const term = terminalSessions.value.find((t) => t.active)
    if (!term) return

    // Send to real process if available
    if (term.processId && term.processId > 0 && isTauriEnv() && type !== 'info') {
      try {
        const { invoke } = await import('@tauri-apps/api/core')
        await invoke('write_to_pty', { pid: term.processId, data: `${text}\r\n` })
      } catch {
        console.warn('[Terminal] write_to_pty failed')
      }
    }

    _pushLine(term, text, type)
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

  /** Execute command in terminal (TasksPanel) */
  async function executeCommandInTerminal(
    command: string,
    title: string = command.slice(0, 20),
    cwd: string = useFileTreeStore().workspaceRoot || '.',
    shellType: TerminalSession['shellType'] = 'powershell',
  ): Promise<string> {
    terminalSessions.value.forEach(t => (t.active = false))
    const id = uid()

    if (isTauriEnv()) {
      try {
        const { invoke } = await import('@tauri-apps/api/core')
        const info: any = await invoke('spawn_shell', {
          config: { shell: shellType === 'bash' ? 'bash' : 'powershell.exe', cwd },
        })
        // Send the command
        await invoke('write_to_pty', { pid: info.id, data: `${command}\r\n` })
        const term: TerminalSession = {
          id,
          title: `任务: ${title}`,
          shellType,
          lines: [
            { id: uid(), text: `\n  执行: ${command}\r\n`, type: 'info', timestamp: Date.now() },
          ],
          active: true,
          cwd,
          processId: info.id,
        }
        terminalSessions.value.push(term)
        return id
      } catch (e) {
        console.warn('[Terminal] executeCommand failed:', e)
      }
    }

    // Fallback
    const term: TerminalSession = {
      id,
      title: `任务: ${title}`,
      shellType,
      lines: [
        { id: uid(), text: `\n  执行: ${command} (仿真模式)\r\n`, type: 'info', timestamp: Date.now() },
      ],
      active: true,
      cwd,
    }
    terminalSessions.value.push(term)
    return id
  }

  return {
    terminalSessions,
    activeTerminalId,
    createTerminal,
    closeTerminal,
    switchToTerminal,
    duplicateTerminal,
    renameTerminal,
    addTerminalLine,
    outputChannels,
    activeOutputChannel,
    addOutputLine,
    executeCommandInTerminal,
  }
})

interface TerminalTauriOutput {
  pid: number
  data: string
  isError: boolean
  timestamp: number
}
