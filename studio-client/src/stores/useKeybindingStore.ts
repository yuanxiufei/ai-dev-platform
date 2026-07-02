/**
 * VSCode KeybindingService — 全局快捷键注册表
 *
 * Session 23: 统一管理全平台键盘快捷键，支持 when 条件、和弦序列 (chord)
 *
 * 借鉴: VSCode src/vs/platform/keybinding/common/keybindingResolver.ts
 *
 * 使用:
 *   const kb = useKeybindingStore()
 *   kb.register("Ctrl+Shift+P", () => togglePalette(), "global")
 *   kb.register("Ctrl+K Ctrl+D", () => duplicateTab(), "editor")
 */

import { ref, onMounted, onUnmounted } from "vue"

// ── 键盘修饰符常量（对齐 VSCode KeyMod） ──

export const enum KeyCode {
  Unknown = 0,
  Backspace = 1, Tab = 2, Enter = 3, Escape = 4,
  Space = 5, PageUp = 6, PageDown = 7, End = 8, Home = 9,
  LeftArrow = 10, UpArrow = 11, RightArrow = 12, DownArrow = 13,
  Delete = 14, Insert = 15,
  Key0 = 20, Key1 = 21, Key2 = 22, Key3 = 23, Key4 = 24,
  Key5 = 25, Key6 = 26, Key7 = 27, Key8 = 28, Key9 = 29,
  KeyA = 30, KeyB = 31, KeyC = 32, KeyD = 33, KeyE = 34,
  KeyF = 35, KeyG = 36, KeyH = 37, KeyI = 38, KeyJ = 39,
  KeyK = 40, KeyL = 41, KeyM = 42, KeyN = 43, KeyO = 44,
  KeyP = 45, KeyQ = 46, KeyR = 47, KeyS = 48, KeyT = 49,
  KeyU = 50, KeyV = 51, KeyW = 52, KeyX = 53, KeyY = 54, KeyZ = 55,
  F1 = 60, F2 = 61, F3 = 62, F4 = 63, F5 = 64,
  F6 = 65, F7 = 66, F8 = 67, F9 = 68, F10 = 69,
  F11 = 70, F12 = 71,
  Backquote = 80, Minus = 81, Equal = 82,
  BracketLeft = 83, BracketRight = 84, Backslash = 85,
  Semicolon = 86, Quote = 87, Comma = 88, Period = 89, Slash = 90,
}

/** VSCode 风格 KeyMod 位掩码 */
export const enum KeyMod {
  CtrlCmd  = 1 << 11,  // 2048
  Shift    = 1 << 10,  // 1024
  Alt      = 1 << 9,   // 512
  WinCtrl  = 1 << 8,   // 256
}

/** 平台适配: macOS 用 Cmd，其他用 Ctrl */
const isMac = typeof navigator !== "undefined" && /Mac/.test(navigator.platform)

/** 键盘快捷键绑定 */
export interface Keybinding {
  /** 绑定的键字符串，如 "Ctrl+Shift+P" 或 "Ctrl+K Ctrl+D" */
  key: string
  /** 执行动作 */
  action: () => void
  /** when 条件: "global" | "editor" | "terminal" | "sidebar" | "editorHasSelection" */
  when?: string
  /** 优先级: 数字越大越优先，默认 0 */
  priority?: number
  /** 和弦序列的第二键（如果 key 包含空格则为和弦） */
  _chordFirst?: number
  _chordSecond?: number
}

/** 当前上下文（由焦点决定） */
const currentContext = ref<string>("global")

// ── 键名映射表 ──

const KEY_MAP: Record<string, number> = {
  "A": KeyCode.KeyA, "B": KeyCode.KeyB, "C": KeyCode.KeyC, "D": KeyCode.KeyD,
  "E": KeyCode.KeyE, "F": KeyCode.KeyF, "G": KeyCode.KeyG, "H": KeyCode.KeyH,
  "I": KeyCode.KeyI, "J": KeyCode.KeyJ, "K": KeyCode.KeyK, "L": KeyCode.KeyL,
  "M": KeyCode.KeyM, "N": KeyCode.KeyN, "O": KeyCode.KeyO, "P": KeyCode.KeyP,
  "Q": KeyCode.KeyQ, "R": KeyCode.KeyR, "S": KeyCode.KeyS, "T": KeyCode.KeyT,
  "U": KeyCode.KeyU, "V": KeyCode.KeyV, "W": KeyCode.KeyW, "X": KeyCode.KeyX,
  "Y": KeyCode.KeyY, "Z": KeyCode.KeyZ,
  "0": KeyCode.Key0, "1": KeyCode.Key1, "2": KeyCode.Key2, "3": KeyCode.Key3,
  "4": KeyCode.Key4, "5": KeyCode.Key5, "6": KeyCode.Key6, "7": KeyCode.Key7,
  "8": KeyCode.Key8, "9": KeyCode.Key9,
  "F1": KeyCode.F1, "F2": KeyCode.F2, "F3": KeyCode.F3, "F4": KeyCode.F4,
  "F5": KeyCode.F5, "F6": KeyCode.F6, "F7": KeyCode.F7, "F8": KeyCode.F8,
  "F9": KeyCode.F9, "F10": KeyCode.F10, "F11": KeyCode.F11, "F12": KeyCode.F12,
  "Space": KeyCode.Space, "Tab": KeyCode.Tab, "Enter": KeyCode.Enter,
  "Escape": KeyCode.Escape,
  "Backspace": KeyCode.Backspace, "Delete": KeyCode.Delete,
  "Insert": KeyCode.Insert,
  "Up": KeyCode.UpArrow, "Down": KeyCode.DownArrow,
  "Left": KeyCode.LeftArrow, "Right": KeyCode.RightArrow,
  "PageUp": KeyCode.PageUp, "PageDown": KeyCode.PageDown,
  "Home": KeyCode.Home, "End": KeyCode.End,
  "`": KeyCode.Backquote, "-": KeyCode.Minus, "=": KeyCode.Equal,
  "[": KeyCode.BracketLeft, "]": KeyCode.BracketRight, "\\": KeyCode.Backslash,
  ";": KeyCode.Semicolon, "'": KeyCode.Quote,
  ",": KeyCode.Comma, ".": KeyCode.Period, "/": KeyCode.Slash,
}

/** 解析键字符串为修饰符 + 键码 */
function parseKeyChord(part: string): { mods: number; keyCode: number } | null {
  const parts = part.toUpperCase().split("+")
  let mods = 0
  let keyStr = ""

  for (const p of parts) {
    switch (p) {
      case "CTRL": case "CTRLCMD": mods |= KeyMod.CtrlCmd; break
      case "CMD": case "META": case "SUPER": mods |= isMac ? KeyMod.CtrlCmd : KeyMod.WinCtrl; break
      case "SHIFT": mods |= KeyMod.Shift; break
      case "ALT": mods |= KeyMod.Alt; break
      default: keyStr = p;
    }
  }

  const keyCode = KEY_MAP[keyStr]
  if (keyCode === undefined) return null
  return { mods, keyCode }
}

/** 序列化键盘事件为 mods+keyCode */
function eventToHash(e: KeyboardEvent): number {
  let mods = 0
  if (e.ctrlKey || e.metaKey) mods |= KeyMod.CtrlCmd
  if (e.shiftKey) mods |= KeyMod.Shift
  if (e.altKey) mods |= KeyMod.Alt

  const key = e.key.toUpperCase()
  const keyCode = KEY_MAP[key] ?? KEY_MAP[e.code.replace("Key", "").replace("Digit", "")] ?? KeyCode.Unknown
  return (mods << 16) | keyCode
}

// ── 全局状态 ──

const bindings = ref<Keybinding[]>([])
let pendingChord: number | null = null  // 等待和弦第二键
const contextStack: string[] = ["global"]

// ── 预定义快捷键 ──

const DEFAULT_BINDINGS: Keybinding[] = [
  // 全局
  { key: "Ctrl+Shift+P", action: () => toggleCommandPalette(), when: "global", priority: 10 },
  { key: "Ctrl+P", action: () => toggleQuickOpen(), when: "global", priority: 10 },
  { key: "F1", action: () => toggleCommandPalette(), when: "global", priority: 9 },
  // 编辑器
  { key: "Ctrl+S", action: () => saveFile(), when: "editor", priority: 10 },
  { key: "Ctrl+W", action: () => closeActiveTab(), when: "editor", priority: 10 },
  { key: "Ctrl+\\", action: () => splitEditorRight(), when: "editor", priority: 10 },
  { key: "Ctrl+Shift+E", action: () => focusFileExplorer(), when: "global", priority: 9 },
  { key: "Ctrl+`", action: () => toggleTerminal(), when: "global", priority: 9 },
  { key: "Ctrl+B", action: () => toggleSidebar(), when: "global", priority: 9 },
  { key: "Ctrl+J", action: () => toggleBottomPanel(), when: "global", priority: 9 },
  { key: "Ctrl+Shift+F", action: () => toggleGlobalSearch(), when: "global", priority: 10 },
  { key: "Ctrl+N", action: () => newUntitledFile(), when: "global", priority: 9 },
]

// ── 对外回调（由组件注册） ──

let _toggleCommandPalette: () => void = () => {}
let _toggleQuickOpen: () => void = () => {}
let _saveFile: () => void = () => {}
let _closeActiveTab: () => void = () => {}
let _splitEditorRight: () => void = () => {}
let _focusFileExplorer: () => void = () => {}
let _toggleTerminal: () => void = () => {}
let _toggleSidebar: () => void = () => {}
let _toggleBottomPanel: () => void = () => {}
let _toggleGlobalSearch: () => void = () => {}
let _newUntitledFile: () => void = () => {}

function toggleCommandPalette() { _toggleCommandPalette() }
function toggleQuickOpen() { _toggleQuickOpen() }
function saveFile() { _saveFile() }
function closeActiveTab() { _closeActiveTab() }
function splitEditorRight() { _splitEditorRight() }
function focusFileExplorer() { _focusFileExplorer() }
function toggleTerminal() { _toggleTerminal() }
function toggleSidebar() { _toggleSidebar() }
function toggleBottomPanel() { _toggleBottomPanel() }
function toggleGlobalSearch() { _toggleGlobalSearch() }
function newUntitledFile() { _newUntitledFile() }

/** 检测当前上下文是否匹配 when 条件 */
function contextMatches(actual: string, expected: string): boolean {
  if (expected === "global") return true
  return actual === expected || actual.startsWith(expected)
}

/** 核心事件处理 */
function handleKeydown(e: KeyboardEvent): void {
  // 在输入框/文本区域内不拦截（除非是全局快捷键）
  const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
  const isInput = tag === "input" || tag === "textarea" || tag === "select" || (e.target as HTMLElement)?.isContentEditable
  // Monaco 编辑器内部有自己的快捷键处理，我们在外部处理全局/面板级快捷键

  const hash = eventToHash(e)

  // 如果有等待的和弦第二键
  if (pendingChord !== null) {
    e.preventDefault()
    const matched = bindings.value
      .sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0))
      .find(b => b._chordFirst === pendingChord && b._chordSecond === hash && contextMatches(currentContext.value, b.when ?? "global"))
    pendingChord = null
    if (matched) {
      matched.action()
    }
    return
  }

  // 查找匹配的绑定
  const sorted = bindings.value
    .filter(b => !b.key.includes(" "))  // 非和弦
    .sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0))

  for (const binding of sorted) {
    if (!binding._chordFirst) continue
    if (binding._chordFirst !== hash) continue
    if (!contextMatches(currentContext.value, binding.when ?? "global")) continue

    e.preventDefault()
    e.stopPropagation()
    binding.action()
    return
  }

  // 查找和弦第一键
  const chordBindings = bindings.value.filter(b => b.key.includes(" "))
  for (const binding of chordBindings) {
    if (!binding._chordFirst) continue
    if (binding._chordFirst !== hash) continue
    if (!contextMatches(currentContext.value, binding.when ?? "global")) continue

    e.preventDefault()
    pendingChord = hash
    // 1 秒后超时清除
    setTimeout(() => { pendingChord = null }, 1000)
    return
  }
}

/**
 * 注册一个快捷键绑定
 * @param key 键字符串，如 "Ctrl+Shift+P" 或 "Ctrl+K Ctrl+D"
 * @param action 回调函数
 * @param when 上下文条件: "global" | "editor" | "terminal" | "sidebar"
 * @param priority 优先级，默认 0
 */
function register(key: string, action: () => void, when: string = "global", priority: number = 0): () => void {
  const binding: Keybinding = { key, action, when, priority }

  if (key.includes(" ")) {
    // 和弦序列: "Ctrl+K Ctrl+D"
    const parts = key.split(" ")
    const first = parseKeyChord(parts[0])
    const second = parseKeyChord(parts[1])
    if (first) binding._chordFirst = (first.mods << 16) | first.keyCode
    if (second) binding._chordSecond = (second.mods << 16) | second.keyCode
  } else {
    // 单键
    const parsed = parseKeyChord(key)
    if (parsed) binding._chordFirst = (parsed.mods << 16) | parsed.keyCode
  }

  bindings.value.push(binding)

  // 返回取消注册函数
  return () => {
    const idx = bindings.value.indexOf(binding)
    if (idx !== -1) bindings.value.splice(idx, 1)
  }
}

/** 取消注册所有绑定 */
function unregisterAll(): void {
  bindings.value = []
}

/** 设置当前上下文（由组件焦点变化时调用） */
function setContext(context: string): void {
  contextStack[0] = context
  currentContext.value = context
}

/** 推入上下文（进入编辑器区域等） */
function pushContext(context: string): void {
  contextStack.unshift(context)
  currentContext.value = context
}

/** 弹出上下文 */
function popContext(): void {
  contextStack.shift()
  currentContext.value = contextStack[0] ?? "global"
}

// ── 注册预定义快捷键的回调 ──

interface KeybindingCallbacks {
  toggleCommandPalette: () => void
  toggleQuickOpen: () => void
  saveFile: () => void
  closeActiveTab: () => void
  splitEditorRight: () => void
  focusFileExplorer: () => void
  toggleTerminal: () => void
  toggleSidebar: () => void
  toggleBottomPanel: () => void
  toggleGlobalSearch: () => void
  newUntitledFile: () => void
}

/** 注册预定义快捷键的回调 */
function registerCallbacks(cbs: Partial<KeybindingCallbacks>): void {
  if (cbs.toggleCommandPalette) _toggleCommandPalette = cbs.toggleCommandPalette
  if (cbs.toggleQuickOpen) _toggleQuickOpen = cbs.toggleQuickOpen
  if (cbs.saveFile) _saveFile = cbs.saveFile
  if (cbs.closeActiveTab) _closeActiveTab = cbs.closeActiveTab
  if (cbs.splitEditorRight) _splitEditorRight = cbs.splitEditorRight
  if (cbs.focusFileExplorer) _focusFileExplorer = cbs.focusFileExplorer
  if (cbs.toggleTerminal) _toggleTerminal = cbs.toggleTerminal
  if (cbs.toggleSidebar) _toggleSidebar = cbs.toggleSidebar
  if (cbs.toggleBottomPanel) _toggleBottomPanel = cbs.toggleBottomPanel
  if (cbs.toggleGlobalSearch) _toggleGlobalSearch = cbs.toggleGlobalSearch
  if (cbs.newUntitledFile) _newUntitledFile = cbs.newUntitledFile
}

// ── Composable ──

/** 全局单例状态 */
let _initialized = false

export function useKeybindingStore() {
  if (!_initialized) {
    _initialized = true
    // 注册默认快捷键
    for (const b of DEFAULT_BINDINGS) {
      const parsed = parseKeyChord(b.key)
      if (parsed) b._chordFirst = (parsed.mods << 16) | parsed.keyCode
      bindings.value.push(b)
    }
  }

  // 全局事件监听（只在客户端）
  if (typeof window !== "undefined") {
    window.removeEventListener("keydown", handleKeydown)
    window.addEventListener("keydown", handleKeydown)
  }

  return {
    register,
    registerCallbacks,
    unregisterAll,
    setContext,
    pushContext,
    popContext,
    currentContext,
    bindings,
  }
}
