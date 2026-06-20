<template>
  <button type="button" role="switch" :aria-checked="modelValue"
    :class="['relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus-visible:ring-2 focus-visible:ring-[var(--color-ide-accent)]',
      modelValue ? 'bg-[var(--color-ide-accent)]' : 'bg-[var(--color-ide-border)]'"
    @click="$emit('update:modelValue', !modelValue)">
    <span :class="['pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out', modelValue ? 'translate-x-4' : 'translate-x-0']" />
  </button>
</template>

<script setup lang="ts">
defineProps<{ modelValue?: boolean }>()
defineEmits<{ (e: 'update:modelValue', value: boolean): void }>()
</script>
