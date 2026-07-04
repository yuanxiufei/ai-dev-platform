/**
 * useInputDialog — 全局输入对话框命令式 API
 *
 * 在任何组件中直接调用:
 *   import { inputDialog } from '@/composables/useInputDialog'
 *   const name = await inputDialog({ title: '文件名', placeholder: '请输入' })
 */
import { ref } from "vue"

export interface InputDialogOptions {
  title?: string
  placeholder?: string
  defaultValue?: string
  confirmText?: string
  cancelText?: string
  validator?: (value: string) => string | null
}

// ── 全局响应式状态 (由 InputDialogHost 绑定) ──
export const dlgOpen = ref(false)
export const dlgOpts = ref<InputDialogOptions>({})
export const dlgValue = ref("")
export const dlgError = ref<string | null>(null)

let resolver: ((v: string | null) => void) | null = null

export function inputDialog(options: InputDialogOptions = {}): Promise<string | null> {
  return new Promise((resolve) => {
    resolver = resolve
    dlgOpts.value = options
    dlgValue.value = options.defaultValue ?? ""
    dlgError.value = null
    dlgOpen.value = true
  })
}

export function confirmDialog(v: string): void {
  dlgOpen.value = false
  resolver?.(v)
  resolver = null
}

export function cancelDialog(): void {
  dlgOpen.value = false
  resolver?.(null)
  resolver = null
}
