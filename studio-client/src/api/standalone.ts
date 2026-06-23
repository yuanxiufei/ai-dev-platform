import apiClient from './client'

// ========== 类型定义 ==========

export interface StandaloneStatus {
  version: string
  started: boolean
  timestamp: number
  features: FeatureState[]
  subsystems: {
    watchdog?: WatchdogState
    sleep?: SleepStats
    api_auth?: { active_keys: number }
    wol?: WOLInfo
  }
}

export interface FeatureState {
  key: string
  name: string
  description: string
  enabled: boolean
  dynamic: boolean
  env_override: string | null
}

export interface WatchdogState {
  state: string
  health_pid?: number
  restarts?: number
}

export interface SleepStats {
  state: string
  last_request_seconds_ago: number
  active_requests: number
  sleep_count: number
  total_sleep_duration: number
  current_sleep_duration: number
  os_sleep: OsSleepState
}

export interface OsSleepState {
  enabled: boolean
  scheduled: boolean
  scheduled_at: number
  seconds_until_os_sleep: number
  mode: string
  timeout_seconds: number
}

export interface ApiKeyInfo {
  key_prefix: string
  hashed_key: string
  tenant: string
  name: string
  roles: string[]
  created_at: number | null
  status?: string
}

export interface ApiKeyCreated {
  full_key: string
  access_key_prefix: string
  tenant: string
  name: string
  roles: string[]
  created_at: number | null
}

export interface CreateKeyPayload {
  tenant: string
  name: string
  roles: string[] | null
}

export interface FeatureTogglePayload {
  enabled: boolean
}

// ========== API 方法 ==========

/** 获取系统完整状态 */
export const getStandaloneStatus = () =>
  apiClient.get<StandaloneStatus>('/standalone/status')

/** 连通性检查 */
export const pingStandalone = () =>
  apiClient.get<{ status: string; service: string }>('/standalone/ping')

/** 列出所有功能开关 */
export const listFeatures = () =>
  apiClient.get<{ features: FeatureState[] }>('/standalone/features')

/** 获取单个功能开关 */
export const getFeature = (key: string) =>
  apiClient.get<{ key: string; enabled: boolean }>(`/standalone/features/${key}`)

/** 设置功能开关 */
export const setFeature = (key: string, payload: FeatureTogglePayload) =>
  apiClient.post<{ key: string; enabled: boolean; message: string }>(`/standalone/features/${key}`, payload)

/** 翻转功能开关 */
export const toggleFeature = (key: string) =>
  apiClient.post<{ key: string; enabled: boolean; message: string }>(`/standalone/features/${key}/toggle`)

/** 强制休眠 */
export const forceSleep = () =>
  apiClient.post<{ status: string; message: string }>('/standalone/sleep')

/** 强制唤醒 */
export const forceWake = () =>
  apiClient.post<{ status: string; message: string }>('/standalone/wake')

/** 守护进程状态 */
export const getWatchdogStatus = () =>
  apiClient.get<{ watchdog: WatchdogState }>('/standalone/watchdog')

/** 列出 API Keys */
export const listApiKeys = () =>
  apiClient.get<{ keys: ApiKeyInfo[]; count: number }>('/standalone/keys')

/** 创建 API Key */
export const createApiKey = (payload: CreateKeyPayload) =>
  apiClient.post<ApiKeyCreated>('/standalone/keys', payload)

/** 撤销 API Key */
export const revokeApiKey = (hashedKey: string) =>
  apiClient.delete(`/standalone/keys/${hashedKey}`)

// ========== OS 休眠控制 ==========

/** 获取 OS 休眠计划状态 */
export const getOsSleepStatus = () =>
  apiClient.get<OsSleepState & { platform?: string }>('/standalone/os-sleep/status')

/** 立即触发 OS 休眠 */
export const triggerOsSleep = () =>
  apiClient.post<{ status: string; message: string }>('/standalone/os-sleep')

/** 取消已安排的 OS 休眠 */
export const cancelOsSleep = () =>
  apiClient.post<{ cancelled: boolean; reason?: string }>('/standalone/os-sleep/cancel')

// ========== Wake-on-LAN 远程唤醒 ==========

export interface NetworkInterface {
  interface_name: string
  mac: string
  ip: string
  broadcast: string
}

export interface WOLInfo {
  target_mac: string
  broadcast_address: string
  port: number
  interfaces: NetworkInterface[]
  last_sent_at: number
  last_sent_success: boolean
  platform: string
}

export interface WOLSendPayload {
  mac_address: string
  broadcast: string
  port: number
}

export interface WOLSendResult {
  success: boolean
  message: string
  target_mac: string
  broadcast: string
  port?: number
}

export interface WOLConfigurePayload {
  target_mac: string
  broadcast_address: string
  port: number
}

/** 获取 WOL 配置信息 */
export const getWOLInfo = () =>
  apiClient.get<WOLInfo>('/standalone/wol/info')

/** 发送 WOL 魔术包 */
export const sendWOL = (payload: WOLSendPayload) =>
  apiClient.post<WOLSendResult>('/standalone/wol/send', payload)

/** 配置 WOL 参数 */
export const configureWOL = (payload: WOLConfigurePayload) =>
  apiClient.post<WOLInfo>('/standalone/wol/configure', payload)

/** 重新检测网络接口 */
export const redetectWOL = () =>
  apiClient.post<WOLInfo>('/standalone/wol/redetect')
