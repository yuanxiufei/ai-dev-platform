<script setup lang="ts">
import { ref } from 'vue'
import { cn } from '@/lib/utils'
import { X, Menu } from 'lucide-vue-next'

const props = defineProps<{
  class?: string
  side?: 'left' | 'right'
  open?: boolean
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

function close() {
  emit('update:open', false)
}
</script>

<template>
  <Teleport to="body">
    <!-- Overlay -->
    <div
      v-if="open"
      class="fixed inset-0 z-50 bg-black/50 transition-opacity"
      @click="close"
    />

    <!-- Sheet -->
    <div
      :class="cn(
        'fixed z-50 gap-4 bg-background p-6 shadow-lg transition-all duration-300 ease-in-out',
        side === 'right' ? 'right-0 top-0 h-full w-3/4 border-l sm:max-w-sm' : 'left-0 top-0 h-full w-3/4 border-r sm:max-w-sm',
        open
          ? (side === 'right' ? 'translate-x-0' : 'translate-x-0')
          : (side === 'right' ? 'translate-x-full' : '-translate-x-full'),
        $props.class,
      )"
      aria-hidden="true"
    >
      <button
        class="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
        @click="close"
      >
        <X class="h-4 w-4" />
      </button>
      <slot />
    </div>
  </Teleport>
</template>
