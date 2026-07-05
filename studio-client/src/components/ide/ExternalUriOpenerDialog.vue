<script setup lang="ts">
/**
 * ExternalUriOpenerDialog — URL 打开器选择对话框
 *
 * 对标 VSCode externalUriOpener picker
 * 当 URL 匹配多个 opener 或配置为 prompt 模式时弹出
 */
import { computed } from "vue"
import { openerDialogVisible, openerDialogUrl, openerDialogOptions, selectOpener } from "@/composables/useExternalUriOpener"
import { X, Globe, Monitor, HelpCircle } from "lucide-vue-next"

const hostname = computed(() => {
  try {
    return new URL(openerDialogUrl.value).hostname
  } catch {
    return openerDialogUrl.value
  }
})

const actionIcon = (action: string) => {
  if (action === "external") return Globe
  if (action === "internal") return Monitor
  return HelpCircle
}

const actionLabel = (action: string) => {
  if (action === "external") return "外部浏览器"
  if (action === "internal") return "内置浏览器"
  return "每次询问"
}
</script>

<template>
  <Teleport to="body">
    <div
      v-if="openerDialogVisible"
      class="fixed inset-0 z-[9998] flex items-center justify-center"
      style="background: rgba(0, 0, 0, 0.45);"
      @click.self="selectOpener('cancel')"
    >
      <div
        class="w-[420px] rounded-lg shadow-2xl overflow-hidden"
        style="background: var(--color-ide-surface); border: 1px solid var(--color-ide-border);"
      >
        <!-- Header -->
        <div
          class="flex items-center justify-between px-4 py-3 border-b"
          style="border-color: var(--color-ide-border);"
        >
          <h3 class="text-[14px] font-medium" style="color: var(--color-ide-text);">
            选择打开方式
          </h3>
          <button
            class="p-1 rounded hover:bg-[var(--color-ide-surface-hover)] transition-colors"
            @click="selectOpener('cancel')"
          >
            <X :size="16" style="color: var(--color-ide-text-dim);" />
          </button>
        </div>

        <!-- URL display -->
        <div class="px-4 py-3">
          <div class="text-[12px] mb-1" style="color: var(--color-ide-text-dim);">
            即将打开的链接
          </div>
          <div
            class="text-[13px] px-3 py-2 rounded break-all font-mono"
            style="background: var(--color-ide-bg-secondary); color: var(--color-ide-accent);"
          >
            {{ openerDialogUrl }}
          </div>
        </div>

        <!-- Opener options -->
        <div class="px-4 pb-4 flex flex-col gap-2">
          <button
            v-for="opener in openerDialogOptions"
            :key="opener.id"
            class="flex items-center gap-3 px-3 py-2.5 rounded-md text-left transition-colors border"
            :style="{
              borderColor: 'var(--color-ide-border)',
              color: 'var(--color-ide-text)',
            }"
            @mouseenter="(e: MouseEvent) => {
              (e.currentTarget as HTMLElement).style.background = 'var(--color-ide-surface-hover)'
            }"
            @mouseleave="(e: MouseEvent) => {
              (e.currentTarget as HTMLElement).style.background = 'transparent'
            }"
            @click="selectOpener(opener.action as 'external' | 'internal')"
          >
            <component
              :is="actionIcon(opener.action)"
              :size="20"
              style="color: var(--color-ide-accent);"
            />
            <div class="flex-1">
              <div class="text-[13px] font-medium">{{ opener.label }}</div>
              <div class="text-[12px]" style="color: var(--color-ide-text-dim);">
                {{ opener.description || actionLabel(opener.action) }}
              </div>
            </div>
          </button>

          <!-- Cancel -->
          <button
            class="flex items-center justify-center gap-2 px-3 py-2 rounded-md text-[13px] transition-colors"
            style="color: var(--color-ide-text-dim);"
            @mouseenter="(e: MouseEvent) => {
              (e.currentTarget as HTMLElement).style.background = 'var(--color-ide-surface-hover)'
            }"
            @mouseleave="(e: MouseEvent) => {
              (e.currentTarget as HTMLElement).style.background = 'transparent'
            }"
            @click="selectOpener('cancel')"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
