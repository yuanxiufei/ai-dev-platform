<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { cn } from '@/lib/utils'
import { MoreHorizontal } from 'lucide-vue-next'

defineProps<{
  class?: string
}>()

const isOpen = ref(false)
const menuRef = ref<HTMLElement>()
const triggerRef = ref<HTMLElement>()

function toggle() {
  isOpen.value = !isOpen.value
}

function close() {
  isOpen.value = false
}

onMounted(() => {
  document.addEventListener('click', (e) => {
    if (
      menuRef.value &&
      triggerRef.value &&
      !menuRef.value.contains(e.target as Node) &&
      !triggerRef.value.contains(e.target as Node)
    ) {
      close()
    }
  })
})
</script>

<template>
  <div :class="cn('relative inline-block text-left', $props.class)">
    <button ref="triggerRef" type="button" class="flex items-center" @click.stop="toggle">
      <slot name="trigger">
        <MoreHorizontal class="h-4 w-4" />
      </slot>
    </button>
    <Transition name="dropdown">
      <div
        v-if="isOpen"
        ref="menuRef"
        class="absolute right-0 z-50 mt-2 min-w-[160px] origin-top-right rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
      >
        <slot />
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.dropdown-enter-active {
  transition: all 0.15s ease-out;
}
.dropdown-leave-active {
  transition: all 0.1s ease-in;
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: scale(0.95) translateY(-4px);
}
</style>
