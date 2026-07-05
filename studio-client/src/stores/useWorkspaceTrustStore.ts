/**
 * useWorkspaceTrustStore — VSCode 工作区信任模型
 *
 * 借鉴: VSCode src/vs/workbench/contrib/workspace/
 * 能力:
 *   - 工作区信任状态管理 (trusted/untrusted/unknown)
 *   - 受限模式下禁用的功能列表
 *   - 信任对话框（打开文件夹时弹窗确认）
 */
import { defineStore } from "pinia"
import { ref, computed } from "vue"

const TRUST_STORAGE_KEY = "ide_workspace_trust"

interface TrustEntry {
  path: string
  trusted: boolean
  timestamp: number
}

type TrustState = "unknown" | "trusted" | "untrusted"

export const useWorkspaceTrustStore = defineStore("workspaceTrust", () => {
  const trustMap = ref<Record<string, boolean>>(loadTrustMap())
  const currentPath = ref<string>("")
  const showTrustDialog = ref(false)

  function loadTrustMap(): Record<string, boolean> {
    try {
      const raw = localStorage.getItem(TRUST_STORAGE_KEY)
      if (raw) return JSON.parse(raw)
    } catch { /* ignore */ }
    return {}
  }

  function saveTrustMap(): void {
    try {
      localStorage.setItem(TRUST_STORAGE_KEY, JSON.stringify(trustMap.value))
    } catch { /* ignore */ }
  }

  function trustWorkspace(path: string): void {
    trustMap.value[normalizePath(path)] = true
    saveTrustMap()
    currentPath.value = path
    showTrustDialog.value = false
  }

  function untrustWorkspace(path: string): void {
    delete trustMap.value[normalizePath(path)]
    saveTrustMap()
    currentPath.value = ""
  }

  function normalizePath(path: string): string {
    return path.replace(/\\/g, "/").replace(/\/$/, "")
  }

  function isTrusted(path: string): boolean {
    return trustMap.value[normalizePath(path)] === true
  }

  const currentTrustState = computed<TrustState>(() => {
    if (!currentPath.value) return "unknown"
    return isTrusted(currentPath.value) ? "trusted" : "untrusted"
  })

  /** 受限模式下禁用的功能 */
  const restrictedFeatures = computed(() => [
    { id: "terminal", label: "终端", restricted: currentTrustState.value === "untrusted" },
    { id: "tasks", label: "任务执行", restricted: currentTrustState.value === "untrusted" },
    { id: "debug", label: "调试", restricted: currentTrustState.value === "untrusted" },
    { id: "scm", label: "Git 操作", restricted: false },
    { id: "extensions", label: "扩展安装", restricted: currentTrustState.value === "untrusted" },
  ])

  function requestTrust(path: string): void {
    currentPath.value = path
    if (!isTrusted(path)) {
      showTrustDialog.value = true
    }
  }

  return {
    trustMap, currentPath, showTrustDialog,
    trustWorkspace, untrustWorkspace, isTrusted,
    currentTrustState, restrictedFeatures, requestTrust,
  }
})
