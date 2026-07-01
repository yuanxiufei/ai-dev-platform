/**
 * useChatScroll.ts — 智能滚动组合函数 (参考 Cline useScrollBehavior + Continue auto-scroll)
 *
 * 核心策略:
 *   1. 新消息到达时 → 自动滚到底部 (smooth scroll)
 *   2. 用户手动向上滚动 → 暂停自动滚动 (disableAutoScroll)
 *   3. 用户手动滚到底部 → 恢复自动滚动
 *   4. 新 turn 开始 → 强制恢复自动滚动
 *   5. 双重保险: smooth scroll + 延迟 instant scroll (参考 Cline 40ms/70ms)
 *   6. 流式内容更新 (content growth) → 如果允许则跟随滚动
 */
import { nextTick, onBeforeUnmount, ref, type Ref } from "vue"

export interface UseChatScrollOptions {
  /** 滚动容器 ref */
  containerRef: Ref<HTMLElement | null>
  /** 内容变化时的触发源 (messages 长度, content 文本等) */
  contentDeps: () => unknown[]
  /** 距底部多少像素视为"在底部" (默认 80px, Continue atBottomThreshold=10) */
  bottomThreshold?: number
  /** 平滑滚动后的 instant 修正延迟 (ms, 默认 [40, 70]) */
  snapDelays?: number[]
  /** 是否启用自动滚动 (默认 true) */
  enabled?: Ref<boolean>
}

export interface UseChatScrollReturn {
  /** 是否在底部 */
  isAtBottom: Ref<boolean>
  /** 是否已禁用自动滚动 (用户手动上滚) */
  isAutoScrollDisabled: Ref<boolean>
  /** 平滑滚动到底部 */
  scrollToBottom: (behavior?: ScrollBehavior) => void
  /** 强制启用自动滚动 (新 turn 开始时调用) */
  forceEnableAutoScroll: () => void
  /** 滚动到底部 (仅在 auto-scroll 未禁用时) */
  scrollIfNeeded: () => void
}

export function useChatScroll(options: UseChatScrollOptions): UseChatScrollReturn {
  const {
    containerRef,
    contentDeps,
    bottomThreshold = 80,
    snapDelays = [40, 70],
    enabled = ref(true),
  } = options

  const isAtBottom = ref(true)
  const isAutoScrollDisabled = ref(false)

  // ── 检查是否在底部 ──
  const checkIfAtBottom = (): boolean => {
    const el = containerRef.value
    if (!el) return true
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
    return distanceFromBottom <= bottomThreshold
  }

  // ── 平滑滚动到底部 ──
  const scrollToBottom = (behavior: ScrollBehavior = "smooth") => {
    const el = containerRef.value
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior })
    isAtBottom.value = true
  }

  // ── 强制启用自动滚动 ──
  const forceEnableAutoScroll = () => {
    isAutoScrollDisabled.value = false
    nextTick(() => scrollToBottom("instant"))
  }

  // ── 仅在允许时滚动 ──
  const scrollIfNeeded = () => {
    if (!enabled.value) return
    if (isAutoScrollDisabled.value) return
    // 平滑滚动
    scrollToBottom("smooth")
    // 双重保险: 延迟 instant snap (参考 Cline)
    snapDelays.forEach((delay) => {
      setTimeout(() => {
        if (!isAutoScrollDisabled.value && enabled.value) {
          scrollToBottom("instant")
        }
      }, delay)
    })
  }

  // ── 监听用户滚动 ──
  let wheelTimer: ReturnType<typeof setTimeout> | null = null

  const handleWheel = (e: WheelEvent) => {
    if (!containerRef.value?.contains(e.target as Node)) return
    // 向上滚动 → 禁用自动滚动
    if (e.deltaY < 0) {
      isAutoScrollDisabled.value = true
      if (wheelTimer) clearTimeout(wheelTimer)
      // 3s 后如果滚到底了，自动恢复 (Continue 风格)
      wheelTimer = setTimeout(() => {
        if (checkIfAtBottom()) {
          isAutoScrollDisabled.value = false
        }
      }, 3000)
    }
    // 检查是否滚到底部
    requestAnimationFrame(() => {
      isAtBottom.value = checkIfAtBottom()
      if (isAtBottom.value) {
        isAutoScrollDisabled.value = false
      }
    })
  }

  // ── 监听内容变化 → 自动滚动 ──
  const contentWatcher = () => {
    void contentDeps()
    if (!enabled.value || isAutoScrollDisabled.value) return
    nextTick(() => scrollIfNeeded())
  }

  // ── 生命周期 ──
  const setup = () => {
    window.addEventListener("wheel", handleWheel, { passive: true })
  }
  const teardown = () => {
    window.removeEventListener("wheel", handleWheel)
    if (wheelTimer) clearTimeout(wheelTimer)
  }

  setup()
  onBeforeUnmount(teardown)

  return {
    isAtBottom,
    isAutoScrollDisabled,
    scrollToBottom,
    forceEnableAutoScroll,
    scrollIfNeeded,
  }
}
