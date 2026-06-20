<script setup lang="ts">
import { PenLine, Lightbulb, FileText, Bot } from 'lucide-vue-next'

defineProps<{
  modelValue: ChatMode
  hasFiles?: boolean
}>()

defineEmits<{
  (e: 'update:modelValue', value: ChatMode): void
}>()

export type ChatMode = 'craft' | 'ask' | 'plan' | 'agent'

const modes: { value: ChatMode; label: string; icon: typeof PenLine }[] = [
  { value: 'craft', label: 'Craft', icon: PenLine },
  { value: 'ask', label: 'Ask', icon: Lightbulb },
  { value: 'plan', label: 'Plan', icon: FileText },
  { value: 'agent', label: 'Agent', icon: Bot },
]
</script>

<template>
  <div class="flex items-center gap-1 p-1 rounded-xl bg-white/5 border border-white/8">
    <button
      v-for="mode in modes"
      :key="mode.value"
      :class="[
        'flex items-center gap-1.5 px-3.5 py-2 rounded-lg text-xs font-medium transition-all duration-200',
        modelValue === mode.value
          ? 'bg-brand-500/20 text-brand-400 shadow-sm'
          : 'text-gray-500 hover:text-gray-300',
      ]"
      @click="$emit('update:modelValue', mode.value)"
    >
      <component :is="mode.icon" class="w-3.5 h-3.5" />
      {{ mode.label }}
    </button>
  </div>
</template>
