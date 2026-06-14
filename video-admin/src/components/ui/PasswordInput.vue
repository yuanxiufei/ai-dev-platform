<script setup lang="ts">
import { ref } from 'vue'
import { cn } from '@/lib/utils'
import { Eye, EyeOff } from 'lucide-vue-next'

defineProps<{
  class?: string
  id?: string
  modelValue?: string
  placeholder?: string
  disabled?: boolean
  autocomplete?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const showPassword = ref(false)
</script>

<template>
  <div :class="cn('relative', $props.class)">
    <input
      :id="id"
      :type="showPassword ? 'text' : 'password'"
      :placeholder="placeholder"
      :disabled="disabled"
      :value="modelValue"
      :autocomplete="autocomplete"
      class="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 pr-10 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
      @input="emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
    <button
      type="button"
      class="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
      @click="showPassword = !showPassword"
    >
      <Eye v-if="!showPassword" class="h-4 w-4" />
      <EyeOff v-else class="h-4 w-4" />
    </button>
  </div>
</template>
