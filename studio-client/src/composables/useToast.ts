/**
 * useToast — 全局轻量级 Toast 通知
 *
 * 不依赖外部 UI 库, 直接通过 DOM 注入到 document.body
 * 用于 ActivityBar 等组件的错误提示
 */
import { ref } from 'vue'

export interface ToastItem {
  id: number
  message: string
  type: 'info' | 'success' | 'warning' | 'error'
  duration: number
}

const toasts = ref<ToastItem[]>([])
let nextId = 1

function show(message: string, type: ToastItem['type'] = 'info', duration = 3000): number {
  const id = nextId++
  toasts.value.push({ id, message, type, duration })
  if (duration > 0) {
    setTimeout(() => dismiss(id), duration)
  }
  return id
}

function dismiss(id: number): void {
  const idx = toasts.value.findIndex((t) => t.id === id)
  if (idx >= 0) toasts.value.splice(idx, 1)
}

export function useToast() {
  return {
    toasts,
    show,
    info: (msg: string, dur?: number) => show(msg, 'info', dur),
    success: (msg: string, dur?: number) => show(msg, 'success', dur),
    warning: (msg: string, dur?: number) => show(msg, 'warning', dur),
    error: (msg: string, dur?: number) => show(msg, 'error', dur ?? 4000),
    dismiss,
  }
}
