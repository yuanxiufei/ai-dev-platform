<script setup lang="ts">
import { cn } from '@/lib/utils'
import Button from './Button.vue'
import { Loader2 } from 'lucide-vue-next'

defineProps<{
  class?: string
  loading?: boolean
  variant?: 'default' | 'destructive' | 'outline' | 'secondary' | 'ghost' | 'link'
  size?: 'default' | 'sm' | 'lg' | 'icon'
  type?: 'button' | 'submit' | 'reset'
  disabled?: boolean
}>()
</script>

<template>
  <Button
    :variant="variant || 'default'"
    :size="size"
    :type="type"
    :disabled="disabled || loading"
    :class="cn('relative', $props.class)"
  >
    <Loader2 v-if="loading" class="mr-2 h-4 w-4 animate-spin" />
    <slot />
  </Button>
</template>
