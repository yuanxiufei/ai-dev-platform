<script setup lang="ts">
/**
 * InputDialogHost — VS Code QuickInput 风格输入框
 *
 * 严格对标 VSCode .quick-input-widget:
 *   - 无遮罩, 纯浮层 (position: fixed, 水平居中, 顶部偏下)
 *   - 标题栏 + 输入区 + 消息区 三段布局
 *   - 无"取消/确认"按钮 (Enter 确认, Esc 取消)
 *   - 宽度响应式: min(window * 0.62, 600px)
 *   - 圆角 xLarge, 阴影 xl
 */
import { computed, watch, nextTick, ref, onMounted, onBeforeUnmount } from "vue"
import { X } from "lucide-vue-next"
import {
  dlgOpen, dlgOpts, dlgValue, dlgError,
  confirmDialog, cancelDialog,
} from "@/composables/useInputDialog"

const inputRef = ref<HTMLInputElement | null>(null)

const title = computed(() => dlgOpts.value.title ?? "输入")
const placeholder = computed(() => dlgOpts.value.placeholder ?? "")

function onSubmit(): void {
  const v = dlgValue.value.trim()
  if (!v) {
    dlgError.value = "名称不能为空"
    return
  }
  if (dlgOpts.value.validator) {
    const err = dlgOpts.value.validator(v)
    if (err) {
      dlgError.value = err
      return
    }
  }
  confirmDialog(v)
}

function onDismiss(): void {
  cancelDialog()
}

function onKey(e: KeyboardEvent): void {
  if (!dlgOpen.value) return
  if (e.key === "Escape") {
    e.preventDefault()
    onDismiss()
  } else if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault()
    onSubmit()
  }
}

function onBackdrop(e: MouseEvent): void {
  if (e.target === e.currentTarget) onDismiss()
}

watch(dlgOpen, async (v) => {
  if (v) {
    await nextTick()
    inputRef.value?.focus()
    inputRef.value?.select()
  }
})

onMounted(() => window.addEventListener("keydown", onKey))
onBeforeUnmount(() => window.removeEventListener("keydown", onKey))
</script>

<template>
  <Teleport to="body">
    <Transition name="quick-input">
      <div
        v-if="dlgOpen"
        class="fixed inset-0 z-[2550]"
        @mousedown="onBackdrop"
      >
        <!--
          🔥 VSCode .quick-input-widget — 浮层卡片
          position: absolute 在 relative 容器里, 我们这里是 fixed 容器
          水平居中: left:50% + translate(-50%) 替代 VSCode 的 JS 计算
          VSCode 垂直: titleBarOffset (~27-30px from top)
        -->
        <div
          class="quick-input-widget-fx absolute rounded-lg shadow-2xl border overflow-hidden"
          :style="{
            left: '50%',
            transform: 'translateX(-50%)',
            top: '28px',
            width: 'min(62vw, 600px)',
            background: 'var(--color-ide-bg, #1e1e1e)',
            borderColor: 'var(--color-ide-border, #333)',
            color: 'var(--color-ide-text, #ccc)',
          }"
          @mousedown.stop
        >
          <!-- 🔥 标题栏 VSCode .quick-input-titlebar -->
          <div
            class="flex items-center px-2"
            :style="{
              background: 'var(--input-dialog-header-bg)',
              cursor: 'default',
            }"
          >
            <span
              class="flex-1 text-center text-[12px] py-0.5 select-none truncate"
            >
              {{ title }}
            </span>
            <!-- 关闭按钮 -->
            <button
              class="shrink-0 w-5 h-5 flex items-center justify-center rounded-[3px] opacity-40 hover:opacity-100 hover:!bg-[var(--input-dialog-close-hover)] transition-all ml-1"
              @click="onDismiss"
              title="关闭 (Esc)"
            >
              <X :size="12" />
            </button>
          </div>

          <!-- 🔥 输入区 VSCode .quick-input-header -->
          <div class="p-1.5">
            <!-- .quick-input-and-message -->
            <div class="flex flex-col gap-0">
              <!-- .quick-input-filter > .quick-input-box -->
              <div class="flex relative">
                <div class="flex-1 relative">
                  <!-- 🔥 VSCode .monaco-inputbox — 输入框带边框 -->
                  <input
                    ref="inputRef"
                    v-model="dlgValue"
                    type="text"
                    :placeholder="placeholder"
                    class="w-full text-[13px] leading-[22px] px-2 py-1 outline-none rounded-[3px] border"
                    :style="{
                      background: 'var(--color-ide-surface, #252526)',
                      color: 'var(--color-ide-text, #ccc)',
                      borderColor: dlgError ? 'var(--color-ide-error)' : 'var(--color-ide-border, #3c3c3c)',
                    }"
                    @input="dlgError = null"
                  />
                </div>
              </div>

              <!-- 🔥 消息区 VSCode .quick-input-message -->
              <div
                v-if="dlgError"
                class="text-[11px] leading-[16px] px-0.5 pt-1 select-none"
                style="color: var(--color-ide-error);"
              >
                {{ dlgError }}
              </div>
            </div>
          </div>

          <!-- 🔥 底部提示 (Enter 确认 / Esc 取消) — 轻量无按钮 -->
          <div
            v-if="!dlgError"
            class="flex justify-end items-center px-3 py-1 text-[11px] opacity-40 select-none"
          >
            按 Enter 确认, Esc 取消
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* 🔥 VSCode quick-input 入场/离场动画 */
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

.quick-input-widget-fx {
  /* z-index already on parent */
}
</style>
