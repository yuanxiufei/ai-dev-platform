<template>
  <button
    type="button"
    role="switch"
    :aria-checked="modelValue"
    :class="toggleClasses"
    @click="$emit('update:modelValue', !modelValue)"
  >
    <span :class="knobClasses" />
  </button>
</template>

<script setup lang="ts">
import { computed } from "vue"

const props = defineProps<{ modelValue?: boolean }>()
defineEmits<(e: "update:modelValue", value: boolean) => void>()

const toggleClasses = computed(() => [
  "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus-visible:ring-2",
  {
    "bg-[var(--color-ide-accent)] focus-visible:ring-[var(--color-ide-accent)]":
      props.modelValue,
    "bg-[var(--color-ide-border)]": !props.modelValue,
  },
])

const knobClasses = computed(() => [
  "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out",
  props.modelValue ? "translate-x-4" : "translate-x-0",
])
</script>
