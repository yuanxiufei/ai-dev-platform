<script setup lang="ts">
/**
 * InputDialog — VS Code QuickInput 风格输入框 (声明式)
 *
 * 对标 VSCode .quick-input-widget:
 *   - 标题栏 + 输入区 + 按钮栏 三段布局
 *   - 响应式宽度
 *   - 使用项目 CSS 变量主题化
 */
import { ref, watch, nextTick } from "vue"
import { X } from "lucide-vue-next"
import type { InputDialogOptions } from "@/composables/useInputDialog"

interface Props {
  open: boolean
  title?: string
  placeholder?: string
  defaultValue?: string
  confirmText?: string
  cancelText?: string
  validator?: (value: string) => string | null
}
const props = withDefaults(defineProps<Props>(), {
  title: "输入",
  placeholder: "",
  defaultValue: "",
  confirmText: "确定",
  cancelText: "取消",
  validator: undefined,
})
const emit = defineEmits<{
  "update:open": [v: boolean]
  confirm: [value: string]
  cancel: []
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const value = ref(props.defaultValue)
const error = ref<string | null>(null)

watch(
  () => props.open,
  async (v) => {
    if (v) {
      value.value = props.defaultValue
      error.value = null
      await nextTick()
      inputRef.value?.focus()
      inputRef.value?.select()
    }
  },
)

function onConfirm(): void {
  const v = value.value.trim()
  if (!v) {
    error.value = "名称不能为空"
    return
  }
  if (props.validator) {
    const err = props.validator(v)
    if (err) {
      error.value = err
      return
    }
  }
  emit("confirm", v)
  emit("update:open", false)
}

function onCancel(): void {
  emit("cancel")
  emit("update:open", false)
}

function onInputKey(e: KeyboardEvent): void {
  if (e.key === "Escape") {
    e.preventDefault()
    onCancel()
  } else if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault()
    onConfirm()
  }
}

function onBackdrop(e: MouseEvent): void {
  if (e.target === e.currentTarget) onCancel()
}

function onGlobalKey(e: KeyboardEvent): void {
  if (!props.open) return
  if (e.key === "Escape") {
    e.preventDefault()
    onCancel()
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="quick-input">
      <div
        v-if="open"
        class="fixed inset-0 z-[2550]"
        @mousedown="onBackdrop"
        @keydown="onGlobalKey"
      >
        <!-- 🔥 VSCode .quick-input-widget -->
        <div
          class="quick-input-widget-fx absolute rounded-lg shadow-2xl border overflow-hidden"
          :style="{
            left: '50%',
            transform: 'translateX(-50%)',
            top: '28px',
            width: 'min(62vw, 600px)',
            background: 'var(--color-ide-bg)',
            borderColor: 'var(--color-ide-border)',
            color: 'var(--color-ide-text, #ccc)',
          }"
          @mousedown.stop
        >
          <!-- 🔥 标题栏 -->
          <div
            class="flex items-center px-2"
            :style="{ background: 'var(--input-dialog-header-bg)' }"
          >
            <span class="flex-1 text-center text-[12px] py-0.5 select-none truncate">
              {{ title }}
            </span>
            <button
              class="shrink-0 w-5 h-5 flex items-center justify-center rounded-[3px] opacity-40 hover:opacity-100 hover:!bg-[var(--input-dialog-close-hover)] transition-all ml-1"
              @click="onCancel"
              title="关闭 (Esc)"
            >
              <X :size="12" />
            </button>
          </div>

          <!-- 🔥 输入区 -->
          <div class="p-1.5">
            <div class="flex flex-col gap-0">
              <input
                ref="inputRef"
                v-model="value"
                type="text"
                :placeholder="placeholder"
                class="w-full text-[13px] leading-[22px] px-2 py-1 outline-none rounded-[3px] border"
                :style="{
                  background: 'var(--color-ide-surface, #252526)',
                  color: 'var(--color-ide-text, #ccc)',
                  borderColor: error ? 'var(--color-ide-error)' : 'var(--color-ide-border, #3c3c3c)',
                }"
                @input="error = null"
                @keydown="onInputKey"
              />
              <div
                v-if="error"
                class="text-[11px] leading-[16px] px-0.5 pt-1 select-none"
                style="color: var(--color-ide-error);"
              >
                {{ error }}
              </div>
            </div>
          </div>

          <!-- 🔥 按钮栏 -->
          <div
            class="flex justify-end gap-1.5 px-3 py-2"
            :style="{
              background: 'var(--input-dialog-footer-bg)',
              borderTop: '1px solid ' + 'var(--color-ide-border, #333)',
            }"
          >
            <button
              class="px-3 py-1 text-[12px] rounded-[3px] transition-colors"
              :style="{
                background: 'transparent',
                color: 'var(--color-ide-text, #ccc)',
              }"
              @mouseover="(e: MouseEvent) => ((e.currentTarget as HTMLElement).style.background = 'var(--color-ide-surface-hover)')"
              @mouseleave="(e: MouseEvent) => ((e.currentTarget as HTMLElement).style.background = 'transparent')"
              @click="onCancel"
            >
              {{ cancelText }}
            </button>
            <button
              class="px-3 py-1 text-[12px] rounded-[3px] text-white transition-colors"
              style="background: var(--color-ide-accent);"
              @mouseover="(e: MouseEvent) => ((e.currentTarget as HTMLElement).style.background = 'var(--color-ide-accent-hover)')"
              @mouseleave="(e: MouseEvent) => ((e.currentTarget as HTMLElement).style.background = 'var(--color-ide-accent)')"
              @click="onConfirm"
            >
              {{ confirmText }}
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.quick-input-enter-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.quick-input-leave-active {
  transition: opacity 0.1s ease;
}
.quick-input-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}
.quick-input-leave-to {
  opacity: 0;
}
</style>
