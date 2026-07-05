/**
 * useSyncScroll — VSCode scrollLocking / 同步滚动
 *
 * 对标 VSCode workbench/contrib/scrollLocking: SyncScroll
 * 让所有可见的编辑器面板同步滚动。当你滚动其中一个编辑器时，
 * 其它所有可见编辑器也会按相同的偏移量同步滚动。
 *
 * 工作机制:
 *   1. 激活时记录每个编辑器的初始 scrollTop
 *   2. 任意编辑器滚动时，计算偏移差
 *   3. 将其他编辑器的 scrollTop 设为 初始值 + 偏移差
 */
import { ref, type Ref } from "vue"

/** 编辑器引用包装 */
interface EditorRef {
  /** 编辑器实例 ID (用于去重) */
  id: string
  /** 获取当前 scrollTop */
  getScrollTop: () => number
  /** 设置 scrollTop */
  setScrollTop: (top: number) => void
  /** 订阅滚动事件，返回取消订阅函数 */
  onScroll: (cb: () => void) => () => void
}

/** 同步滚动管理器（模块级单例） */
const _registry: EditorRef[] = []
const _initialScrollTop = new Map<string, number>()
let _isActive = false
const _disposers: Array<() => void> = []
/** 防重入：防止因同步滚动触发重复回调 */
let _reentrancyGuard = false

/** 全局激活状态 */
export const syncScrollActive = ref(false)

/**
 * 注册编辑器到同步滚动管理器。
 * 在编辑器 mounted 时调用。
 */
export function registerSyncScrollEditor(editorRef: EditorRef): void {
  // 去重：先移除同 ID 的旧注册
  const idx = _registry.findIndex((e) => e.id === editorRef.id)
  if (idx !== -1) _registry.splice(idx, 1)
  _registry.push(editorRef)

  // 如果当前正在同步，立即绑定
  if (_isActive) _bindEditorScroll(editorRef)
}

/**
 * 取消注册编辑器。
 * 在编辑器 unmounted 时调用。
 */
export function unregisterSyncScrollEditor(editorId: string): void {
  const idx = _registry.findIndex((e) => e.id === editorId)
  if (idx !== -1) _registry.splice(idx, 1)
}

/** 为单个编辑器绑定滚动监听 */
function _bindEditorScroll(editorRef: EditorRef): void {
  // 记录初始滚动位置
  _initialScrollTop.set(editorRef.id, editorRef.getScrollTop())

  const dispose = editorRef.onScroll(() => {
    if (_reentrancyGuard || !_isActive) return
    _reentrancyGuard = true

    try {
      const scrolledId = editorRef.id
      const initialTop = _initialScrollTop.get(scrolledId)
      if (initialTop === undefined) {
        _initialScrollTop.set(scrolledId, editorRef.getScrollTop())
        return
      }

      const currentTop = editorRef.getScrollTop()
      const delta = currentTop - initialTop

      // 同步其他所有编辑器
      for (const other of _registry) {
        if (other.id === scrolledId) continue
        const otherInitial = _initialScrollTop.get(other.id)
        if (otherInitial === undefined) {
          _initialScrollTop.set(other.id, other.getScrollTop())
          continue
        }
        const targetTop = otherInitial + delta
        if (Math.abs(other.getScrollTop() - targetTop) > 1) {
          other.setScrollTop(targetTop)
        }
      }
    } finally {
      _reentrancyGuard = false
    }
  })

  _disposers.push(dispose)
}

/** 激活同步滚动 */
export function activateSyncScroll(): void {
  if (_isActive) return
  _isActive = true
  syncScrollActive.value = true

  for (const editorRef of _registry) {
    _bindEditorScroll(editorRef)
  }
}

/** 停用同步滚动 */
export function deactivateSyncScroll(): void {
  if (!_isActive) return
  _isActive = false
  syncScrollActive.value = false

  // 取消所有滚动订阅
  for (const dispose of _disposers) {
    try { dispose() } catch { /* noop */ }
  }
  _disposers.length = 0
  _initialScrollTop.clear()
}

/** 切换同步滚动 */
export function toggleSyncScroll(): void {
  if (_isActive) deactivateSyncScroll()
  else activateSyncScroll()
}

/**
 * useSyncScroll — Vue composable 版本。
 * 返回用于集成到组件中的状态和方法。
 */
export function useSyncScroll() {
  return {
    /** 同步滚动是否激活 */
    isActive: syncScrollActive,
    /** 注册编辑器 */
    register: registerSyncScrollEditor,
    /** 取消注册编辑器 */
    unregister: unregisterSyncScrollEditor,
    /** 激活同步 */
    activate: activateSyncScroll,
    /** 停用同步 */
    deactivate: deactivateSyncScroll,
    /** 切换同步 */
    toggle: toggleSyncScroll,
  }
}
