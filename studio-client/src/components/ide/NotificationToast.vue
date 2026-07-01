<script setup lang="ts">
/**
 * CodeBuddy IDE — Notification Toasts (VSCode-style)
 * Slide-in from bottom-right, auto-dismiss, action buttons
 */
import { computed } from 'vue'
import { useNotificationStore, type Notification } from '@/stores/useNotificationStore'
import { AlertCircle, AlertTriangle, CheckCircle2, Info, X, Bell } from 'lucide-vue-next'

const store = useNotificationStore()

const visibleNotifications = computed(() =>
  store.notifications.filter(n => !n.dismissed).slice(0, 8)
)

const iconMap = {
  error: AlertCircle,
  warning: AlertTriangle,
  success: CheckCircle2,
  info: Info,
}

const colorMap = {
  error: { bg: 'rgba(244,135,113,0.08)', border: 'var(--color-ide-error)', icon: 'var(--color-ide-error)' },
  warning: { bg: 'rgba(204,167,0,0.08)', border: 'var(--color-ide-warning)', icon: 'var(--color-ide-warning)' },
  success: { bg: 'rgba(78,201,176,0.08)', border: 'var(--color-ide-success)', icon: 'var(--color-ide-success)' },
  info: { bg: 'rgba(117,190,255,0.08)', border: 'var(--color-ide-info)', icon: 'var(--color-ide-info)' },
}

function timeAgo(ts: number): string {
  const diff = Date.now() - ts
  if (diff < 60e3) return '刚刚'
  if (diff < 3600e3) return `${Math.floor(diff / 60e3)} 分钟前`
  return `${Math.floor(diff / 3600e3)} 小时前`
}
</script>

<template>
  <!-- Toast stack (bottom-right) -->
  <div class="fixed bottom-10 right-4 z-[9000] flex flex-col-reverse gap-2 max-w-[420px]">
    <TransitionGroup name="toast">
      <div v-for="n in visibleNotifications" :key="n.id"
        class="notification-toast rounded-lg border overflow-hidden shadow-xl backdrop-blur-sm"
        :style="{
          background: colorMap[n.type].bg,
          borderColor: colorMap[n.type].border,
          boxShadow: `0 4px 16px rgba(0,0,0,0.4), 0 0 0 0.5px ${colorMap[n.type].border}33`,
        }">
        <div class="flex items-start gap-2.5 px-3 py-2.5">
          <!-- Icon -->
          <component :is="iconMap[n.type]" :size="16" class="shrink-0 mt-0.5"
            :style="{ color: colorMap[n.type].icon }" />

          <!-- Content -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <p class="text-[12px] font-medium text-[var(--color-ide-text)]">{{ n.message }}</p>
              <span v-if="n.source" class="text-[9px] text-[var(--color-ide-text-dim)] opacity-50">{{ n.source }}</span>
            </div>
            <p v-if="n.detail" class="text-[11px] text-[var(--color-ide-text-dim)] mt-0.5">{{ n.detail }}</p>

            <!-- Actions -->
            <div v-if="n.actions && n.actions.length" class="flex items-center gap-2 mt-1.5">
              <button v-for="act in n.actions" :key="act.label"
                class="text-[10px] px-2 py-0.5 rounded font-medium transition-colors"
                :class="act.primary
                  ? 'bg-[var(--color-ide-accent)]/20 text-[var(--color-ide-accent)] hover:bg-[var(--color-ide-accent)]/30'
                  : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)]'"
                @click="act.action(); store.dismiss(n.id)">
                {{ act.label }}
              </button>
            </div>
          </div>

          <!-- Close -->
          <button class="shrink-0 p-0.5 rounded text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
            @click="store.dismiss(n.id)">
            <X :size="12" />
          </button>
        </div>
      </div>
    </TransitionGroup>
  </div>

  <!-- Notification center panel (click bell to open) -->
  <Teleport to="body">
    <Transition name="slide-down">
      <div v-if="store.showNotificationPanel"
        class="fixed top-9 right-4 z-[9100] w-[360px] max-h-[480px] overflow-y-auto rounded-lg border shadow-2xl"
        style="background: var(--color-ide-surface); border-color: var(--color-ide-border);">
        <div class="flex items-center justify-between px-3 py-2 border-b" style="border-color: var(--color-ide-border);">
          <div class="flex items-center gap-2">
            <Bell :size="14" class="text-[var(--color-ide-accent)]" />
            <span class="text-[12px] font-semibold text-[var(--color-ide-text)]">通知中心</span>
          </div>
          <div class="flex items-center gap-1">
            <button v-if="store.notifications.length > 0"
              class="text-[10px] px-1.5 py-0.5 rounded text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
              @click="store.dismissAll()">
              全部清除
            </button>
            <button class="p-1 rounded hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]"
              @click="store.showNotificationPanel = false">
              <X :size="13" />
            </button>
          </div>
        </div>
        <div v-if="store.notifications.length === 0" class="flex flex-col items-center justify-center py-10 text-[var(--color-ide-text-dim)]">
          <Bell :size="20" class="mb-2 opacity-30" />
          <p class="text-[11px]">暂无通知</p>
        </div>
        <div v-else class="divide-y" style="border-color: var(--color-ide-border);">
          <div v-for="n in store.notifications" :key="n.id"
            class="px-3 py-2.5 hover:bg-[var(--color-ide-surface-hover)]/50 transition-colors">
            <div class="flex items-start gap-2">
              <component :is="iconMap[n.type]" :size="14" class="mt-0.5 shrink-0" :style="{color:colorMap[n.type].icon}" />
              <div class="min-w-0 flex-1">
                <p class="text-[11px] font-medium text-[var(--color-ide-text)]">{{ n.message }}</p>
                <p v-if="n.detail" class="text-[10px] text-[var(--color-ide-text-dim)] mt-0.5">{{ n.detail }}</p>
                <div class="flex items-center gap-2 mt-1">
                  <span class="text-[9px] text-[var(--color-ide-text-dim)] opacity-40">{{ timeAgo(n.timestamp) }}</span>
                  <span v-if="n.source" class="text-[9px] text-[var(--color-ide-text-dim)] opacity-40">{{ n.source }}</span>
                </div>
              </div>
              <button class="shrink-0 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]" @click="store.dismiss(n.id)">
                <X :size="11" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.toast-enter-active { transition: all 0.3s ease-out; }
.toast-leave-active { transition: all 0.2s ease-in; }
.toast-enter-from { opacity: 0; transform: translateX(60px); }
.toast-leave-to { opacity: 0; transform: translateX(60px); }

.slide-down-enter-active { transition: all 0.2s ease-out; }
.slide-down-leave-active { transition: all 0.15s ease-in; }
.slide-down-enter-from { opacity: 0; transform: translateY(-8px); }
.slide-down-leave-to { opacity: 0; transform: translateY(-8px); }
</style>
