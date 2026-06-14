<script setup lang="ts">
import { cn } from '@/lib/utils'

defineProps<{
  class?: string
  message?: string
  type?: 'default' | 'destructive'
}>()
</script>

<template>
  <div :class="cn(
    'relative w-full rounded-lg border px-4 py-3 text-sm',
    type === 'destructive'
      ? 'border-destructive/50 text-destructive dark:border-destructive'
      : 'border-border text-foreground',
    $props.class,
  )">
    <slot>
      {{ message }}
    </slot>
  </div>
</template>
