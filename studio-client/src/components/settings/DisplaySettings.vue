<template>
  <div class="settings-section">
    <div class="section-title">外观</div>

    <SettingRow label="主题" hint="选择 IDE 配色方案">
      <select class="select" :value="settings.display.theme" @change="onThemeChange">
        <option value="dark">VSCode Dark+</option>
        <option value="light">VSCode Light+</option>
        <option value="high-contrast">High Contrast</option>
      </select>
    </SettingRow>

    <div class="section-title">聊天体验</div>

    <SettingRow label="流式输出" hint="AI 回复逐字显示">
      <div class="switch" :class="{ on: settings.display.streaming }" @click="toggle('streaming')">
        <div class="switch-thumb" />
      </div>
    </SettingRow>

    <SettingRow label="紧凑模式" hint="缩小聊天间距，显示更多内容">
      <div class="switch" :class="{ on: settings.display.compact }" @click="toggle('compact')">
        <div class="switch-thumb" />
      </div>
    </SettingRow>

    <SettingRow label="显示推理过程" hint="展示 AI 的思考步骤">
      <div class="switch" :class="{ on: settings.display.showReasoning }" @click="toggle('showReasoning')">
        <div class="switch-thumb" />
      </div>
    </SettingRow>

    <SettingRow label="显示 Token 消耗" hint="每次对话后展示费用估算">
      <div class="switch" :class="{ on: settings.display.showCost }" @click="toggle('showCost')">
        <div class="switch-thumb" />
      </div>
    </SettingRow>

    <SettingRow label="行内差异" hint="代码修改以 diff 形式显示">
      <div class="switch" :class="{ on: settings.display.inlineDiffs }" @click="toggle('inlineDiffs')">
        <div class="switch-thumb" />
      </div>
    </SettingRow>

    <div class="section-title">通知</div>

    <SettingRow label="完成时提示音" hint="AI 回复完成后播放提示音">
      <div class="switch" :class="{ on: settings.display.bellOnComplete }" @click="toggle('bellOnComplete')">
        <div class="switch-thumb" />
      </div>
    </SettingRow>

    <SettingRow label="桌面通知" hint="通过系统通知提醒">
      <div class="switch" :class="{ on: settings.display.notifyOnComplete }" @click="toggle('notifyOnComplete')">
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
  const val = (settings.display as any)[key]
  settings.saveSection('display', { [key]: !val })
}

function onThemeChange(e: Event) {
  const val = (e.target as HTMLSelectElement).value
  settings.saveSection('display', { theme: val })
}
</script>

<style scoped>
.section-title {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--color-ide-text-dim);
  padding: 16px 0 8px;
}
.section-title:first-child { padding-top: 0; }
.select {
  padding: 4px 8px; font-size: 12px;
  background: var(--color-chat-input-bg); border: 1px solid var(--color-ide-border);
  border-radius: 3px; color: var(--color-ide-text); outline: none;
}
.select:focus { border-color: var(--color-ide-border-focus); }
.switch {
  width: 36px; height: 20px; border-radius: 10px;
  background: var(--color-ide-border); cursor: pointer;
  position: relative; transition: background 0.15s;
  flex-shrink: 0;
}
.switch.on { background: var(--color-ide-accent); }
.switch-thumb {
  position: absolute; top: 2px; left: 2px;
  width: 16px; height: 16px; border-radius: 50%;
  background: #fff; transition: transform 0.15s;
}
.switch.on .switch-thumb { transform: translateX(16px); }
</style>
