<template>
  <div class="settings-section">
    <div class="section-title">Agent 行为</div>

    <SettingRow label="最大轮次" hint="单次对话最多执行的工具调用轮次 (1-200)">
      <div class="number-control">
        <input
          type="number"
          class="number-input"
          :value="settings.agent.maxTurns"
          @input="onMaxTurnsChange"
          min="1" max="200" step="5"
        />
      </div>
    </SettingRow>

    <SettingRow label="网关超时" hint="Agent 等待工具返回的超时秒数 (60-7200)">
      <div class="number-control">
        <input
          type="number"
          class="number-input"
          :value="settings.agent.gatewayTimeout"
          @input="onGatewayTimeoutChange"
          min="60" max="7200" step="60"
        />
        <span class="unit">s</span>
      </div>
    </SettingRow>

    <SettingRow label="重启缓冲时间" hint="重启前等待正在执行的任务完成的秒数">
      <div class="number-control">
        <input
          type="number"
          class="number-input"
          :value="settings.agent.restartDrainTimeout"
          @input="onDrainTimeoutChange"
          min="10" max="300" step="10"
        />
        <span class="unit">s</span>
      </div>
    </SettingRow>

    <div class="section-title">工具控制</div>

    <SettingRow label="工具执行策略" hint="控制何时允许 Agent 调用工具">
      <select class="select" :value="settings.agent.toolEnforcement" @change="onToolEnforcementChange">
        <option value="auto">自动判断</option>
        <option value="always">始终允许</option>
        <option value="never">禁止调用</option>
      </select>
    </SettingRow>
  </div>
</template>

<script setup lang="ts">
import { useSettingsStore } from '@/stores/useSettingsStore'
import SettingRow from './SettingRow.vue'

const settings = useSettingsStore()

let debounce: ReturnType<typeof setTimeout> | null = null

function debounceSave(key: string, value: any) {
  settings.updateLocal('agent', { [key]: value })
  if (debounce) clearTimeout(debounce)
  debounce = setTimeout(() => settings.saveSection('agent', { [key]: value }), 300)
}

function onMaxTurnsChange(e: Event) {
  const v = parseInt((e.target as HTMLInputElement).value) || 1
  debounceSave('maxTurns', Math.max(1, Math.min(200, v)))
}

function onGatewayTimeoutChange(e: Event) {
  const v = parseInt((e.target as HTMLInputElement).value) || 60
  debounceSave('gatewayTimeout', Math.max(60, Math.min(7200, v)))
}

function onDrainTimeoutChange(e: Event) {
  const v = parseInt((e.target as HTMLInputElement).value) || 10
  debounceSave('restartDrainTimeout', Math.max(10, Math.min(300, v)))
}

function onToolEnforcementChange(e: Event) {
  const v = (e.target as HTMLSelectElement).value
  settings.saveSection('agent', { toolEnforcement: v }, true)
}
</script>

<style scoped>
.section-title {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--color-ide-text-dim);
  padding: 16px 0 8px;
}
.section-title:first-child { padding-top: 0; }
.number-control {
  display: flex; align-items: center; gap: 6px;
}
.number-input {
  width: 80px; padding: 4px 8px; font-size: 13px; text-align: center;
  background: var(--color-chat-input-bg); border: 1px solid var(--color-ide-border);
  border-radius: 3px; color: var(--color-ide-text); outline: none;
}
.number-input:focus { border-color: var(--color-ide-border-focus); }
.unit { font-size: 12px; color: var(--color-ide-text-dim); }
.select {
  padding: 4px 8px; font-size: 12px;
  background: var(--color-chat-input-bg); border: 1px solid var(--color-ide-border);
  border-radius: 3px; color: var(--color-ide-text); outline: none;
}
.select:focus { border-color: var(--color-ide-border-focus); }
</style>
