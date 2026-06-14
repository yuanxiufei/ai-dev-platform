<script setup lang="ts">
import { ref } from 'vue'
import { cn } from '@/lib/utils'
import { ChevronDown, ChevronUp, Check } from 'lucide-vue-next'

defineProps<{
  class?: string
  modelValue?: string
  placeholder?: string
  disabled?: boolean
  items?: { value: string; label: string }[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const open = ref(false)

function select(val: string) {
  emit('update:modelValue', val)
  open.value = false
}
</script>

<template>
  <div :class="cn('relative', $props.class)">
    <button
      :disabled="disabled"
      type="button"
      class="flex h-9 w-full items-center justify-between whitespace-nowrap rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm ring-offset-background focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50 [&>span]:line-clamp-1"
      @click="open = !open"
      @blur="open = false"
    >
      <span :class="!modelValue && 'text-muted-foreground'">{{ items?.find((i) => i.value === modelValue)?.label || placeholder || 'Select...' }}</span>
      <ChevronDown class="h-4 w-4 opacity-50" />
    </button>
    <div
      v-if="open"
      class="absolute z-50 mt-1 max-h-60 w-full overflow-auto rounded-md border bg-popover p-1 text-popover-foreground shadow-md"
    >
      <div
        v-for="item in items"
        :key="item.value"
        class="relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none hover:bg-accent hover:text-accent-foreground"
        :class="{ 'bg-accent text-accent-foreground': modelValue === item.value }"
        @click="select(item.value)"
      >
        <Check v-if="modelValue === item.value" class="mr-2 h-4 w-4" />
        <span :class="modelValue === item.value ? '' : 'ml-6'">{{ item.label }}</span>
      </div>
    </div>
  </div>
</template>
