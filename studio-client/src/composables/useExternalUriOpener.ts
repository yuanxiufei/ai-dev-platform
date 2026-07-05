/**
 * useExternalUriOpener — 外部 URI 打开器
 *
 * 对标 VSCode workbench/contrib/externalUriOpener
 * 当用户点击 URL 时，根据后端配置的策略决定如何打开。
 *
 * 使用方式:
 *   const { openUrl } = useExternalUriOpener()
 *   <a @click.prevent="openUrl('https://localhost:3000')">...</a>
 */
import { ref } from "vue"

export interface UriOpenerConfig {
  id: string
  label: string
  description: string
  action: "external" | "internal" | "prompt"
  patterns: Array<{ regex: string; priority: number; label: string }>
  default_for_schemes: string[]
  enabled: boolean
  is_builtin: boolean
}

interface ResolveResult {
  url: string
  scheme: string
  action: "external" | "internal" | "prompt"
  opener_id: string
  opener_label: string
  matched_by: string
}

/** URL 打开器选择对话框状态 */
export const openerDialogVisible = ref(false)
export const openerDialogUrl = ref("")
export const openerDialogOptions = ref<UriOpenerConfig[]>([])
/** 对话框回调，resolve 后执行 */
let _openerResolve: ((action: "external" | "internal" | "cancel") => void) | null = null

/** 缓存 openers 列表 */
let _cachedOpeners: UriOpenerConfig[] | null = null
let _cacheTime = 0
const CACHE_TTL = 30_000 // 30秒缓存

/** 获取所有 opener 配置 */
export async function fetchOpeners(apiBase: string = "/api/v1"): Promise<UriOpenerConfig[]> {
  const now = Date.now()
  if (_cachedOpeners && now - _cacheTime < CACHE_TTL) {
    return _cachedOpeners
  }
  try {
    const resp = await fetch(`${apiBase}/system/external-uri-openers`)
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const data = await resp.json()
    _cachedOpeners = data.data || []
    _cacheTime = now
    return _cachedOpeners!
  } catch {
    // 回退: 仅系统浏览器
    const fallback: UriOpenerConfig = {
      id: "system-browser",
      label: "系统浏览器",
      description: "默认系统浏览器",
      action: "external",
      patterns: [],
      default_for_schemes: ["http", "https"],
      enabled: true,
      is_builtin: true,
    }
    return [fallback]
  }
}

/** 解析 URL 对应的 opener */
export async function resolveUrl(
  url: string,
  apiBase: string = "/api/v1",
): Promise<ResolveResult> {
  try {
    const resp = await fetch(`${apiBase}/system/external-uri-openers/resolve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    return await resp.json()
  } catch {
    return {
      url,
      scheme: "",
      action: "external",
      opener_id: "system-browser",
      opener_label: "系统浏览器",
      matched_by: "fallback",
    }
  }
}

/** 显示 opener 选择对话框 */
function showOpenerDialog(url: string, openers: UriOpenerConfig[]): Promise<"external" | "internal" | "cancel"> {
  return new Promise((resolve) => {
    openerDialogUrl.value = url
    openerDialogOptions.value = openers.filter((o) => o.enabled)
    openerDialogVisible.value = true
    _openerResolve = resolve
  })
}

/** 选择对话框结果 */
export function selectOpener(action: "external" | "internal" | "cancel"): void {
  openerDialogVisible.value = false
  if (_openerResolve) {
    _openerResolve(action)
    _openerResolve = null
  }
}

/**
 * 打开 URL（根据策略自动选择 opener）
 * 返回: 最终使用的 action
 */
export async function openUrl(
  url: string,
  apiBase: string = "/api/v1",
): Promise<"external" | "internal" | "cancel"> {
  // 非 HTTP(S) URL 直接走系统
  if (!/^https?:\/\//i.test(url)) {
    window.open(url, "_blank")
    return "external"
  }

  const result = await resolveUrl(url, apiBase)

  if (result.action === "external") {
    window.open(url, "_blank")
    return "external"
  }

  if (result.action === "internal") {
    // 内置浏览器 (iframe panel 或新 tab)
    // 使用可扩展的内置浏览器区域
    window.open(url, "_blank") // 默认回退: 新标签
    return "internal"
  }

  if (result.action === "prompt") {
    // 显示选择对话框
    const openers = await fetchOpeners(apiBase)
    const action = await showOpenerDialog(url, openers)
    if (action === "external") {
      window.open(url, "_blank")
    } else if (action === "internal") {
      window.open(url, "_blank")
    }
    return action
  }

  // 回退
  window.open(url, "_blank")
  return "external"
}

/**
 * useExternalUriOpener — Vue composable
 */
export function useExternalUriOpener(apiBase: string = "/api/v1") {
  return {
    openUrl: (url: string) => openUrl(url, apiBase),
    resolveUrl: (url: string) => resolveUrl(url, apiBase),
    fetchOpeners: () => fetchOpeners(apiBase),
    /** 对话框状态 */
    dialogVisible: openerDialogVisible,
    dialogUrl: openerDialogUrl,
    dialogOptions: openerDialogOptions,
    selectOpener,
  }
}
