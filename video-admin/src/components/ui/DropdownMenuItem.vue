<script setup lang="ts">
import { cn } from '@/lib/utils'

defineProps<{
  class?: string
  onClick?: () => void
}>()
</script>

<template>
  <button
    :class="cn(
      'relative flex w-full cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors hover:bg-accent hover:text-accent-foreground',
      $props.class,
    )"
    @click="$props.onClick?.()"
  >
    <slot />
  </button>
</template>
