<script setup lang="ts">
import { cn } from '@/lib/utils'
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from 'lucide-vue-next'
import type { Ref } from 'vue'

interface ToastItem {
  id: number
  message: string
  type: 'success' | 'error' | 'info' | 'warning'
}

defineProps<{
  toasts: ToastItem[]
}>()

const icons: Record<string, any> = {
  success: CheckCircle,
  error: AlertCircle,
  info: Info,
  warning: AlertTriangle,
}

const colors: Record<string, string> = {
  success: 'border-green-500 bg-green-50 dark:bg-green-950 text-green-800 dark:text-green-200',
  error: 'border-red-500 bg-red-50 dark:bg-red-950 text-red-800 dark:text-red-200',
  info: 'border-blue-500 bg-blue-50 dark:bg-blue-950 text-blue-800 dark:text-blue-200',
  warning: 'border-yellow-500 bg-yellow-50 dark:bg-yellow-950 text-yellow-800 dark:text-yellow-200',
}
</script>

<template>
  <div class="fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
    <TransitionGroup name="toast">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        :class="cn(
          'flex items-center gap-2 rounded-lg border px-4 py-3 shadow-lg text-sm min-w-[280px] max-w-[400px]',
          colors[toast.type],
        )"
      >
        <Component :is="icons[toast.type]" class="h-4 w-4 shrink-0" />
        <span class="flex-1">{{ toast.message }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-enter-active {
  transition: all 0.3s ease-out;
}
.toast-leave-active {
  transition: all 0.2s ease-in;
}
.toast-enter-from {
  opacity: 0;
  transform: translateX(30px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateX(30px);
}
</style>
