// ============================================
// System Store — system info, memory, CPU (Tauri-only)
// ============================================
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { isTauriEnv } from './shared'
import type { SystemInfo, MemoryUsage, CPUInfo } from '@/utils/tauri'

export const useSystemStore = defineStore('system', () => {
  const systemInfo = ref<SystemInfo | null>(null)
  const memoryUsage = ref<MemoryUsage | null>(null)
  const cpuInfo = ref<CPUInfo | null>(null)
  const workspaceDir = ref('')
  const isLoading = ref(false)

  /** Whether system info is available (Tauri-only) */
  const available = computed(() => isTauriEnv())

  /** Fetch all system information */
  async function refreshSystemInfo(): Promise<void> {
    if (!isTauriEnv()) { _warnDesktopOnly('系统信息'); return }
    isLoading.value = true
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const [si, mu, ci] = await Promise.all([
        invoke<SystemInfo>('get_system_info'),
        invoke<MemoryUsage>('get_memory_usage'),
        invoke<CPUInfo>('get_cpu_info'),
      ])
      systemInfo.value = si
      memoryUsage.value = mu
      cpuInfo.value = ci
    } catch (e) {
      console.warn('[System] Failed to refresh system info:', e)
    } finally {
      isLoading.value = false
    }
  }

  /** Fetch system overview only */
  async function getSystemInfo(): Promise<SystemInfo | null> {
    if (!isTauriEnv()) { _warnDesktopOnly('系统信息'); return null }
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const info = await invoke<SystemInfo>('get_system_info')
      systemInfo.value = info
      return info
    } catch (e) {
      console.warn('[System] get_system_info failed:', e)
      return null
    }
  }

  /** Fetch memory usage only */
  async function getMemoryUsage(): Promise<MemoryUsage | null> {
    if (!isTauriEnv()) { _warnDesktopOnly('内存信息'); return null }
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const info = await invoke<MemoryUsage>('get_memory_usage')
      memoryUsage.value = info
      return info
    } catch (e) {
      console.warn('[System] get_memory_usage failed:', e)
      return null
    }
  }

  /** Fetch CPU info only */
  async function getCPUInfo(): Promise<CPUInfo | null> {
    if (!isTauriEnv()) { _warnDesktopOnly('CPU 信息'); return null }
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const info = await invoke<CPUInfo>('get_cpu_info')
      cpuInfo.value = info
      return info
    } catch (e) {
      console.warn('[System] get_cpu_info failed:', e)
      return null
    }
  }

  /** Get current workspace directory */
  async function getWorkspaceDir(): Promise<string> {
    if (!isTauriEnv()) { _warnDesktopOnly('工作目录'); return '' }
    try {
      const { invoke } = await import('@tauri-apps/api/core')
      const dir = await invoke<string>('get_workspace_dir')
      workspaceDir.value = dir
      return dir
    } catch (e) {
      console.warn('[System] get_workspace_dir failed:', e)
      return ''
    }
  }

  return {
    systemInfo,
    memoryUsage,
    cpuInfo,
    workspaceDir,
    isLoading,
    available,
    refreshSystemInfo,
    getSystemInfo,
    getMemoryUsage,
    getCPUInfo,
    getWorkspaceDir,
  }
})

/** Lazily notify user that feature requires desktop app */
async function _warnDesktopOnly(feature: string): Promise<void> {
  try {
    const { useNotificationStore } = await import('./useNotificationStore')
    useNotificationStore().warn(
      `「${feature}」功能需要桌面版应用支持，Web 模式下不可用。`,
      { source: 'System', autoDismiss: 6000 }
    )
  } catch { /* notification store not available */ }
}
