/**
 * Context Key Store — VS Code 风格 when 条件求值
 *
 * 对标: vscode/src/vs/platform/contextkey/
 *
 * 用法:
 *   const ctxKey = useCtxStore()
 *   await ctxKey.setKey('editorLangId', 'python')
 *   const show = ctxKey.evaluate('editorLangId == "python" && editorHasSelection')
 *
 * 在模板中 (条件渲染):
 *   <div v-if="ctxKey.when('editorLangId == \"python\"')">Python 专属面板</div>
 */

import { defineStore } from 'pinia'
import { ref, computed, reactive } from 'vue'
import { useIDEStore } from './useIDEStore'
import * as ctxApi from '@/api/contextKeys'

export const useCtxStore = defineStore('contextKeys', () => {
  // ---- State ----
  const workspaceId = ref('default')
  const keys = reactive<Record<string, any>>({})
  const initialized = ref(false)
  const syncing = ref(false)

  // 初始化默认值
  function _initDefaults() {
    const defaults: Record<string, any> = {
      isMac: _isMac(),
      isLinux: !_isMac() && !_isWin(),
      isWindows: _isWin(),
      isWeb: true,
      editorHasSelection: false,
      editorHasMultipleSelections: false,
      editorReadonly: false,
      editorLangId: 'plaintext',
      editorHasCodeActions: false,
      editorHasDiagnostics: false,
      editorTabFocusMode: false,
      terminalFocus: false,
      sideBarVisible: true,
      panelVisible: false,
      zenMode: false,
      inDebugMode: false,
      debugState: 'stopped',
      gitOpenRepositoryCount: 0,
      activeEditorIsModified: false,
      activeEditorIsPreview: false,
      resourceExtname: '',
      resourceFilename: '',
      resourceLangId: 'plaintext',
      workspaceFolderCount: 1,
      listFocus: false,
      inputFocus: false,
      textInputFocus: false,
      explorerViewletVisible: true,
      extensionsViewletVisible: false,
      searchViewletVisible: false,
    }
    Object.assign(keys, defaults)
    _syncPlatformKeys()
  }

  function _isMac() { return navigator.platform.toUpperCase().includes('MAC') }
  function _isWin() { return navigator.platform.toUpperCase().includes('WIN') }

  // ---- Init ----

  async function init(wsId?: string) {
    if (wsId) workspaceId.value = wsId
    _initDefaults()

    // 从后端加载已持久化的 keys
    try {
      const snapshot = await ctxApi.getContextKeys(workspaceId.value)
      if (snapshot.keys) {
        Object.assign(keys, snapshot.keys)
      }
    } catch {
      // 后端不可用时使用默认值
    }
    initialized.value = true
  }

  // ---- Sync with editor changes ----

  function _syncPlatformKeys() {
    keys.isMac = _isMac()
    keys.isLinux = !_isMac() && !_isWin()
    keys.isWindows = _isWin()
  }

  /** 当编辑器状态变化时调用 (从 useIDEStore 或其他地方) */
  function syncEditorState(state: {
    langId?: string
    hasSelection?: boolean
    hasMultiSelections?: boolean
    readonly?: boolean
    isModified?: boolean
    resourceExt?: string
    resourceFilename?: string
    resourcePath?: string
  }) {
    if (state.langId !== undefined) {
      keys.editorLangId = state.langId
      keys.resourceLangId = state.langId
    }
    if (state.hasSelection !== undefined) keys.editorHasSelection = state.hasSelection
    if (state.hasMultiSelections !== undefined) keys.editorHasMultipleSelections = state.hasMultiSelections
    if (state.readonly !== undefined) keys.editorReadonly = state.readonly
    if (state.isModified !== undefined) keys.activeEditorIsModified = state.isModified
    if (state.resourceExt !== undefined) keys.resourceExtname = state.resourceExt
    if (state.resourceFilename !== undefined) keys.resourceFilename = state.resourceFilename
    if (state.resourcePath !== undefined) {
      keys.resourcePath = state.resourcePath
      // 从路径提取目录名
      const lastSlash = state.resourcePath.lastIndexOf('/')
      keys.resourceDirname = lastSlash > 0 ? state.resourcePath.slice(0, lastSlash) : ''
    }

    // 可选同步到后端
    syncToBackend(state).catch(() => {})
  }

  /** 同步调试状态 */
  function syncDebugState(state: 'stopped' | 'running' | 'paused') {
    keys.debugState = state
    keys.inDebugMode = state !== 'stopped'
  }

  /** 同步 Git 状态 */
  function syncGitState(repoCount: number) {
    keys.gitOpenRepositoryCount = repoCount
  }

  // ---- Key management ----

  function setKey(key: string, value: any, persist = false) {
    keys[key] = value
    if (persist) {
      ctxApi.setContextKey(workspaceId.value, key, value, true).catch(() => {})
    }
  }

  function getKey(key: string): any {
    return keys[key]
  }

  function hasKey(key: string): boolean {
    return key in keys
  }

  function deleteKey(key: string) {
    delete keys[key]
    ctxApi.deleteContextKey(workspaceId.value, key).catch(() => {})
  }

  // ---- When 子句求值 (纯前端实现) ----

  /**
   * 求值 when 子句
   *
   * 支持语法:
   *   - 逻辑: &&, ||, !, ()
   *   - 比较: ==, !=, >, <, >=, <=
   *   - 集合: in, not in
   *   - 正则: =~
   */
  function evaluate(when: string): boolean {
    if (!when || !when.trim()) return true
    try {
      return _parseOr(when)
    } catch {
      return false
    }
  }

  /** 对 when 子句求值并返回布尔值 (用于 v-if 绑定) */
  function when(whenClause: string): boolean {
    return evaluate(whenClause)
  }

  /** 后端求值 (用于复杂表达式或需后端状态) */
  async function evaluateRemote(whenClause: string): Promise<boolean> {
    try {
      const result = await ctxApi.evaluateWhen(workspaceId.value, whenClause)
      return result.result
    } catch {
      return evaluate(whenClause) // 后端不可用时回退到本地求值
    }
  }

  // ---- Backend sync ----

  async function syncToBackend(state?: Record<string, any>) {
    if (syncing.value) return
    syncing.value = true
    try {
      if (state) {
        await ctxApi.updateEditorState(workspaceId.value, state as any)
      } else {
        await ctxApi.setContextKeys(workspaceId.value, { ...keys })
      }
    } catch {
      // 静默失败
    } finally {
      syncing.value = false
    }
  }

  // ---- When clause parser (recursive descent) ----

  let _tokens: { type: string; value: any }[] = []
  let _pos = 0

  function _tokenize(source: string) {
    _tokens = []
    let i = 0
    const s = source
    while (i < s.length) {
      if (/\s/.test(s[i])) { i++; continue }
      if (s.startsWith('&&', i)) { _tokens.push({ type: '&&', value: null }); i += 2; continue }
      if (s.startsWith('||', i)) { _tokens.push({ type: '||', value: null }); i += 2; continue }
      if (s.startsWith('!=', i)) { _tokens.push({ type: '!=', value: null }); i += 2; continue }
      if (s.startsWith('==', i)) { _tokens.push({ type: '==', value: null }); i += 2; continue }
      if (s.startsWith('>=', i)) { _tokens.push({ type: '>=', value: null }); i += 2; continue }
      if (s.startsWith('<=', i)) { _tokens.push({ type: '<=', value: null }); i += 2; continue }
      if (s.startsWith('=~', i)) { _tokens.push({ type: '=~', value: null }); i += 2; continue }
      if (s.startsWith('not in', i)) { _tokens.push({ type: 'not in', value: null }); i += 6; continue }
      if (s.startsWith('in ', i)) { _tokens.push({ type: 'in', value: null }); i += 3; continue }
      if (s[i] === '!') { _tokens.push({ type: '!', value: null }); i++; continue }
      if (s[i] === '(') { _tokens.push({ type: '(', value: null }); i++; continue }
      if (s[i] === ')') { _tokens.push({ type: ')', value: null }); i++; continue }
      if (s[i] === '>' || s[i] === '<') { _tokens.push({ type: s[i], value: null }); i++; continue }

      // 字符串
      if (s[i] === "'" || s[i] === '"') {
        const q = s[i]; let j = i + 1
        while (j < s.length && s[j] !== q) j++
        _tokens.push({ type: 'string', value: s.slice(i + 1, j) })
        i = j + 1; continue
      }
      // true/false/null
      if (s.slice(i).startsWith('true')) { _tokens.push({ type: 'bool', value: true }); i += 4; continue }
      if (s.slice(i).startsWith('false')) { _tokens.push({ type: 'bool', value: false }); i += 5; continue }
      if (s.slice(i).startsWith('null')) { _tokens.push({ type: 'null', value: null }); i += 4; continue }
      // 数字
      const numMatch = s.slice(i).match(/^-?\d+(\.\d+)?/)
      if (numMatch) {
        _tokens.push({ type: 'number', value: parseFloat(numMatch[0]) })
        i += numMatch[0].length; continue
      }
      // 键名
      const keyMatch = s.slice(i).match(/^[a-zA-Z_][a-zA-Z0-9_.]*/)
      if (keyMatch) {
        _tokens.push({ type: 'key', value: keyMatch[0] })
        i += keyMatch[0].length; continue
      }
      i++ // 跳过无法识别的字符
    }
    _pos = 0
  }

  function _peek() { return _pos < _tokens.length ? _tokens[_pos] : null }
  function _advance() { return _pos < _tokens.length ? _tokens[_pos++] : null }
  function _match(...types: string[]) { if (_peek() && types.includes(_peek()!.type)) return _advance(); return null }

  function _parseOr(src: string): boolean {
    _tokenize(src)
    return _parseOrExpr()
  }

  function _parseOrExpr(): boolean {
    let left = _parseAndExpr()
    while (_match('||')) left = left || _parseAndExpr()
    return left
  }

  function _parseAndExpr(): boolean {
    let left = _parseNotExpr()
    while (_match('&&')) left = left && _parseNotExpr()
    return left
  }

  function _parseNotExpr(): boolean {
    if (_match('!')) return !_parseNotExpr()
    return _parsePrimary()
  }

  function _parsePrimary(): boolean {
    if (_match('(')) {
      const result = _parseOrExpr()
      _match(')')
      return result
    }
    return _parseComparison()
  }

  function _parseComparison(): boolean {
    const leftVal = _parseValue()
    if (leftVal === undefined) {
      _skipComparison()
      return false
    }
    const op = _peek()
    if (op && ['==', '!=', '>', '<', '>=', '<=', 'in', 'not in', '=~'].includes(op.type)) {
      _advance()
      const rightVal = _parseValue()
      return _applyOp(op.type, leftVal, rightVal)
    }
    return Boolean(leftVal)
  }

  function _skipComparison() {
    const t = _peek()
    if (t && ['==', '!=', '>', '<', '>=', '<=', 'in', 'not in', '=~'].includes(t.type)) {
      _advance()
      _parseValue()
    }
  }

  function _parseValue(): any {
    const t = _advance()
    if (!t) return undefined
    if (t.type === 'key') return keys[t.value]
    if (t.type === 'string' || t.type === 'number' || t.type === 'bool' || t.type === 'null') return t.value
    return undefined
  }

  function _applyOp(op: string, left: any, right: any): boolean {
    try {
      switch (op) {
        case '==': return left == right
        case '!=': return left != right
        case '>': return Number(left) > Number(right)
        case '<': return Number(left) < Number(right)
        case '>=': return Number(left) >= Number(right)
        case '<=': return Number(left) <= Number(right)
        case 'in': {
          if (Array.isArray(right)) return right.includes(left)
          if (typeof right === 'string' && typeof left === 'string') return right.includes(left)
          return false
        }
        case 'not in': {
          if (Array.isArray(right)) return !right.includes(left)
          if (typeof right === 'string' && typeof left === 'string') return !right.includes(left)
          return true
        }
        case '=~':
          try { return new RegExp(String(right)).test(String(left ?? '')) } catch { return false }
        default: return false
      }
    } catch { return false }
  }

  return {
    workspaceId, keys, initialized,
    init, evaluate, when, evaluateRemote, getKey, setKey, hasKey, deleteKey,
    syncEditorState, syncDebugState, syncGitState, syncToBackend,
  }
})
