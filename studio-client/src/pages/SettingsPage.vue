<template>
  <div class="settings-page">
    <div class="settings-header">
      <h2 class="page-title">设置</h2>
    </div>
    <div class="settings-layout">
      <!-- Tab sidebar -->
      <div class="tab-sidebar">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="tab-btn"
          :class="{ active: active === tab.key }"
          @click="active = tab.key"
        >
          <span class="tab-icon">{{ tab.icon }}</span>
          <span class="tab-label">{{ tab.label }}</span>
        </button>
      </div>
      <!-- Content area -->
      <div class="settings-content">
        <AccountSettings v-if="active === 'account'" />
        <DisplaySettings v-if="active === 'display'" />
        <AgentSettings v-if="active === 'agent'" />
        <MemorySettings v-if="active === 'memory'" />
        <ModelSettings v-if="active === 'models'" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import AccountSettings from '@/components/settings/AccountSettings.vue'
import DisplaySettings from '@/components/settings/DisplaySettings.vue'
import AgentSettings from '@/components/settings/AgentSettings.vue'
import ModelSettings from '@/components/settings/ModelSettings.vue'
import MemorySettings from '@/components/settings/MemorySettings.vue'

const active = ref('account')

const tabs = [
  { key: 'account', label: '账户', icon: '👤' },
  { key: 'display', label: '显示', icon: '🎨' },
  { key: 'agent', label: 'Agent', icon: '🤖' },
  { key: 'memory', label: '记忆', icon: '🧠' },
  { key: 'models', label: '模型', icon: '⚡' },
]
</script>

<style scoped>
.settings-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-ide-bg);
  color: var(--color-ide-text);
}
.settings-header {
  flex-shrink: 0;
  padding: 16px 24px;
  background: var(--color-ide-bg-secondary);
  border-bottom: 1px solid var(--color-ide-border);
}
.page-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--color-ide-text-bright);
}
.settings-layout {
  flex: 1;
  display: flex;
  overflow: hidden;
}
.tab-sidebar {
  width: 180px;
  flex-shrink: 0;
  background: var(--color-ide-bg-secondary);
  border-right: 1px solid var(--color-ide-border);
  padding: 8px 0;
  overflow-y: auto;
}
.tab-btn {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  padding: 10px 20px;
  font-size: 13px;
  color: var(--color-ide-text-dim);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background 0.08s, color 0.08s;
  text-align: left;
}
.tab-btn:hover {
  background: var(--color-ide-surface-hover);
  color: var(--color-ide-text);
}
.tab-btn.active {
  background: var(--color-ide-surface-active);
  color: var(--color-ide-text-bright);
  border-left: 3px solid var(--color-ide-accent);
  padding-left: 17px;
}
.tab-icon {
  font-size: 16px;
}
.tab-label {
  font-weight: 500;
}
.settings-content {
  flex: 1;
  overflow-y: auto;
  padding: 0 32px 32px;
}
</style>
