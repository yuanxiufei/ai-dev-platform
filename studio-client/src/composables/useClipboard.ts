/**
 * useClipboard — 统一剪贴板操作 (含历史记录)
 *
 * 对标: vscode/src/vs/platform/clipboard/
 *
 * 用法:
 *   const clipboard = useClipboard()
 *   await clipboard.copy('hello')
 *   const text = await clipboard.read()
 *   clipboard.history.value  // ClipboardEntry[]
 */

import { ref } from 'vue'

export interface ClipboardEntry {
  text: string
  timestamp: number
  source: string  // 来源: 'copy' | 'cut' | 'external'
}

export function useClipboard(maxHistory = 50) {
  const history = ref<ClipboardEntry[]>([])
  const hasText = ref(false)
  const hasImage = ref(false)
  const lastOperation = ref<'copy' | 'cut' | 'paste' | ''>('')

  /** 写入剪贴板 */
  async function copy(text: string, source: string = 'copy'): Promise<boolean> {
    try {
      await navigator.clipboard.writeText(text)
      _addToHistory(text, source === 'cut' ? 'cut' : 'copy')
      lastOperation.value = 'copy'
      hasText.value = true
      return true
    } catch {
      return _fallbackCopy(text)
    }
  }

  /** 剪切 (复制 + 标记为 cut) */
  async function cut(text: string): Promise<boolean> {
    return copy(text, 'cut')
  }

  /** 读取剪贴板 */
  async function read(): Promise<string> {
    try {
      const text = await navigator.clipboard.readText()
      lastOperation.value = 'paste'
      return text
    } catch {
      return ''
    }
  }

  /** 粘贴到指定位置 (替换选中文本) */
  async function paste(getSelectedText: () => string, setText: (text: string) => void): Promise<boolean> {
    const text = await read()
    if (!text) return false
    setText(text)  // 调用者负责实现具体粘贴逻辑
    lastOperation.value = 'paste'
    return true
  }

  /** 检查剪贴板权限 */
  async function checkPermission(): Promise<boolean> {
    try {
      const result = await navigator.permissions.query({ name: 'clipboard-read' as any })
      return result.state === 'granted'
    } catch {
      return true // 大部分浏览器默认允许
    }
  }

  /** 检查是否有图片 */
  async function checkForImage(): Promise<boolean> {
    try {
      const items = await navigator.clipboard.read()
      for (const item of items) {
        if (item.types.some(t => t.startsWith('image/'))) {
          hasImage.value = true
          return true
        }
      }
    } catch { /* 静默 */ }
    hasImage.value = false
    return false
  }

  /** 读取图片 blob */
  async function readImage(): Promise<Blob | null> {
    try {
      const items = await navigator.clipboard.read()
      for (const item of items) {
        for (const type of item.types) {
          if (type.startsWith('image/')) {
            return await item.getType(type)
          }
        }
      }
    } catch { /* 静默 */ }
    return null
  }

  /** 历史记录 */
  function _addToHistory(text: string, source: string) {
    // 去重: 相同文本不重复添加
    const existing = history.value.find(e => e.text === text)
    if (existing) {
      existing.timestamp = Date.now()
      return
    }
    history.value.unshift({ text, timestamp: Date.now(), source })
    if (history.value.length > maxHistory) {
      history.value = history.value.slice(0, maxHistory)
    }
  }

  /** 清除历史 */
  function clearHistory() {
    history.value = []
  }

  /** 退回旧方案 (execCommand) */
  function _fallbackCopy(text: string): boolean {
    try {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
      _addToHistory(text, 'copy')
      hasText.value = true
      return true
    } catch {
      return false
    }
  }

  // 初始化: 检查剪贴板状态
  async function init() {
    try {
      const text = await navigator.clipboard.readText()
      hasText.value = text.length > 0
    } catch {
      hasText.value = false
    }
  }

  return {
    history, hasText, hasImage, lastOperation,
    copy, cut, read, paste,
    checkPermission, checkForImage, readImage,
    clearHistory, init,
  }
}
