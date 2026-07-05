/**
 * Session 57: Widget Navigation — 对标 VSCode widgetNavigationCommands (F6/Shift+F6)
 *
 * 焦点区域循环: Editor → StatusBar → Panel → Sidebar → AuxiliaryBar → Editor
 * 类似 VSCode focusPreviousWidget / focusNextWidget 命令
 */
import { ref, onMounted, onUnmounted, type Ref } from 'vue'

/** 可聚焦的 IDE 区域 ID */
export type FocusZone =
  | 'editor'
  | 'statusbar'
  | 'panel'
  | 'sidebar'
  | 'auxiliarybar'
  | 'activitybar'

/** 焦点区域顺序 (F6 正向 / Shift+F6 反向) */
const FOCUS_ZONE_ORDER: FocusZone[] = [
  'editor',
  'statusbar',
  'panel',
  'sidebar',
  'activitybar',
  'auxiliarybar',
]

/** 区域注册信息 */
interface ZoneRegistration {
  id: FocusZone
  getFocusableEl: () => HTMLElement | null
}

const zones: Map<FocusZone, ZoneRegistration> = new Map()
export const activeFocusZone: Ref<FocusZone | null> = ref(null)

/** 注册一个可焦点区域 */
export function registerFocusZone(
  id: FocusZone,
  getFocusableEl: () => HTMLElement | null,
): () => void {
  zones.set(id, { id, getFocusableEl })
  return () => { zones.delete(id) }
}

/** 聚焦下一个区域 (F6) */
export function focusNextZone(): void {
  const currentIdx = activeFocusZone.value
    ? FOCUS_ZONE_ORDER.indexOf(activeFocusZone.value)
    : -1

  const start = currentIdx + 1
  for (let i = 0; i < FOCUS_ZONE_ORDER.length; i++) {
    const idx = (start + i) % FOCUS_ZONE_ORDER.length
    const zoneId = FOCUS_ZONE_ORDER[idx]
    const reg = zones.get(zoneId)
    const el = reg?.getFocusableEl()
    if (el) {
      el.focus()
      activeFocusZone.value = zoneId
      return
    }
  }
}

/** 聚焦上一个区域 (Shift+F6) */
export function focusPreviousZone(): void {
  const currentIdx = activeFocusZone.value
    ? FOCUS_ZONE_ORDER.indexOf(activeFocusZone.value)
    : FOCUS_ZONE_ORDER.length

  const start = currentIdx - 1
  for (let i = 0; i < FOCUS_ZONE_ORDER.length; i++) {
    const idx = ((start - i) % FOCUS_ZONE_ORDER.length + FOCUS_ZONE_ORDER.length) % FOCUS_ZONE_ORDER.length
    const zoneId = FOCUS_ZONE_ORDER[idx]
    const reg = zones.get(zoneId)
    const el = reg?.getFocusableEl()
    if (el) {
      el.focus()
      activeFocusZone.value = zoneId
      return
    }
  }
}

/** 使指定区域获得焦点 */
export function focusZone(id: FocusZone): void {
  const reg = zones.get(id)
  const el = reg?.getFocusableEl()
  if (el) {
    el.focus()
    activeFocusZone.value = id
  }
}

/**
 * Composable: 在组件中使用 Widget 导航
 * 用法:
 *   const { focusZoneRef } = useWidgetNavigation('editor', containerRef)
 *   然后在模板中: <div ref="containerRef" tabindex="-1">
 */
export function useWidgetNavigation(
  zoneId: FocusZone,
  elRef: Ref<HTMLElement | null>,
) {
  let unregister: (() => void) | null = null

  const focusZoneRef = (el: HTMLElement | null) => {
    if (!el) return
    // 设置 tabindex 确保可编程聚焦
    el.setAttribute('tabindex', '-1')
    el.style.outline = 'none'

    const handleFocus = () => { activeFocusZone.value = zoneId }
    const handleBlur = () => { if (activeFocusZone.value === zoneId) activeFocusZone.value = null }

    el.addEventListener('focus', handleFocus)
    el.addEventListener('blur', handleBlur)

    unregister = registerFocusZone(zoneId, () => document.contains(el) ? el : null)

    // 清理
    return () => {
      el.removeEventListener('focus', handleFocus)
      el.removeEventListener('blur', handleBlur)
      unregister?.()
    }
  }

  onMounted(() => {
    if (elRef.value) {
      focusZoneRef(elRef.value)
    }
  })

  onUnmounted(() => {
    unregister?.()
  })

  return { activeFocusZone, focusZone: (id: FocusZone) => focusZone(id) }
}

/**
 * 全局键盘监听 F6/Shift+F6
 * 应在 App.vue 中调用 setupWidgetNavigationKeyboard()
 */
let cleanupHandler: (() => void) | null = null

export function setupWidgetNavigationKeyboard(): void {
  if (cleanupHandler) return

  const handler = (e: KeyboardEvent) => {
    // F6: forward, Shift+F6: backward
    if (e.key === 'F6' && !e.ctrlKey && !e.altKey && !e.metaKey) {
      e.preventDefault()
      if (e.shiftKey) {
        focusPreviousZone()
      } else {
        focusNextZone()
      }
    }
  }

  window.addEventListener('keydown', handler, true)
  cleanupHandler = () => window.removeEventListener('keydown', handler, true)
}

export function teardownWidgetNavigationKeyboard(): void {
  cleanupHandler?.()
  cleanupHandler = null
}
