<script setup lang="ts">
import { cn } from '@/lib/utils'

defineProps<{
  class?: string
  src?: string
  alt?: string
}>()
</script>

<template>
  <span :class="cn('relative flex h-10 w-10 shrink-0 overflow-hidden rounded-full bg-muted', $props.class)">
    <img v-if="src" :src="src" :alt="alt" class="aspect-square h-full w-full" @error="(e) => { (e.target as HTMLImageElement).style.display = 'none' }" />
    <span v-else class="flex h-full w-full items-center justify-center rounded-full text-xs font-medium">{{ alt?.charAt(0)?.toUpperCase() || 'U' }}</span>
  </span>
</template>
