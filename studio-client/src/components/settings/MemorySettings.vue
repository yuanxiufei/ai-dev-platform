<template>
  <div class="settings-section">
    <div class="section-title">记忆管理</div>

    <SettingRow label="启用长期记忆" hint="记住对话中的关键信息，用于后续对话">
      <div class="switch" :class="{ on: settings.memory.enabled }" @click="toggle('enabled')">
        <div class="switch-thumb" />
      </div>
    </SettingRow>

    <SettingRow label="最大记忆条数" hint="超过该数量时自动清理旧记忆">
      <div class="number-control">
        <input
          type="number"
          class="number-input"
          :value="settings.memory.maxEntries"
          @input="onMaxEntriesChange"
          min="100" max="10000" step="100"
        />
        <span class="unit">条</span>
      </div>
    </SettingRow>

    <SettingRow label="记忆衰减" hint="旧记忆随时间推移权重降低">
      <div class="switch" :class="{ on: settings.memory.decayEnabled }" @click="toggle('decayEnabled')">
        <div class="switch-thumb" />
      </div>
    </SettingRow>
  </div>
</template>

<script setup lang="ts">
import { useSettingsStore } from '@/stores/useSettingsStore'
import SettingRow from './SettingRow.vue'

const settings = useSettingsStore()

function toggle(key: string) {
  const val = (settings.memory as any)[key]
  settings.saveSection('memory', { [key]: !val })
}

function onMaxEntriesChange(e: Event) {
  const v = parseInt((e.target as HTMLInputElement).value) || 100
  settings.saveSection('memory', { maxEntries: Math.max(100, Math.min(10000, v)) })
}
</script>

<style scoped>
.section-title {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--color-ide-text-dim);
  padding: 16px 0 8px;
}
.section-title:first-child { padding-top: 0; }
.switch {
  width: 36px; height: 20px; border-radius: 10px;
  background: var(--color-ide-border); cursor: pointer;
  position: relative; transition: background 0.15s; flex-shrink: 0;
}
.switch.on { background: var(--color-ide-accent); }
.switch-thumb {
  position: absolute; top: 2px; left: 2px;
  width: 16px; height: 16px; border-radius: 50%;
  background: #fff; transition: transform 0.15s;
}
.switch.on .switch-thumb { transform: translateX(16px); }
.number-control { display: flex; align-items: center; gap: 6px; }
.number-input {
  width: 80px; padding: 4px 8px; font-size: 13px; text-align: center;
  background: var(--color-chat-input-bg); border: 1px solid var(--color-ide-border);
  border-radius: 3px; color: var(--color-ide-text); outline: none;
}
.number-input:focus { border-color: var(--color-ide-border-focus); }
.unit { font-size: 12px; color: var(--color-ide-text-dim); }
</style>
