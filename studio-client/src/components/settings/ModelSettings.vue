<template>
  <div class="settings-section">
    <div class="section-title">API 提供商</div>

    <div v-if="settings.providers.length === 0" class="empty-hint">
      暂无已配置的 API 提供商。请在 .env 中配置 API 密钥后重启服务。
    </div>

    <div v-for="provider in settings.providers" :key="provider.key" class="provider-card">
      <div class="provider-header">
        <span class="provider-name">{{ provider.name }}</span>
        <span class="type-badge" :class="provider.isBuiltin ? 'builtin' : 'custom'">
          {{ provider.isBuiltin ? '内置' : '自定义' }}
        </span>
      </div>
      <div class="provider-body">
        <div class="field-row">
          <input
            :type="showKey[provider.key] ? 'text' : 'password'"
            class="key-input"
            :value="editKeys[provider.key] ?? provider.apiKey"
            @input="(e) => editKeys[provider.key] = (e.target as HTMLInputElement).value"
            placeholder="输入 API Key"
          />
          <button class="btn btn-small" @click="toggleShow(provider.key)">{{ showKey[provider.key] ? '隐藏' : '显示' }}</button>
          <button class="btn btn-primary btn-small" :disabled="savingKey === provider.key" @click="saveKey(provider.key)">
            {{ savingKey === provider.key ? '保存中' : '保存' }}
          </button>
        </div>
        <div class="model-tags" v-if="provider.models.length">
          <span v-for="m in provider.models" :key="m" class="model-tag">{{ m }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useSettingsStore } from '@/stores/useSettingsStore'
import SettingRow from './SettingRow.vue'

const settings = useSettingsStore()
const savingKey = ref<string | null>(null)
const editKeys = reactive<Record<string, string>>({})
const showKey = reactive<Record<string, boolean>>({})

onMounted(() => {
  settings.fetchProviders()
})

function toggleShow(key: string) {
  showKey[key] = !showKey[key]
}

async function saveKey(providerKey: string) {
  savingKey.value = providerKey
  await settings.saveProviderKey(providerKey, editKeys[providerKey] || '')
  savingKey.value = null
}
</script>

<style scoped>
.section-title {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.05em; color: var(--color-ide-text-dim);
  padding: 16px 0 8px;
}
.section-title:first-child { padding-top: 0; }
.empty-hint {
  padding: 40px 0; text-align: center;
  font-size: 13px; color: var(--color-ide-text-dim);
}
.provider-card {
  background: var(--color-ide-surface);
  border: 1px solid var(--color-ide-border);
  border-radius: 6px; padding: 16px; margin-bottom: 12px;
}
.provider-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px;
}
.provider-name {
  font-size: 14px; font-weight: 600; color: var(--color-ide-text);
}
.type-badge {
  font-size: 11px; padding: 2px 8px; border-radius: 3px; font-weight: 600;
}
.builtin { background: rgba(0,122,204,0.12); color: var(--color-ide-accent); }
.custom { background: rgba(78,201,176,0.12); color: var(--color-ide-success); }
.field-row {
  display: flex; gap: 8px; align-items: center;
}
.key-input {
  flex: 1; padding: 6px 10px; font-size: 13px; font-family: monospace;
  background: var(--color-chat-input-bg); border: 1px solid var(--color-ide-border);
  border-radius: 3px; color: var(--color-ide-text); outline: none;
}
.key-input:focus { border-color: var(--color-ide-border-focus); }
.btn {
  padding: 5px 12px; font-size: 12px; border-radius: 3px; border: none; cursor: pointer;
  font-weight: 600; transition: background 0.1s;
}
.btn-small { padding: 4px 10px; font-size: 11px; }
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-primary:hover { background: var(--color-ide-accent-hover); }
.btn-primary:disabled { opacity: 0.4; }
.model-tags {
  display: flex; flex-wrap: wrap; gap: 4px; margin-top: 10px;
}
.model-tag {
  font-size: 10.5px; padding: 2px 8px;
  background: rgba(204,204,204,0.08); border-radius: 3px;
  color: var(--color-ide-text-dim);
}
</style>
