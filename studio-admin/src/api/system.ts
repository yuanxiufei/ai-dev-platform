import apiClient from './client'

/* ========== 存储管理 ========== */

export const getStorageStats = () =>
  apiClient.get('/system/storage/stats')

export const getStorageConfig = () =>
  apiClient.get('/system/storage/config')

export const updateStorageConfig = (data: Record<string, any>) =>
  apiClient.post('/system/storage/config', data)

export const migrateStorage = (newRoot: string) =>
  apiClient.post('/system/storage/migrate', { new_root: newRoot })

export const cleanupStorage = (path: string, maxAgeHours: number = 24) =>
  apiClient.post('/system/storage/cleanup', { path, max_age_hours: maxAgeHours })

export const checkStorageQuota = () =>
  apiClient.get('/system/storage/quota')

/* ========== 检查点管理 ========== */

export const listCheckpoints = () =>
  apiClient.get('/system/checkpoints')

export const createCheckpoint = (label: string = '', metadata: Record<string, string> = {}) =>
  apiClient.post('/system/checkpoints', { label, metadata })

export const restoreCheckpoint = (id: string) =>
  apiClient.post(`/system/checkpoints/${id}/restore`)

export const deleteCheckpoint = (id: string) =>
  apiClient.delete(`/system/checkpoints/${id}`)

export const getCheckpointDiff = (id: string) =>
  apiClient.get(`/system/checkpoints/${id}/diff`)

/* ========== GPU 管理 ========== */

export const getGPUDevices = () =>
  apiClient.get('/system/gpu/devices')

export const getGPUStats = () =>
  apiClient.get('/system/gpu/stats')

/* ========== 系统资源 ========== */

export const getSystemResources = () =>
  apiClient.get('/system/resources')

export const getResourceHistory = () =>
  apiClient.get('/system/resources/history')

/* ========== 配置管理 ========== */

export const getSystemConfig = () =>
  apiClient.get('/system/config')

export const reloadConfig = () =>
  apiClient.post('/system/config/reload')

/* ========== 健康检查 ========== */

export const getHealth = () =>
  apiClient.get('/system/health')

export const getDetailedHealth = () =>
  apiClient.get('/system/health/detailed')

export const getHealthStats = () =>
  apiClient.get('/system/health/stats')

/* ========== 护栏配置 ========== */

export const getGuardrailsConfig = () =>
  apiClient.get('/system/guardrails/config')

export const checkGuardrails = (toolName: string, toolParams: Record<string, string>) =>
  apiClient.post('/system/guardrails/check', { tool_name: toolName, tool_params: toolParams })
