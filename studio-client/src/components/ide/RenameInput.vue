<script setup lang="ts">
/**
 * CodeBuddy IDE — Rename Input (VSCode-style inline rename widget)
 *
 * 借鉴: VSCode renameInputField.ts + renameWidget
 * Session 38: F2 重命名符号内联输入框 + 预览面板
 */
import { ref, watch, nextTick, onMounted } from "vue"

const props = defineProps<{
  visible: boolean
  x: number
  y: number
  symbolName: string
  occurrencesCount: number
}>()

const emit = defineEmits<{
  (e: "confirm", newName: string): void
  (e: "cancel"): void
  (e: "update-preview", newName: string): void
}>()

const inputRef = ref<HTMLInputElement | null>(null)
const newName = ref("")
const isComposing = ref(false)

watch(
  () => props.visible,
  async (v) => {
    if (v) {
      newName.value = props.symbolName
      await nextTick()
      inputRef.value?.focus()
      inputRef.value?.select()
    }
  },
)

watch(
  () => props.symbolName,
  (name) => {
    if (props.visible) {
      newName.value = name
    }
  },
)

/** 实时预览更新 */
function onInput(e: Event): void {
  const val = (e.target as HTMLInputElement).value
  newName.value = val
  if (!isComposing.value) {
    emit("update-preview", val)
  }
}

function onCompositionStart(): void {
  isComposing.value = true
}

function onCompositionEnd(e: CompositionEvent): void {
  isComposing.value = false
  newName.value = (e.target as HTMLInputElement).value
  emit("update-preview", newName.value)
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === "Enter" && !isComposing.value) {
    e.preventDefault()
    if (newName.value && newName.value !== props.symbolName) {
      emit("confirm", newName.value)
    } else {
      emit("cancel")
    }
  } else if (e.key === "Escape") {
    e.preventDefault()
    emit("cancel")
  }
}

function onConfirm(): void {
  if (newName.value && newName.value !== props.symbolName) {
    emit("confirm", newName.value)
  } else {
    emit("cancel")
  }
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="visible"
      class="rename-input-container"
      :style="{ left: x + 'px', top: y + 'px' }"
      @click.stop
    >
      <!-- 主输入区域 -->
      <div class="rename-box">
        <div class="rename-header">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            stroke-linecap="round"
            stroke-linejoin="round"
            class="rename-icon"
          >
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
          </svg>
          <span class="rename-title">重命名符号</span>
          <span class="rename-hint">Enter 确认 · Esc 取消</span>
        </div>
        <div class="rename-input-wrapper">
          <input
            ref="inputRef"
            v-model="newName"
            class="rename-input"
            type="text"
            spellcheck="false"
            @input="onInput"
            @keydown="onKeydown"
            @compositionstart="onCompositionStart"
            @compositionend="onCompositionEnd"
          />
        </div>
        <div class="rename-footer">
          <span class="rename-occurrences" v-if="occurrencesCount > 0">
            {{ occurrencesCount }} 处匹配
          </span>
          <div class="rename-actions">
            <button class="rename-btn cancel" @click="emit('cancel')">取消</button>
            <button class="rename-btn confirm" @click="onConfirm">确认</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.rename-input-container {
  position: fixed;
  z-index: 9999;
  pointer-events: auto;
}

.rename-box {
  background: var(--color-ide-surface, #252526);
  border: 1px solid var(--color-ide-accent, #007acc);
  border-radius: 6px;
  box-shadow:
    0 4px 12px rgba(0, 0, 0, 0.5),
    0 0 0 1px rgba(0, 122, 204, 0.2);
  min-width: 320px;
  max-width: 480px;
  overflow: hidden;
  animation: renameSlideIn 0.1s ease-out;
}

@keyframes renameSlideIn {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.rename-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  background: var(--color-ide-accent, #007acc);
  color: #fff;
  font-size: 11px;
}

.rename-icon {
  flex-shrink: 0;
}

.rename-title {
  font-weight: 600;
  flex: 1;
}

.rename-hint {
  opacity: 0.7;
  font-size: 10px;
}

.rename-input-wrapper {
  padding: 8px 10px 6px;
}

.rename-input {
  width: 100%;
  background: var(--color-ide-input-bg, #3c3c3c);
  color: var(--color-ide-text, #cccccc);
  border: 1px solid var(--color-ide-border, #3e3e3e);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 13px;
  font-family: var(--editor-font, "Cascadia Code", "Fira Code", monospace);
  outline: none;
  line-height: 1.6;
  transition: border-color 0.1s;
}

.rename-input:focus {
  border-color: var(--color-ide-accent, #007acc);
}

.rename-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 10px 6px;
}

.rename-occurrences {
  font-size: 11px;
  color: var(--color-ide-text-dim, #858585);
}

.rename-actions {
  display: flex;
  gap: 6px;
}

.rename-btn {
  padding: 3px 12px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.1s;
  border: none;
}

.rename-btn.cancel {
  background: transparent;
  color: var(--color-ide-text, #cccccc);
}

.rename-btn.cancel:hover {
  background: var(--color-ide-surface-hover, #2a2d2e);
}

.rename-btn.confirm {
  background: var(--color-ide-accent, #007acc);
  color: #fff;
}

.rename-btn.confirm:hover {
  filter: brightness(1.15);
}
</style>
