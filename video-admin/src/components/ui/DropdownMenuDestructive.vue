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
      'relative flex w-full cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none transition-colors text-destructive hover:bg-destructive/10 hover:text-destructive',
      $props.class,
    )"
    @click="$props.onClick?.()"
  >
    <slot />
  </button>
</template>
