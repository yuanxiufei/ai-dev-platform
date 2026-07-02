import { ref, reactive } from 'vue'
import { defineStore } from 'pinia'
import apiClient from '@/api/client'

export interface DisplaySettings {
  theme: 'dark' | 'light' | 'high-contrast'
  streaming: boolean
  compact: boolean
  showReasoning: boolean
  showCost: boolean
  inlineDiffs: boolean
  bellOnComplete: boolean
  notifyOnComplete: boolean
  chatInputHeight: number
}

export interface AgentSettings {
  maxTurns: number
  gatewayTimeout: number
  restartDrainTimeout: number
  toolEnforcement: 'auto' | 'always' | 'never'
}

export interface MemorySettings {
  enabled: boolean
  maxEntries: number
  decayEnabled: boolean
}

export interface ModelProvider {
  name: string
  key: string
  isBuiltin: boolean
  apiKey: string
  models: string[]
}

export const useSettingsStore = defineStore('settings', () => {
  // ── State ──
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')
  const activeTab = ref('account')

  const display = reactive<DisplaySettings>({
    theme: 'dark',
    streaming: true,
    compact: false,
    showReasoning: true,
    showCost: false,
    inlineDiffs: true,
    bellOnComplete: false,
    notifyOnComplete: false,
    chatInputHeight: 200,
  })

  const agent = reactive<AgentSettings>({
    maxTurns: 30,
    gatewayTimeout: 600,
    restartDrainTimeout: 60,
    toolEnforcement: 'auto',
  })

  const memory = reactive<MemorySettings>({
    enabled: true,
    maxEntries: 1000,
    decayEnabled: true,
  })

  const providers = ref<ModelProvider[]>([])

  const debounceTimers: Record<string, ReturnType<typeof setTimeout>> = {}

  // ── Actions ──

  async function fetchSettings(): Promise<void> {
    loading.value = true
    try {
      // Fetch display/agent/memory settings from backend if available
      const res = await apiClient.get('/system/config')
      if (res.data?.display) Object.assign(display, res.data.display)
      if (res.data?.agent) Object.assign(agent, res.data.agent)
      if (res.data?.memory) Object.assign(memory, res.data.memory)
    } catch {
      // Fallback to defaults — backend may not have this endpoint yet
    } finally {
      loading.value = false
    }
  }

  async function fetchProviders(): Promise<void> {
    try {
      const res = await apiClient.get('/system/models/providers')
      providers.value = (res.data?.providers || res.data || []).map((p: any) => ({
        name: p.name || p.provider || 'unknown',
        key: p.key || p.name || p.provider || 'unknown',
        isBuiltin: !p.name?.startsWith('custom:'),
        apiKey: p.api_key || '***',
        models: p.models || [],
      }))
    } catch {
      providers.value = []
    }
  }

  function updateLocal(section: string, values: Record<string, any>): void {
    const target = section === 'display' ? display
      : section === 'agent' ? agent
      : section === 'memory' ? memory
      : null
    if (target) Object.assign(target, values)
  }

  async function saveSection(
    section: string,
    values: Record<string, any>,
    immediate?: boolean,
  ): Promise<void> {
    updateLocal(section, values)

    if (immediate) {
      await doSave(section, values)
      return
    }

    // Debounce
    const key = section
    if (debounceTimers[key]) clearTimeout(debounceTimers[key])
    debounceTimers[key] = setTimeout(() => doSave(section, values), 300)
  }

  async function doSave(section: string, values: Record<string, any>): Promise<void> {
    saving.value = true
    try {
      await apiClient.patch('/system/config', { [section]: values })
    } catch {
      // Silently fail for now — backend endpoint may not exist
    } finally {
      saving.value = false
    }
  }

  async function saveProviderKey(providerKey: string, apiKey: string): Promise<void> {
    saving.value = true
    try {
      await apiClient.post('/system/models/providers', {
        provider: providerKey,
        api_key: apiKey,
      })
      const p = providers.value.find(pr => pr.key === providerKey)
      if (p) p.apiKey = apiKey
    } catch {
      error.value = '保存 API Key 失败'
    } finally {
      saving.value = false
    }
  }

  return {
    loading,
    saving,
    error,
    activeTab,
    display,
    agent,
    memory,
    providers,
    fetchSettings,
    fetchProviders,
    updateLocal,
    saveSection,
    saveProviderKey,
  }
})
