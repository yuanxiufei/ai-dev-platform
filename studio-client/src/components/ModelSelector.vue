<script setup lang="ts">
import { Cpu, HardDrive, Wifi } from "lucide-vue-next"
import { onMounted, onUnmounted, ref } from "vue"

interface ModelOption {
  value: string
  label: string
  source: "local" | "api" | "auto"
  provider?: string
  capability?: string
}

defineProps<{
  modelValue: string
  options?: ModelOption[]
}>()

defineEmits<(e: "update:modelValue", value: string) => void>()

const open = ref(false)
const dropdownRef = ref<HTMLDivElement | null>(null)

const defaultOptions: ModelOption[] = [
  { value: "", label: "Auto 自动选择", source: "auto" },
  { value: "openai-gpt4o", label: "GPT-4o", source: "api", provider: "OpenAI" },
  {
    value: "openai-gpt4o-mini",
    label: "GPT-4o Mini",
    source: "api",
    provider: "OpenAI",
  },
  {
    value: "claude-sonnet",
    label: "Claude Sonnet 4",
    source: "api",
    provider: "Anthropic",
  },
  {
    value: "deepseek-v3",
    label: "DeepSeek V3",
    source: "api",
    provider: "DeepSeek",
  },
  { value: "qwen25-coder-7b", label: "Qwen2.5-Coder 7B", source: "local" },
  { value: "gemma-31b", label: "Gemma 3 1B", source: "local" },
]

const sourceIcon = (source: string) => {
  switch (source) {
    case "local":
      return HardDrive
    case "api":
      return Wifi
    default:
      return Cpu
  }
}

const sourceLabel = (source: string) => {
  switch (source) {
    case "local":
      return "本地"
    case "api":
      return "云端"
    default:
      return "Auto"
  }
}

const handleClickOutside = (e: MouseEvent) => {
  if (dropdownRef.value && !dropdownRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener("click", handleClickOutside))
onUnmounted(() => document.removeEventListener("click", handleClickOutside))
</script>

<template>
  <div ref="dropdownRef" class="relative">
    <button
      class="flex items-center gap-2 rounded-xl bg-white/5 border border-white/10 hover:border-white/20 px-3 py-1.5 text-xs text-gray-300 transition-all duration-200 min-w-[140px]"
      @click.stop="open = !open"
    >
      <Cpu class="w-3.5 h-3.5 text-brand-400 shrink-0" />
      <span class="flex-1 text-left truncate">
        {{ defaultOptions.find(o => o.value === modelValue)?.label ?? 'Auto 自动选择' }}
      </span>
      <ChevronDown
        :class="['w-3 h-3 text-gray-500 transition-transform duration-200', open && 'rotate-180']"
      />
    </button>

    <!-- 下拉菜单 -->
    <Transition
      enter-active-class="transition-all duration-200 ease-out"
      enter-from-class="opacity-0 -translate-y-2 scale-95"
      enter-to-class="opacity-100 translate-y-0 scale-100"
      leave-active-class="transition-all duration-150 ease-in"
      leave-from-class="opacity-100 translate-y-0 scale-100"
      leave-to-class="opacity-0 -translate-y-2 scale-95"
    >
      <div
        v-if="open"
        class="absolute right-0 top-full mt-1.5 w-60 rounded-2xl border border-white/10 bg-surface-800 shadow-2xl shadow-black/30 backdrop-blur-xl p-1.5 z-50 max-h-72 overflow-y-auto"
      >
        <div class="px-2.5 py-1.5 text-[10px] font-semibold text-gray-500 uppercase tracking-wider">
          选择模型
        </div>
        <button
          v-for="opt in defaultOptions"
          :key="opt.value"
          :class="[
            'flex items-center gap-3 w-full text-left px-2.5 py-2 rounded-lg text-sm transition-colors duration-150',
            modelValue === opt.value
              ? 'bg-brand-500/15 text-brand-400'
              : 'text-gray-300 hover:bg-white/5',
          ]"
          @click.stop="open = false; $emit('update:modelValue', opt.value)"
        >
          <component
            :is="sourceIcon(opt.source)"
            :class="['w-3.5 h-3.5 shrink-0', opt.source === 'local' ? 'text-amber-400' : opt.source === 'api' ? 'text-blue-400' : 'text-brand-400']"
          />
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium truncate">{{ opt.label }}</div>
            <div v-if="opt.provider" class="text-[10px] text-gray-500 mt-0.5">{{ opt.provider }}</div>
          </div>
          <span
            :class="[
              'text-[10px] rounded-md px-1.5 py-0.5 font-medium',
              opt.source === 'local' ? 'bg-amber-500/10 text-amber-400' : opt.source === 'api' ? 'bg-blue-500/10 text-blue-400' : 'bg-brand-500/10 text-brand-400'
            ]"
          >
            {{ sourceLabel(opt.source) }}
          </span>
        </button>
      </div>
    </Transition>
  </div>
</template>
