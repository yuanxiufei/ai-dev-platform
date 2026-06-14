<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { cn } from '@/lib/utils'

const TOOLTIP_SIDE_OFFSET = 4

const props = defineProps<{
  class?: string
}>()

const isOpen = ref(false)
const tooltipRef = ref<HTMLElement>()
const triggerRef = ref<HTMLElement>()

let showTimer: ReturnType<typeof setTimeout>
let hideTimer: ReturnType<typeof setTimeout>

function show() {
  clearTimeout(hideTimer)
  showTimer = setTimeout(() => {
    isOpen.value = true
  }, 300)
}

function hide() {
  clearTimeout(showTimer)
  hideTimer = setTimeout(() => {
    isOpen.value = false
  }, 100)
}

onMounted(() => {
  if (triggerRef.value) {
    triggerRef.value.addEventListener('mouseenter', show)
    triggerRef.value.addEventListener('mouseleave', hide)
    triggerRef.value.addEventListener('focus', show)
    triggerRef.value.addEventListener('blur', hide)
  }
})
onUnmounted(() => {
  if (triggerRef.value) {
    triggerRef.value.removeEventListener('mouseenter', show)
    triggerRef.value.removeEventListener('mouseleave', hide)
  }
})
</script>

<template>
  <div class="relative inline-block">
    <div ref="triggerRef" class="inline-block">
      <slot name="trigger" />
    </div>
    <Teleport to="body">
      <Transition name="tooltip-fade">
        <div
          v-if="isOpen"
          :class="cn(
            'z-50 overflow-hidden rounded-md bg-primary px-3 py-1.5 text-xs text-primary-foreground animate-in fade-in-0 zoom-in-95 absolute -top-2 left-1/2 -translate-x-1/2 -translate-y-full',
            $props.class,
          )"
        >
          <slot />
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.tooltip-fade-enter-active,
.tooltip-fade-leave-active {
  transition: opacity 0.15s ease;
}
.tooltip-fade-enter-from,
.tooltip-fade-leave-to {
  opacity: 0;
}
</style>
