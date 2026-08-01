import apiClient from "./client"

// ============================================
// GPU 管理 API — 设备列表/分配/状态/释放
// ============================================

export const gpuApi = {
  /** 列出所有检测到的 GPU 设备及当前利用率 */
  listDevices: () =>
    apiClient.get("/system/gpu/devices"),

  /** 列出所有 GPU 内存分配 */
  listAllocations: () =>
    apiClient.get("/system/gpu/allocations"),

  /** 获取 GPU 整体状态摘要（显存总量/空闲量等） */
  getStatus: () =>
    apiClient.get("/system/gpu/status"),

  /** 释放指定 GPU 内存分配 */
  releaseAllocation: (allocationId: string) =>
    apiClient.post(`/system/gpu/allocations/${allocationId}/release`),
}
