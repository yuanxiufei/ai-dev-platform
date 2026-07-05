<script setup lang="ts">
/**
 * Terminal — xterm.js 真终端 (Session 28 重构)
 *
 * 从 Vue 伪终端 + HTML input 重构为 xterm.js Canvas 渲染 + 隐藏 textarea。
 * VSCode 同款架构：Canvas 绘制所有内容，<textarea> 隐藏只捕获键盘事件。
 *
 * 功能保持：
 *   - 多终端标签页 (+ 新建 / × 关闭)
 *   - 终端分割 (复制当前)
 *   - Shell 类型切换 (bash/zsh/powershell/cmd)
 *   - 终端重命名 (双击标签)
 *   - 清屏
 *   - 14 个终端主题
 *   - ANSI 彩色输出 (xterm原生支持)
 */
import { ref, computed, nextTick, onMounted, onBeforeUnmount, watch } from "vue"
import { useIDEStore } from "@/stores/useIDEStore"
import { Plus, X, Palette, SplitSquareVertical, Trash2, Eraser, ChevronDown } from "lucide-vue-next"
import { Terminal } from "xterm"
import { FitAddon } from "@xterm/addon-fit"
import { WebLinksAddon } from "@xterm/addon-web-links"
import "xterm/css/xterm.css"
import type { TerminalSession } from "@/types/ide"

const props = withDefaults(
  defineProps<{
    embedded?: boolean
  }>(),
  { embedded: false },
)

// ── xterm 实例管理 ──
interface XtermInstance {
  terminal: Terminal
  fitAddon: FitAddon
  container: HTMLDivElement
}

const xtermMap = new Map<string, XtermInstance>()

// ── 主题 ──
interface TerminalTheme {
  id: string; name: string; bg: string; fg: string; accent: string
  green: string; red: string; yellow: string; blue: string
  cyan: string; magenta: string; white: string; brightBlack: string
  cursor: string; selection: string
}

const TERMINAL_THEMES: TerminalTheme[] = [
  { id: "vscode-dark", name: "VSCode Dark", bg: "#1e1e1e", fg: "#d4d4d4", accent: "#007acc", green: "#6a9955", red: "#f44747", yellow: "#d7ba7d", blue: "#569cd6", cyan: "#4ec9b0", magenta: "#c586c0", white: "#d4d4d4", brightBlack: "#808080", cursor: "#d4d4d4", selection: "#264f78" },
  { id: "default", name: "Default Dark", bg: "#1a1a2e", fg: "#cdd6f4", accent: "#89b4fa", green: "#50fa7b", red: "#f38ba8", yellow: "#f9e2af", blue: "#89b4fa", cyan: "#89dceb", magenta: "#cba6f7", white: "#cdd6f4", brightBlack: "#45475a", cursor: "#f5f5f5", selection: "#45475a99" },
  { id: "solarized-dark", name: "Solarized Dark", bg: "#002b36", fg: "#839496", accent: "#268bd2", green: "#859900", red: "#dc322f", yellow: "#b58900", blue: "#268bd2", cyan: "#2aa198", magenta: "#d33682", white: "#eee8d5", brightBlack: "#586e75", cursor: "#839496", selection: "#073642" },
  { id: "one-dark-pro", name: "One Dark Pro", bg: "#282c34", fg: "#abb2bf", accent: "#61afef", green: "#98c379", red: "#e06c75", yellow: "#d19a66", blue: "#61afef", cyan: "#56b6c2", magenta: "#c678dd", white: "#abb2bf", brightBlack: "#5c6370", cursor: "#528bff", selection: "#3e4452" },
  { id: "dracula", name: "Dracula", bg: "#282a36", fg: "#f8f8f2", accent: "#bd93f9", green: "#50fa7b", red: "#ff5555", yellow: "#f1fa8c", blue: "#6272a4", cyan: "#8be9fd", magenta: "#ff79c6", white: "#f8f8f2", brightBlack: "#44475a", cursor: "#f8f8f2", selection: "#44475a" },
  { id: "tokyo-night", name: "Tokyo Night", bg: "#1a1b26", fg: "#a9b1d6", accent: "#7aa2f7", green: "#9ece6a", red: "#f7768e", yellow: "#e0af68", blue: "#7aa2f7", cyan: "#7dcfff", magenta: "#bb9af7", white: "#c0caf5", brightBlack: "#414868", cursor: "#c0caf5", selection: "#364A82" },
  { id: "monokai", name: "Monokai", bg: "#272822", fg: "#f8f8f2", accent: "#a6e22e", green: "#a6e22e", red: "#f92672", yellow: "#e6db74", blue: "#66d9ef", cyan: "#a1efe4", magenta: "#fd5ff0", white: "#f8f8f2", brightBlack: "#75715e", cursor: "#f8f8f2", selection: "#49483e" },
  { id: "nord", name: "Nord", bg: "#2e3440", fg: "#d8dee9", accent: "#88c0d0", green: "#a3be8c", red: "#bf616a", yellow: "#ebcb8b", blue: "#81a1c1", cyan: "#88c0d0", magenta: "#b48ead", white: "#e5e9f0", brightBlack: "#4c566a", cursor: "#d8dee9", selection: "#434c5e" },
  { id: "catppuccin", name: "Catppuccin", bg: "#1e1e2e", fg: "#cdd6f4", accent: "#89b4fa", green: "#a6e3a1", red: "#f38ba8", yellow: "#f9e2af", blue: "#89b4fa", cyan: "#94e2d5", magenta: "#cba6f7", white: "#cdd6f4", brightBlack: "#585b70", cursor: "#f5e0dc", selection: "#45475a" },
  { id: "material", name: "Material", bg: "#263238", fg: "#eeffff", accent: "#82aaff", green: "#c3e88d", red: "#ff5370", yellow: "#ffcb6b", blue: "#82aaff", cyan: "#89ddff", magenta: "#c792ea", white: "#eeffff", brightBlack: "#546e7a", cursor: "#eeffff", selection: "#314549" },
  { id: "github-dark", name: "GitHub Dark", bg: "#0d1117", fg: "#c9d1d9", accent: "#58a6ff", green: "#3fb950", red: "#f85149", yellow: "#d2991d", blue: "#58a6ff", cyan: "#39c5cf", magenta: "#bc8cff", white: "#b1bac4", brightBlack: "#484f58", cursor: "#c9d1d9", selection: "#264f78" },
  { id: "ayu-dark", name: "Ayu Dark", bg: "#0b0e14", fg: "#bfbdb6", accent: "#ff8f40", green: "#aad94c", red: "#f07178", yellow: "#ffb454", blue: "#59c2ff", cyan: "#95e6cb", magenta: "#d2a6ff", white: "#acb6bf", brightBlack: "#475266", cursor: "#f29668", selection: "#1f2430" },
  { id: "solarized-light", name: "Solarized Light", bg: "#fdf6e3", fg: "#657b83", accent: "#268bd2", green: "#859900", red: "#dc322f", yellow: "#b58900", blue: "#268bd2", cyan: "#2aa198", magenta: "#d33682", white: "#073642", brightBlack: "#839496", cursor: "#657b83", selection: "#eee8d5" },
  { id: "github-light", name: "GitHub Light", bg: "#ffffff", fg: "#24292f", accent: "#0969da", green: "#1a7f37", red: "#cf222e", yellow: "#9a6700", blue: "#0969da", cyan: "#1b7c83", magenta: "#8250df", white: "#6e7781", brightBlack: "#57606a", cursor: "#24292f", selection: "#ddf4ff" },
]

const savedThemeId = localStorage.getItem("terminal_theme") || "vscode-dark"
const activeTheme = ref<TerminalTheme>(
  TERMINAL_THEMES.find((t) => t.id === savedThemeId) || TERMINAL_THEMES[0],
)
const showThemeMenu = ref(false)
const showShellMenu = ref(false)
const renamingTerminal = ref<string | null>(null)
const renameInput = ref("")
const renameRef = ref<HTMLInputElement | null>(null)

// ── Session 43: Terminal FindWidget ──
const showTerminalFind = ref(false)
const terminalFindQuery = ref("")
const terminalFindMatchCase = ref(false)
const terminalFindWholeWord = ref(false)
const terminalFindRegex = ref(false)
const terminalFindResults = ref<{ line: number; col: number; text: string }[]>([])
const terminalFindIndex = ref(0)
const terminalFindRef = ref<HTMLInputElement | null>(null)

// ── Session 47: Terminal Split Pane (真正的并排终端分屏) ──
const terminalSplitMode = ref<'none' | 'vertical' | 'horizontal'>('none')
const terminalSplitRatio = ref(50) // 0-100, 第一个窗格的百分比
const splitResizeRef = ref<HTMLDivElement | null>(null)
const splitPane1Ref = ref<HTMLDivElement | null>(null)
const splitPane2Ref = ref<HTMLDivElement | null>(null)

// ── Session 47: Terminal QuickFix ──
const showQuickFix = ref(false)
const quickfixCategories = ref<any[]>([])
const quickfixLastCommand = ref("")
const quickfixTimer = ref<ReturnType<typeof setTimeout> | null>(null)
const quickfixBaseUrl = import.meta.env.VITE_API_BASE || "/api/v1"

/** 搜索当前活动终端缓冲区 */
function searchTerminalBuffer(): void {
  const activeId = store.activeTerminalId
  if (!activeId) return
  const inst = xtermMap.get(activeId)
  if (!inst) return

  const query = terminalFindQuery.value
  if (!query.trim()) {
    terminalFindResults.value = []
    return
  }

  const buffer = inst.terminal.buffer.active
  const results: { line: number; col: number; text: string }[] = []

  let pattern: RegExp
  try {
    const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
    const flags = terminalFindMatchCase.value ? "g" : "gi"
    const source = terminalFindRegex.value ? query : (terminalFindWholeWord.value ? `\\b${escaped}\\b` : escaped)
    pattern = new RegExp(source, flags)
  } catch {
    return
  }

  for (let i = 0; i < buffer.length; i++) {
    const line = buffer.getLine(i)
    if (!line) continue
    const text = line.translateToString()
    let match: RegExpExecArray | null
    const linePattern = new RegExp(pattern.source, pattern.flags)
    while ((match = linePattern.exec(text)) !== null) {
      results.push({ line: i + 1, col: match.index + 1, text: match[0] })
    }
  }

  terminalFindResults.value = results
  if (results.length > 0) {
    terminalFindIndex.value = 0
    scrollToTerminalMatch(results[0].line)
  }
}

/** 滚动到指定行并高亮 */
function scrollToTerminalMatch(lineNum: number): void {
  const activeId = store.activeTerminalId
  if (!activeId) return
  const inst = xtermMap.get(activeId)
  if (!inst) return

  // xterm.scrollToLine (如果可用) 或使用 scrollLines
  try {
    inst.terminal.scrollToLine(lineNum - 1)
  } catch {
    // 回退方案：计算滚动偏移
    const buffer = inst.terminal.buffer.active
    const viewport = buffer.viewportY
    if (lineNum < viewport || lineNum > viewport + inst.terminal.rows) {
      const offset = lineNum - Math.floor(inst.terminal.rows / 2)
      inst.terminal.scrollLines(offset - buffer.viewportY)
    }
  }
}

/** 导航到上一个终端匹配 */
function terminalFindPrev(): void {
  if (terminalFindResults.value.length === 0) return
  terminalFindIndex.value = (terminalFindIndex.value - 1 + terminalFindResults.value.length) % terminalFindResults.value.length
  scrollToTerminalMatch(terminalFindResults.value[terminalFindIndex.value].line)
}

/** 导航到下一个终端匹配 */
function terminalFindNext(): void {
  if (terminalFindResults.value.length === 0) return
  terminalFindIndex.value = (terminalFindIndex.value + 1) % terminalFindResults.value.length
  scrollToTerminalMatch(terminalFindResults.value[terminalFindIndex.value].line)
}

/** 打开终端查找 */
function toggleTerminalFind(): void {
  showTerminalFind.value = !showTerminalFind.value
  if (showTerminalFind.value) {
    nextTick(() => terminalFindRef.value?.focus())
  } else {
    terminalFindResults.value = []
    terminalFindQuery.value = ""
  }
}

/** 关闭终端查找 */
function closeTerminalFind(): void {
  showTerminalFind.value = false
  terminalFindResults.value = []
  terminalFindQuery.value = ""
}

const store = useIDEStore()

// ══════════════════════════════════════════════
// WebSocket PTY connections (VSCode 架构)
// ══════════════════════════════════════════════
const wsMap = new Map<string, WebSocket>()

const SHELL_PATH_MAP: Record<string, string> = {
  bash: '/bin/bash',
  zsh: '/bin/zsh',
  powershell: 'powershell.exe',
  cmd: 'cmd.exe',
}

function getPtyWsUrl(sessionId: string): string {
  const token = localStorage.getItem('token')
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/api/v1/system/terminal/sessions/${sessionId}/ws?token=${token}`
}

function closePtyWs(sessionId: string): void {
  const ws = wsMap.get(sessionId)
  if (!ws) return
  ws.onclose = null
  ws.onerror = null
  ws.onmessage = null
  try {
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.send(JSON.stringify({ type: 'shutdown' }))
      ws.close()
    }
  } catch { /* ignore */ }
  wsMap.delete(sessionId)
}

// ── Shell 类型 ──
const shellTypes = ["bash", "zsh", "powershell", "cmd"] as const
const shellLabels: Record<string, string> = {
  bash: "Bash",
  zsh: "Zsh",
  powershell: "PowerShell",
  cmd: "Cmd",
}

const activeTerminal = computed(() =>
  store.terminalSessions.find((t) => t.id === store.activeTerminalId),
)

// ── 输入缓冲 ──
// 每个 session 维护自己的输入缓冲（xterm.onData 逐字符接收）
const inputBuffer = new Map<string, string>()

function getBuffer(id: string): string {
  if (!inputBuffer.has(id)) inputBuffer.set(id, "")
  return inputBuffer.get(id)!
}
function setBuffer(id: string, val: string): void {
  inputBuffer.set(id, val)
}
function appendBuffer(id: string, char: string): void {
  inputBuffer.set(id, getBuffer(id) + char)
}
function backspaceBuffer(id: string): void {
  const v = getBuffer(id)
  if (v.length > 0) setBuffer(id, v.slice(0, -1))
}
function clearBuffer(id: string): void {
  setBuffer(id, "")
}

// ── xterm 主题映射 ──
function applyThemeToXterm(t: Terminal, theme: TerminalTheme): void {
  const isLight = theme.id.includes("light")
  t.options.theme = {
    background: theme.bg,
    foreground: theme.fg,
    cursor: theme.cursor,
    cursorAccent: theme.bg,
    selectionBackground: theme.selection,
    selectionForeground: theme.fg,
    black: isLight ? "#002b36" : "#000000",
    red: theme.red,
    green: theme.green,
    yellow: theme.yellow,
    blue: theme.blue,
    magenta: theme.magenta,
    cyan: theme.cyan,
    white: theme.white,
    brightBlack: theme.brightBlack,
    brightRed: theme.red,
    brightGreen: theme.green,
    brightYellow: theme.yellow,
    brightBlue: theme.blue,
    brightMagenta: theme.magenta,
    brightCyan: theme.cyan,
    brightWhite: theme.fg,
  }
}

// ── 打印 prompt ──
// ANSI 绿色箭头 + 灰色路径
function writePrompt(t: Terminal, session: TerminalSession): void {
  const cwd = session.cwd ?? "~"
  const shellSymbol =
    session.shellType === "powershell" ? "PS" :
    session.shellType === "cmd" ? ">" :
    session.shellType === "zsh" ? "%" : "➜"
  // 模拟 VSCode 风格 prompt：绿色符号 + 蓝色路径 + 灰色 $
  t.write(`\x1b[32m${shellSymbol}\x1b[0m \x1b[34m${cwd}\x1b[0m \x1b[90m$\x1b[0m `)
}

// ── 创建 xterm 实例（含 WebSocket PTY 连接）──
function createXtermInstance(session: TerminalSession): XtermInstance {
  const container = document.createElement("div")
  container.className = "xterm-container"
  container.style.cssText = "width:100%;height:100%;"

  const fitAddon = new FitAddon()
  const terminal = new Terminal({
    cursorBlink: true,
    cursorStyle: "bar",
    fontSize: 13,
    fontFamily: "'Cascadia Code','JetBrains Mono','Fira Code',Consolas,monospace",
    allowProposedApi: true,
    convertEol: true,
    scrollback: 5000,
    disableStdin: false,
    cols: 80,
    rows: 24,
    allowTransparency: false,
    overviewRulerWidth: 0,
  })

  terminal.loadAddon(fitAddon)
  terminal.loadAddon(new WebLinksAddon())
  applyThemeToXterm(terminal, activeTheme.value)
  terminal.open(container)

  // ── WebSocket PTY 连接 ──
  let wsConnected = false

  function connectWebSocket(): void {
    const token = localStorage.getItem('token')
    if (!token) return

    const ws = new WebSocket(getPtyWsUrl(session.id))
    let pendingSent = false

    ws.onopen = () => {
      wsConnected = true
      // 发送 init 消息
      const shellPath = SHELL_PATH_MAP[session.shellType] || '/bin/bash'
      ws.send(JSON.stringify({
        type: 'init',
        shell: shellPath,
        cwd: session.cwd !== '~' ? session.cwd : undefined,
        rows: terminal.rows,
        cols: terminal.cols,
      }))
    }

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data as string)
        if (msg.type === 'ready') {
          // WS 就绪，发送待处理命令
          if (session.pendingCommand && !pendingSent) {
            pendingSent = true
            ws.send(JSON.stringify({ type: 'input', data: session.pendingCommand + '\r' }))
            session.pendingCommand = undefined
          }
          return
        }
        if (msg.type === 'exit') {
          terminal.writeln(`\x1b[90m\r\n[进程已退出，退出码: ${msg.exit_code}]\x1b[0m`)
          return
        }
        if (msg.type === 'pong' || msg.type === 'error') return
      } catch {
        // 二进制数据或纯文本 PTY 输出
        if (typeof event.data === 'string') {
          terminal.write(event.data as string)
        }
      }
      // 纯文本 PTY 输出
      if (typeof event.data === 'string') {
        try { JSON.parse(event.data) } catch { terminal.write(event.data as string) }
      }
    }

    ws.onerror = () => {
      // WebSocket 连接失败，使用本地回退
      terminal.writeln('\x1b[33m[终端未连接后端，使用本地模式]\x1b[0m\r\n')
      writePrompt(terminal, session)
    }

    ws.onclose = () => {
      wsMap.delete(session.id)
      wsConnected = false
    }

    wsMap.set(session.id, ws)
  }

  // 延迟连接（给 DOM 一点时间挂载）
  connectWebSocket()

  // ── 输入处理 ──
  terminal.onData((data: string) => {
    const currentWs = wsMap.get(session.id)
    if (currentWs && currentWs.readyState === WebSocket.OPEN) {
      // 通过 WebSocket 发送到后端 PTY
      currentWs.send(JSON.stringify({ type: 'input', data }))
    } else {
      // 本地回退：仅处理基本终端操作
      handleLocalInput(terminal, session, data)
    }
  })

  // ── 窗口大小变化 → 通知后端 ──
  terminal.onResize(({ rows, cols }) => {
    const currentWs = wsMap.get(session.id)
    if (currentWs && currentWs.readyState === WebSocket.OPEN) {
      currentWs.send(JSON.stringify({ type: 'resize', rows, cols }))
    }
  })

  return { terminal, fitAddon, container }
}

// ── 本地输入回退（仅限无 WS 连接时使用）──
function handleLocalInput(
  t: Terminal,
  session: TerminalSession,
  data: string,
): void {
  for (const ch of data) {
    if (ch === '\r') {
      // Enter — 回显并提示
      const cmd = getBuffer(session.id).trim()
      t.write('\r\n')
      clearBuffer(session.id)
      if (cmd) {
        if (cmd === 'cls' || cmd === 'clear') {
          t.clear()
          writePrompt(t, session)
        } else {
          t.writeln(`\x1b[90m[本地模式不支持命令执行: ${cmd.slice(0, 60)}]\x1b[0m`)
          writePrompt(t, session)
        }
      } else {
        writePrompt(t, session)
      }
    } else if (ch === '\x7f') {
      if (getBuffer(session.id).length > 0) {
        backspaceBuffer(session.id)
        t.write('\b \b')
      }
    } else if (ch === '\x03') {
      clearBuffer(session.id)
      t.write('^C\r\n')
      writePrompt(t, session)
    } else if (ch === '\x0c') {
      t.clear()
      writePrompt(t, session)
    } else if (ch >= ' ') {
      appendBuffer(session.id, ch)
      t.write(ch)
    }
  }
}

// ── 终端操作 ──
function newTerminal(): void {
  store.createTerminal("bash")
}

function splitTerminal(): void {
  // Session 47: 真正的分屏 — 切换 none → vertical → horizontal → none
  if (terminalSplitMode.value === 'none') {
    terminalSplitMode.value = 'vertical'
    // 确保有至少 2 个终端会话
    if (store.terminalSessions.length < 2) {
      store.createTerminal("bash")
    }
  } else if (terminalSplitMode.value === 'vertical') {
    terminalSplitMode.value = 'horizontal'
  } else {
    terminalSplitMode.value = 'none'
  }
}

/** Session 47: 分屏尺寸拖拽 */
function onSplitResizeStart(e: MouseEvent): void {
  e.preventDefault()
  const isVertical = terminalSplitMode.value === 'vertical'
  const container = splitPane1Ref.value?.parentElement
  if (!container) return
  const startPos = isVertical ? e.clientX : e.clientY
  const containerSize = isVertical ? container.clientWidth : container.clientHeight
  const startRatio = terminalSplitRatio.value

  const onMove = (ev: MouseEvent) => {
    const delta = isVertical ? ev.clientX - startPos : ev.clientY - startPos
    const deltaPct = (delta / containerSize) * 100
    terminalSplitRatio.value = Math.min(80, Math.max(20, startRatio + deltaPct))
  }
  const onUp = () => {
    document.removeEventListener("mousemove", onMove)
    document.removeEventListener("mouseup", onUp)
  }
  document.addEventListener("mousemove", onMove)
  document.addEventListener("mouseup", onUp)
}

/** Session 47: 获取分屏中第二个终端的 session id（当前活动终端之后的那个） */
function getSplitSecondTerminalId(): string {
  const activeId = store.activeTerminalId
  const sessions = store.terminalSessions
  if (sessions.length >= 2) {
    const idx = sessions.findIndex(s => s.id === activeId)
    if (idx >= 0 && idx + 1 < sessions.length) return sessions[idx + 1].id
    // 如果当前是最后一个，取第一个
    if (idx === sessions.length - 1) return sessions[0].id
    // fallback: 取非活动的一个
    const other = sessions.find(s => s.id !== activeId)
    if (other) return other.id
  }
  return ""
}

/** Session 47: 终端输出变化时触发 QuickFix 检测 (防抖 2秒) */
function triggerQuickFixCheck(lastCmd: string): void {
  quickfixLastCommand.value = lastCmd
  if (quickfixTimer.value) clearTimeout(quickfixTimer.value)
  quickfixTimer.value = setTimeout(async () => {
    const inst = xtermMap.get(store.activeTerminalId || "")
    if (!inst) return
    // 读取最后 20 行
    const buf = inst.terminal.buffer.active
    const totalLines = buf.length
    const startLine = Math.max(0, totalLines - 20)
    const lines: string[] = []
    for (let i = startLine; i < totalLines; i++) {
      const line = buf.getLine(i)
      if (line) lines.push(line.translateToString())
    }
    const output = lines.join("\n")
    try {
      const res = await fetch(`${quickfixBaseUrl}/system/terminal/quickfix`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ output, last_command: lastCmd, working_directory: "" }),
      })
      if (res.ok) {
        const data = await res.json()
        if (data.has_issues && data.categories?.length) {
          quickfixCategories.value = data.categories
          showQuickFix.value = true
        }
      }
    } catch { /* 网络异常时静默 */ }
  }, 2000)
}

function killTerminal(id: string): void {
  // 先关闭 WebSocket 连接
  closePtyWs(id)
  // 销毁 xterm 实例
  const inst = xtermMap.get(id)
  if (inst) {
    inst.terminal.dispose()
    xtermMap.delete(id)
  }
  inputBuffer.delete(id)
  store.closeTerminal(id)
}

function switchTerminal(id: string): void {
  store.switchToTerminal(id)
}

function clearTerminal(): void {
  const id = store.activeTerminalId
  if (!id) return
  const inst = xtermMap.get(id)
  if (inst) {
    inst.terminal.clear()
    const session = store.terminalSessions.find((t) => t.id === id)
    if (session) writePrompt(inst.terminal, session)
  }
}

function changeShell(type: TerminalSession["shellType"]): void {
  const term = activeTerminal.value
  if (!term) return
  term.shellType = type
  term.title = `${shellLabels[type]} ${store.terminalSessions.indexOf(term) + 1}`
  showShellMenu.value = false

  // 当前终端重新打印 prompt
  const id = term.id
  const inst = xtermMap.get(id)
  if (inst) {
    inst.terminal.writeln(`\x1b[90m# Switched to ${shellLabels[type]}\x1b[0m`)
    writePrompt(inst.terminal, term)
  }
}

// ── 重命名 ──
function startRename(id: string, currentName: string): void {
  renamingTerminal.value = id
  renameInput.value = currentName
  nextTick(() => renameRef.value?.focus())
}

function finishRename(id: string): void {
  if (renameInput.value.trim()) {
    store.renameTerminal(id, renameInput.value.trim())
  }
  renamingTerminal.value = null
}

// ── 主题切换 ──
function selectTheme(theme: TerminalTheme): void {
  activeTheme.value = theme
  showThemeMenu.value = false
  localStorage.setItem("terminal_theme", theme.id)
  // 更新所有 xterm 实例的主题
  xtermMap.forEach((inst) => {
    applyThemeToXterm(inst.terminal, theme)
  })
}

// ── 容器 refs 管理（xterm 容器挂载区） ──
const xtermAreaRef = ref<HTMLDivElement | null>(null)

// ── 监听 session 变化，创建/销毁 xterm 实例 ──
watch(
  () => store.terminalSessions.map((s) => s.id),
  (newIds, oldIds) => {
    // 新增的 session
    for (const sid of newIds) {
      if (!xtermMap.has(sid)) {
        const session = store.terminalSessions.find((s) => s.id === sid)
        if (session) {
          const inst = createXtermInstance(session)
          xtermMap.set(sid, inst)

          // 挂载容器到 DOM
          const area = xtermAreaRef.value
          if (area) {
            // Session 47: 分屏模式下，第二个终端放到 pane2
            const splitSecondId = terminalSplitMode.value !== 'none' ? getSplitSecondTerminalId() : ""
            const targetPane = (sid === splitSecondId && splitPane2Ref.value)
              ? splitPane2Ref.value : (splitPane1Ref.value || area)
            targetPane.appendChild(inst.container)
            // 非当前活动终端隐藏（分屏中第二个终端总是可见）
            if (!session.active && sid !== splitSecondId) {
              inst.container.style.display = "none"
            } else {
              // 活动终端写入启动 prompt
              nextTick(() => {
                inst.fitAddon.fit()
                inst.terminal.focus()
                writePrompt(inst.terminal, session)
              })
            }
          }
        }
      }
    }
    // 移除已删除的 session
    const removed = (oldIds || []).filter((id) => !newIds.includes(id))
    for (const rid of removed) {
      closePtyWs(rid)
      const inst = xtermMap.get(rid)
      if (inst) {
        inst.terminal.dispose()
        inst.container.remove()
        xtermMap.delete(rid)
      }
      inputBuffer.delete(rid)
    }
  },
  { immediate: false },
)

// ── 监听 activeTerminalId 变化，切换显示/隐藏 ──
watch(
  () => store.activeTerminalId,
  (newId) => {
    const splitSecondId = terminalSplitMode.value !== 'none' ? getSplitSecondTerminalId() : ""
    // 隐藏所有，显示当前（分屏中第二个终端总是可见）
    xtermMap.forEach((inst, id) => {
      if (id === newId || id === splitSecondId) {
        inst.container.style.display = ""
        if (id === newId) {
          nextTick(() => {
            inst.fitAddon.fit()
            inst.terminal.focus()
            // 如果终端还没有 prompt，写入一个
            const session = store.terminalSessions.find((s) => s.id === id)
            if (session) {
              // 检查 buffer 是否空（粗略判断）
              const buf = inst.terminal.buffer.active
              if (buf.length <= 2) {
                writePrompt(inst.terminal, session)
              }
            }
          })
        }
      } else {
        inst.container.style.display = "none"
      }
    })
  },
)

// ── 初始挂载 ──
onMounted(() => {
  // Session 43: Terminal 键盘查找 (Ctrl+F)
  const area = xtermAreaRef.value
  if (area) {
    area.addEventListener("keydown", handleTerminalKeydown)
  }
  // 为已有 session 创建 xterm 实例
  nextTick(() => {
    for (const session of store.terminalSessions) {
      if (!xtermMap.has(session.id)) {
        const inst = createXtermInstance(session)
        xtermMap.set(session.id, inst)
        const xtermArea = xtermAreaRef.value
        if (xtermArea) {
          xtermArea.appendChild(inst.container)
          if (!session.active) {
            inst.container.style.display = "none"
          } else {
            inst.fitAddon.fit()
            inst.terminal.focus()
            writePrompt(inst.terminal, session)
          }
        }
      }
    }
  })
  // ResizeObserver
  if (area) {
    resizeObserver = new ResizeObserver(() => {
      const activeId = store.activeTerminalId
      if (!activeId) return
      const inst = xtermMap.get(activeId)
      if (inst && inst.container.style.display !== "none") {
        inst.fitAddon.fit()
      }
    })
    resizeObserver.observe(area)
  }
})

/** Session 43: Terminal 键盘查找 (Ctrl+F) */
function handleTerminalKeydown(e: KeyboardEvent): void {
  if (e.ctrlKey && e.key === "f") {
    e.preventDefault()
    toggleTerminalFind()
  } else if (e.key === "Escape" && showTerminalFind.value) {
    closeTerminalFind()
  }
}

// ── 销毁 ──
onBeforeUnmount(() => {
  // 移除键盘事件
  const area = xtermAreaRef.value
  if (area) {
    area.removeEventListener("keydown", handleTerminalKeydown)
  }
  resizeObserver?.disconnect()
  resizeObserver = null
  // 关闭所有 WebSocket 连接
  wsMap.forEach((_ws, id) => closePtyWs(id))
  xtermMap.forEach((inst) => {
    inst.terminal.dispose()
  })
  xtermMap.clear()
  inputBuffer.clear()
})
</script>

<template>
  <div class="terminal-container h-full flex flex-col">
    <!-- ═══ Terminal Tab Bar (32px) — 标签页+工具栏同行 ═══ -->
    <div
      class="flex items-center shrink-0 border-b border-[var(--color-ide-border)]"
      style="background:var(--color-ide-bg-secondary); height:32px;"
    >
      <!-- Terminal tabs (可滚动) -->
      <div class="flex-1 flex items-center h-full min-w-0 overflow-x-auto scrollbar-none">
        <button
          v-for="term in store.terminalSessions"
          :key="term.id"
          class="terminal-tab flex items-center gap-1.5 px-3 h-full text-[11px] uppercase tracking-wide font-semibold transition-colors shrink-0 select-none border-r border-[var(--color-ide-border)] relative group"
          :class="
            term.active
              ? 'text-[var(--color-ide-text)]'
              : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]'
          "
          @click="switchTerminal(term.id)"
          @dblclick="startRename(term.id, term.title)"
        >
          <input
            v-if="renamingTerminal === term.id"
            ref="renameRef"
            v-model="renameInput"
            type="text"
            class="bg-[var(--color-terminal-bg)] text-[11px] border border-[var(--color-ide-border-focus)] rounded-[2px] px-1 py-0 outline-none w-20"
            style="background: var(--term-bg); color: var(--term-fg)"
            @blur="finishRename(term.id)"
            @keydown.enter="finishRename(term.id)"
            @keydown.escape="renamingTerminal = null"
          />
          <template v-else>
            <span v-if="term.shellType === 'powershell'" class="text-[9px] opacity-60" style="font-family: inherit">PS</span>
            <span v-else-if="term.shellType === 'bash'" class="text-[9px] opacity-60">$</span>
            <span v-else-if="term.shellType === 'zsh'" class="text-[9px] opacity-60">%</span>
            <span v-else class="text-[9px] opacity-60">&gt;</span>
            {{ term.title }}
          </template>
          <div
            v-if="term.active"
            class="absolute bottom-0 left-0 right-0"
            style="height:2px; background:var(--term-accent, #007acc)"
          />
          <span
            class="shrink-0 w-5 h-5 flex items-center justify-center rounded-[3px] opacity-0 group-hover:opacity-100 transition-all"
            :style="{ background: 'var(--term-tab-close-hover)', color: 'var(--color-ide-text-dim)' }"
            role="button"
            tabindex="0"
            @click.stop="killTerminal(term.id)"
            :title="store.terminalSessions.length > 1 ? '关闭终端' : '无法关闭最后一个终端'"
            @keydown.enter.stop="killTerminal(term.id)"
            @keydown.space.prevent.stop="killTerminal(term.id)"
          >
            <X :size="11" />
          </span>
        </button>
      </div>

      <!-- 工具栏 (始终显示) -->
      <div class="flex items-center shrink-0 gap-0.5 pr-1" style="border-left: 1px solid var(--color-ide-border)">
        <button
          class="w-7 h-7 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
          title="新建终端 (Ctrl+Shift+`)"
          @click="newTerminal"
        >
          <Plus :size="14" style="color: var(--color-ide-text-dim)" />
        </button>
        <button
          class="w-7 h-7 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
          title="分割终端 (Ctrl+Shift+5)"
          @click="splitTerminal"
        >
          <SplitSquareVertical :size="13" style="color: var(--color-ide-text-dim)" />
        </button>
        <button
          class="w-7 h-7 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
          title="关闭终端"
          @click="killTerminal(store.activeTerminalId!)"
          :disabled="store.terminalSessions.length <= 1"
        >
          <Trash2 :size="13" style="color: var(--color-ide-text-dim)" />
        </button>

        <!-- Shell 切换 -->
        <div class="relative">
          <button
            class="flex items-center gap-0.5 px-1.5 h-7 rounded-[3px] text-[10px] font-medium transition-colors hover:bg-[var(--color-ide-surface-hover)]"
            style="color: var(--color-ide-text-dim)"
            @click="showShellMenu = !showShellMenu; showThemeMenu = false"
          >
            {{ shellLabels[activeTerminal?.shellType || 'bash'] }}
            <ChevronDown :size="8" />
          </button>
          <Transition name="fade">
            <div
              v-if="showShellMenu"
              class="absolute right-0 top-full z-50 mt-0.5 py-1 min-w-[120px] rounded-md shadow-xl border"
              style="background:var(--color-ide-surface); border-color:var(--color-ide-border)"
            >
              <button
                v-for="st in shellTypes"
                :key="st"
                class="w-full text-left px-3 py-1.5 text-[11px] flex items-center gap-2 transition-colors hover:bg-[var(--color-ide-surface-hover)]"
                :class="
                  activeTerminal?.shellType === st
                    ? 'text-[var(--color-ide-accent)]'
                    : 'text-[var(--color-ide-text)]'
                "
                @click="changeShell(st)"
              >
                <svg
                  v-if="activeTerminal?.shellType === st"
                  width="10"
                  height="8"
                  viewBox="0 0 12 9"
                  fill="none"
                >
                  <path
                    d="M1 3l4 4 6-6"
                    stroke="var(--term-accent)"
                    stroke-width="1.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
                <span v-else class="w-2.5" />
                {{ shellLabels[st] }}
              </button>
            </div>
          </Transition>
        </div>

        <!-- 主题切换 -->
        <div class="relative">
          <button
            class="flex items-center gap-0.5 px-1.5 h-7 rounded-[3px] text-[10px] font-medium transition-colors hover:bg-[var(--color-ide-surface-hover)]"
            style="color: var(--color-ide-text-dim)"
            @click="showThemeMenu = !showThemeMenu; showShellMenu = false"
            title="终端主题"
          >
            <Palette :size="11" />
            <ChevronDown :size="8" />
          </button>
          <Transition name="fade">
            <div
              v-if="showThemeMenu"
              class="absolute right-0 top-full z-50 mt-0.5 py-1 min-w-[180px] max-h-72 overflow-y-auto rounded-md shadow-xl border"
              style="background:var(--color-ide-surface); border-color:var(--color-ide-border)"
            >
              <button
                v-for="theme in TERMINAL_THEMES"
                :key="theme.id"
                class="w-full text-left px-3 py-1.5 text-[11px] flex items-center gap-2 transition-colors hover:bg-[var(--color-ide-surface-hover)]"
                style="color:var(--color-ide-text)"
                @click="selectTheme(theme)"
              >
                <span
                  class="w-3 h-3 rounded-full border shrink-0"
                  :style="{ background: theme.bg, borderColor: theme.fg + '40' }"
                />
                <span class="flex-1">{{ theme.name }}</span>
                <svg
                  v-if="theme.id === activeTheme.id"
                  width="10"
                  height="8"
                  viewBox="0 0 12 9"
                  fill="none"
                >
                  <path
                    d="M1 3l4 4 6-6"
                    stroke="var(--term-accent)"
                    stroke-width="1.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
            </div>
          </Transition>
        </div>

        <!-- 清屏 -->
        <button
          class="w-7 h-7 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
          title="清屏 (Cmd+K)"
          @click="clearTerminal"
        >
          <Eraser :size="13" style="color: var(--color-ide-text-dim)" />
        </button>
      </div>
    </div>

    <!-- ═══ Terminal FindWidget (Session 43) ═══ -->
    <Transition name="find-slide">
      <div
        v-if="showTerminalFind"
        class="flex items-center gap-2 shrink-0 px-2 py-1.5 border-b border-[var(--color-ide-border)]"
        style="background:var(--color-ide-bg-secondary)"
      >
        <!-- 查找输入 -->
        <div class="flex items-center gap-1 flex-1">
          <input
            ref="terminalFindRef"
            v-model="terminalFindQuery"
            type="text"
            class="flex-1 bg-[var(--color-ide-surface)] text-[12px] text-[var(--color-ide-text)] border border-[var(--color-ide-border)] rounded px-2 py-0.5 outline-none focus:border-[var(--color-ide-border-focus)]"
            placeholder="查找..."
            @input="searchTerminalBuffer"
            @keydown.enter="terminalFindNext"
            @keydown.shift.enter="terminalFindPrev"
            @keydown.escape="closeTerminalFind"
          />
          <!-- 匹配计数 -->
          <span v-if="terminalFindResults.length > 0" class="text-[10px] text-[var(--color-ide-text-dim)] shrink-0" style="min-width: 40px; text-align: right;">
            {{ terminalFindIndex + 1 }}/{{ terminalFindResults.length }}
          </span>
          <span v-else-if="terminalFindQuery" class="text-[10px] shrink-0" style="color: var(--color-terminal-red); min-width: 30px; text-align: right;">无结果</span>
        </div>

        <!-- 导航按钮 -->
        <button
          class="w-5 h-5 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
          :style="{ color: terminalFindResults.length > 0 ? 'var(--color-ide-text-dim)' : 'var(--color-ide-text-dim)' }"
          title="上一个 (Shift+Enter)"
          @click="terminalFindPrev"
        >
          <ChevronUp :size="13" />
        </button>
        <button
          class="w-5 h-5 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
          :style="{ color: terminalFindResults.length > 0 ? 'var(--color-ide-text-dim)' : 'var(--color-ide-text-dim)' }"
          title="下一个 (Enter)"
          @click="terminalFindNext"
        >
          <ChevronDown :size="13" />
        </button>

        <!-- 选项按钮 -->
        <button
          class="w-5 h-5 flex items-center justify-center rounded-[3px] transition-colors text-[10px] font-bold"
          :class="terminalFindMatchCase ? 'bg-[var(--color-ide-border-focus)]' : 'hover:bg-[var(--color-ide-surface-hover)]'"
          :style="{ color: terminalFindMatchCase ? 'var(--color-ide-text)' : 'var(--color-ide-text-dim)' }"
          title="区分大小写"
          @click="terminalFindMatchCase = !terminalFindMatchCase; searchTerminalBuffer()"
        >Aa</button>
        <button
          class="w-5 h-5 flex items-center justify-center rounded-[3px] transition-colors text-[10px] font-bold"
          :class="terminalFindWholeWord ? 'bg-[var(--color-ide-border-focus)]' : 'hover:bg-[var(--color-ide-surface-hover)]'"
          :style="{ color: terminalFindWholeWord ? 'var(--color-ide-text)' : 'var(--color-ide-text-dim)' }"
          title="全字匹配"
          @click="terminalFindWholeWord = !terminalFindWholeWord; searchTerminalBuffer()"
        >W</button>
        <button
          class="w-5 h-5 flex items-center justify-center rounded-[3px] transition-colors text-[10px] font-bold"
          :class="terminalFindRegex ? 'bg-[var(--color-ide-border-focus)]' : 'hover:bg-[var(--color-ide-surface-hover)]'"
          :style="{ color: terminalFindRegex ? 'var(--color-ide-text)' : 'var(--color-ide-text-dim)' }"
          title="正则表达式"
          @click="terminalFindRegex = !terminalFindRegex; searchTerminalBuffer()"
        >.*</button>

        <!-- 关闭 -->
        <button
          class="w-5 h-5 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
          title="关闭 (Esc)"
          style="color: var(--color-ide-text-dim)"
          @click="closeTerminalFind"
        >
          <X :size="12" />
        </button>
      </div>
    </Transition>

    <!-- ═══ Session 47: QuickFix Bar ═══ -->
    <Transition name="find-slide">
      <div
        v-if="showQuickFix && quickfixCategories.length > 0"
        class="flex items-center gap-1.5 shrink-0 px-2 py-1 border-b border-[var(--color-ide-border)] overflow-x-auto"
        style="background:var(--color-ide-bg-secondary)"
      >
        <span class="text-[10px] font-semibold shrink-0" style="color:var(--term-yellow)">💡</span>
        <template v-for="cat in quickfixCategories" :key="cat.category">
          <button
            v-for="fix in cat.suggestions"
            :key="fix.id"
            class="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] whitespace-nowrap transition-colors hover:brightness-110 shrink-0"
            :style="{ background: fix.severity === 'error' ? 'var(--term-red)' : fix.severity === 'warning' ? 'var(--term-yellow)' : 'var(--term-blue)', color: '#fff' }"
            :title="fix.tooltip"
            @click="navigator.clipboard.writeText(fix.command).then(() => store.terminalSessions.find(t=>t.active)?.id && sendToPty(store.terminalSessions.find(t=>t.active)!.id, fix.command + String.fromCharCode(13)))"
          >
            {{ fix.label }}
          </button>
        </template>
        <button
          class="shrink-0 w-4 h-4 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)] ml-auto"
          @click="showQuickFix = false"
        ><X :size="10" style="color:var(--color-ide-text-dim)" /></button>
      </div>
    </Transition>

    <!-- ═══ xterm.js Canvas 渲染区 (Session 47: 分屏支持) ═══ -->
    <div
      ref="xtermAreaRef"
      class="flex-1 relative overflow-hidden xterm-area"
      :class="{ 'split-horizontal': terminalSplitMode === 'horizontal', 'split-vertical': terminalSplitMode === 'vertical' }"
      :style="terminalSplitMode !== 'none' ? { display: 'flex', flexDirection: terminalSplitMode === 'vertical' ? 'row' : 'column' } : {}"
    >
      <!-- 单窗格模式 -->
      <template v-if="terminalSplitMode === 'none'">
        <!-- xterm 容器由 JS 动态创建注入 -->
      </template>

      <!-- 分屏模式: 窗格 1 -->
      <template v-if="terminalSplitMode !== 'none'">
        <div
          ref="splitPane1Ref"
          class="flex-1 relative overflow-hidden"
          :style="{ flexBasis: terminalSplitRatio + '%' }"
        >
          <!-- 活动终端在此窗格显示 -->
        </div>
        <!-- 分屏拖拽手柄 -->
        <div
          ref="splitResizeRef"
          class="split-resize-handle shrink-0 transition-colors"
          :class="{ 'handle-vertical': terminalSplitMode === 'vertical', 'handle-horizontal': terminalSplitMode === 'horizontal' }"
          @mousedown="onSplitResizeStart"
        />
        <!-- 分屏模式: 窗格 2 -->
        <div
          ref="splitPane2Ref"
          class="flex-1 relative overflow-hidden"
          :style="{ flexBasis: (100 - terminalSplitRatio) + '%' }"
        >
          <!-- 第二个终端在此窗格显示 -->
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
/* ═══ 终端面板主题变量（组件级 CSS 变量） ═══ */
.terminal-container {
  --term-tab-close-hover: rgba(255, 255, 255, 0.1);
  --term-tab-hover-bg: rgba(255, 255, 255, 0.03);
}
/* Terminal tab */
.terminal-tab {
  border: none;
  cursor: pointer;
  outline: none;
  background: transparent;
  transition: background-color 0.08s ease;
}
.terminal-tab:hover {
  background: var(--term-tab-hover-bg);
}
.terminal-tab:focus-visible {
  outline: 1px solid var(--color-ide-border-focus);
  outline-offset: -1px;
}

/* Hide scrollbar on tab bar */
.scrollbar-none::-webkit-scrollbar {
  display: none;
}
.scrollbar-none {
  -ms-overflow-style: none;
  scrollbar-width: none;
}

/* xterm area */
.xterm-area :deep(.xterm-container) {
  width: 100%;
  height: 100%;
}

/* xterm.js default styles — 确保终端填满容器 */
.xterm-area :deep(.xterm) {
  height: 100%;
  padding: 4px 8px;
}
.xterm-area :deep(.xterm-viewport) {
  width: 100% !important;
}

/* 终端内部无 input 边框感 */
.xterm-area :deep(.xterm-helper-textarea) {
  opacity: 0 !important;
  left: -9999em !important;
}

/* Session 43: Terminal FindWidget 过渡动画 */
.find-slide-enter-active,
.find-slide-leave-active {
  transition: all 0.15s ease;
}
.find-slide-enter-from,
.find-slide-leave-to {
  opacity: 0;
  max-height: 0;
  margin-top: 0;
  margin-bottom: 0;
  padding-top: 0;
  padding-bottom: 0;
  border-bottom-width: 0;
}
.find-slide-enter-to,
.find-slide-leave-from {
  opacity: 1;
  max-height: 36px;
}

/* Session 47: Terminal Split Pane — 分屏手柄样式 */
.split-resize-handle {
  background: var(--color-ide-border);
  transition: background-color 0.15s;
}
.split-resize-handle:hover,
.split-resize-handle:active {
  background: var(--color-ide-border-focus);
}
.handle-vertical {
  width: 4px;
  cursor: col-resize;
}
.handle-horizontal {
  height: 4px;
  cursor: row-resize;
}
</style>
