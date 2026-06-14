<script setup lang="ts">
import { cn } from '@/lib/utils'

defineProps<{
  class?: string
  htmlFor?: string
  error?: string
}>()
</script>

<template>
  <div :class="cn('space-y-2', $props.class)">
    <div class="space-y-1">
      <slot name="label" />
      <slot />
    </div>
    <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
  </div>
</template>
