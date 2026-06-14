import { ref } from "vue"

type ToastType = "success" | "error" | "info" | "warning"

interface ToastItem {
  id: number
  message: string
  type: ToastType
}

const toasts = ref<ToastItem[]>([])
let nextId = 0

export function toast(message: string, type: ToastType = "info") {
  const id = nextId++
  toasts.value.push({ id, message, type })
  setTimeout(() => {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }, 4000)
}

export function showSuccessToast(message: string) {
  toast(message, "success")
}

export function showErrorToast(message: string) {
  toast(message, "error")
}

export function useToast() {
  return { toasts, showSuccessToast, showErrorToast }
}
