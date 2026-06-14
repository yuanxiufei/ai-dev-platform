<script setup lang="ts">
import { ref, watch, defineExpose } from 'vue'
import { cn } from '@/lib/utils'
import { X } from 'lucide-vue-next'

const props = defineProps<{
  open?: boolean
  class?: string
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
}>()

const localOpen = ref(props.open ?? false)

watch(() => props.open, (val) => {
  if (val !== undefined) localOpen.value = val
})

watch(localOpen, (val) => {
  emit('update:open', val)
})

function openDialog() { localOpen.value = true }
function closeDialog() { localOpen.value = false }

defineExpose({ open: openDialog, close: closeDialog })
</script>

<template>
  <Teleport to="body">
    <div v-if="localOpen" class="fixed inset-0 z-50 flex items-center justify-center">
      <!-- Overlay -->
      <div class="fixed inset-0 bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out" @click="closeDialog" />
      <!-- Content -->
      <div :class="cn(
        'relative z-50 w-full max-w-lg gap-4 border bg-background p-6 shadow-lg duration-200 sm:rounded-lg',
        props.class,
      )">
        <button
          class="absolute right-4 top-4 rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
          @click="closeDialog"
        >
          <X class="h-4 w-4" />
        </button>
        <slot />
      </div>
    </div>
  </Teleport>
</template>
