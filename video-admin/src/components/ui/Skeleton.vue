<script setup lang="ts">
import { cn } from '@/lib/utils'

defineProps<{
  class?: string
}>()
</script>

<template>
  <div :class="cn('animate-pulse rounded-md bg-primary/10', $props.class)">
    <slot />
  </div>
</template>
