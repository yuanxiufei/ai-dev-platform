<script setup lang="ts">
import { cn } from '@/lib/utils'

defineProps<{
  class?: string
}>()
</script>

<template>
  <div :class="cn('flex flex-col space-y-4', $props.class)">
    <div class="flex border-b">
      <div
        v-for="(tab, index) in tabs"
        :key="index"
        class="inline-flex items-center justify-center whitespace-nowrap px-3 py-1.5 text-sm font-medium ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 cursor-pointer border-b-2"
        :class="modelValue === tab.value
          ? 'border-primary text-foreground'
          : 'border-transparent text-muted-foreground hover:text-foreground'"
        @click="emit('update:modelValue', tab.value)"
      >
        <Component :is="tab.icon" v-if="tab.icon" class="mr-2 h-4 w-4" />
        {{ tab.label }}
      </div>
    </div>
    <slot name="default" :activeTab="modelValue" />
  </div>
</template>

<script lang="ts">
export interface TabItem {
  value: string
  label: string
  icon?: any
}
</script>

<script setup lang="ts">
defineProps<{
  class?: string
  modelValue: string
  tabs: TabItem[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()
</script>
