<script setup lang="ts">
defineProps<{ modelValue: boolean; disabled?: boolean; size?: 'sm' | 'md' }>()
const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()
</script>

<template>
  <button
    type="button"
    role="switch"
    :aria-checked="modelValue"
    :disabled="disabled"
    :class="[
      'relative inline-flex shrink-0 rounded-full transition-colors duration-200 ease-in-out focus-visible:outline-2 focus-visible:outline-brand-400',
      size === 'sm' ? 'w-8 h-4.5' : 'w-10 h-5.5',
      modelValue ? 'bg-brand-500' : 'bg-white/10',
      disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer hover:bg-brand-400',
    ]"
    @click="emit('update:modelValue', !modelValue)"
  >
    <span
      :class="[
        'absolute top-1/2 -translate-y-1/2 rounded-full bg-white shadow-sm transition-all duration-200',
        size === 'sm' ? 'w-3 h-3' : 'w-4 h-4',
        modelValue ? (size === 'sm' ? 'left-[calc(100%-0.85rem)]' : 'left-[calc(100%-1.1rem)]') : 'left-0.5',
      ]"
    />
  </button>
</template>
