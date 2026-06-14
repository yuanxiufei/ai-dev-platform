<script setup lang="ts">
import { cn } from '@/lib/utils'

defineProps<{
  as?: string
  class?: string
}>()
</script>

<template>
  <Component :is="as || 'div'" :class="cn('flex flex-col space-y-1.5 p-6', $props.class)">
    <slot />
  </Component>
</template>
