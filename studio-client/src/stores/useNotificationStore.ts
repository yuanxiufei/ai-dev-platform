// ============================================
// Notification Store — VSCode-style notification system
// ============================================
import { defineStore } from 'pinia'
import { ref } from 'vue'

export interface Notification {
  id: string
  type: 'info' | 'warning' | 'error' | 'success'
  message: string
  detail?: string
  source?: string
  actions?: NotificationAction[]
  autoDismiss?: number // ms, 0 = no auto-dismiss
  dismissed?: boolean
  timestamp: number
}

export interface NotificationAction {
  label: string
  primary?: boolean
  action: () => void
}

export const useNotificationStore = defineStore('notifications', () => {
  const notifications = ref<Notification[]>([])
  const showNotificationPanel = ref(false)
  // Track dismissed for badge count
  const historyCount = ref(0)

  let idCounter = 0

  function add(
    message: string,
    type: Notification['type'] = 'info',
    opts?: {
      detail?: string
      source?: string
      actions?: NotificationAction[]
      autoDismiss?: number
    }
  ): string {
    const id = `notif_${Date.now()}_${++idCounter}`
    const n: Notification = {
      id,
      type,
      message,
      detail: opts?.detail,
      source: opts?.source,
      actions: opts?.actions,
      autoDismiss: opts?.autoDismiss ?? (type === 'error' ? 8000 : 5000),
      dismissed: false,
      timestamp: Date.now(),
    }
    notifications.value.push(n)

    // Limit stack to 10
    if (notifications.value.length > 10) {
      dismiss(notifications.value[0].id)
    }

    // Auto-dismiss
    if (n.autoDismiss && n.autoDismiss > 0) {
      setTimeout(() => dismiss(id), n.autoDismiss)
    }

    return id
  }

  function dismiss(id: string) {
    const n = notifications.value.find(x => x.id === id)
    if (n) {
      n.dismissed = true
      historyCount.value++
      // Remove after animation
      setTimeout(() => {
        notifications.value = notifications.value.filter(x => x.id !== id)
      }, 300)
    }
  }

  function dismissAll() {
    notifications.value.forEach(n => { n.dismissed = true })
    setTimeout(() => { notifications.value = [] }, 300)
  }

  function clearHistory() {
    historyCount.value = 0
  }

  function info(msg: string, opts?: any) { return add(msg, 'info', opts) }
  function warn(msg: string, opts?: any) { return add(msg, 'warning', opts) }
  function error(msg: string, opts?: any) { return add(msg, 'error', opts) }
  function success(msg: string, opts?: any) { return add(msg, 'success', opts) }

  const activeCount = () => notifications.value.filter(n => !n.dismissed).length

  return {
    notifications, showNotificationPanel, historyCount,
    add, dismiss, dismissAll, clearHistory,
    info, warn, error, success, activeCount,
  }
})
