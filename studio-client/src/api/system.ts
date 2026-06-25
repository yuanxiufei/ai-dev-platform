import apiClient from "./client"

/* ========== 存储管理 ========== */

export const getStorageStats = () => apiClient.get("/system/storage/stats")

export const getStorageConfig = () => apiClient.get("/system/storage/config")

export const updateStorageConfig = (data: Record<string, any>) =>
  apiClient.post("/system/storage/config", data)

export const cleanupStorage = (path: string, maxAgeHours: number = 24) =>
  apiClient.post("/system/storage/cleanup", {
    path,
    max_age_hours: maxAgeHours,
  })

/* ========== 检查点管理 ========== */

export const listCheckpoints = () => apiClient.get("/system/checkpoints")

export const createCheckpoint = (
  label: string = "",
  metadata: Record<string, string> = {},
) => apiClient.post("/system/checkpoints", { label, metadata })

export const restoreCheckpoint = (id: string) =>
  apiClient.post(`/system/checkpoints/${id}/restore`)

export const deleteCheckpoint = (id: string) =>
  apiClient.delete(`/system/checkpoints/${id}`)

/* ========== 健康检查 ========== */

export const getHealth = () => apiClient.get("/system/health")
