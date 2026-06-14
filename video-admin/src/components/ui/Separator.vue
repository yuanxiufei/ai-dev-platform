<script setup lang="ts">
import { cn } from '@/lib/utils'

defineProps<{
  class?: string
  orientation?: 'horizontal' | 'vertical'
}>()
</script>

<template>
  <div
    :class="cn(
      'shrink-0 bg-border',
      orientation === 'vertical' ? 'h-full w-px' : 'h-px w-full',
      orientation === 'horizontal' && 'h-px w-full',
      !orientation && 'h-px w-full',
      $props.class,
    )"
    role="separator"
  />
</template>
