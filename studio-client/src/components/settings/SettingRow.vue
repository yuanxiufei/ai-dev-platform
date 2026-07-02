<template>
  <div class="setting-row">
    <div class="setting-info">
      <label class="setting-label">{{ label }}</label>
      <p v-if="hint" class="setting-hint">{{ hint }}</p>
    </div>
    <div class="setting-control">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  hint?: string
}>()
</script>

<style scoped>
.setting-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 0;
  border-bottom: 1px solid var(--color-ide-border);
  min-height: 48px;
  gap: 16px;
}
.setting-row:last-child {
  border-bottom: none;
}
.setting-info {
  flex: 0 0 auto;
  max-width: 55%;
}
.setting-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-ide-text);
  display: block;
}
.setting-hint {
  font-size: 11.5px;
  color: var(--color-ide-text-dim);
  margin-top: 3px;
  line-height: 1.4;
}
.setting-control {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
}
</style>
