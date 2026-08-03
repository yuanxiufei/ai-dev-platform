import { apiClient } from "./client";

/* ===== Types ===== */
export interface GpuDevice {
  index: number;
  name: string;
  vram_total_mb: number;
  vram_used_mb: number;
  vram_free_mb: number;
  utilization_pct: number;
  temperature_c?: number;
  driver_version?: string;
  cuda_version?: string;
}

export interface GpuDevicesResponse {
  data: GpuDevice[];
  total: number;
}

export interface GpuAllocation {
  allocation_id: string;
  gpu_index: number;
  model_name: string;
  requested_mb: number;
  allocated_mb: number;
  status: string;
  created_at: string;
}

export interface GpuAllocationsResponse {
  active: GpuAllocation[];
  total_allocations: number;
}

export interface GpuStatus {
  gpu_count: number;
  total_vram_mb: number;
  free_vram_mb: number;
  active_allocations: number;
  last_snapshot_ts: string;
}

/* ===== API ===== */
export const gpuMonitorApi = {
  /** 列出所有 GPU 设备及利用率 */
  listDevices() {
    return apiClient.get<GpuDevicesResponse>("/system/gpu/devices");
  },

  /** 列出 GPU 内存分配 */
  listAllocations() {
    return apiClient.get<GpuAllocationsResponse>("/system/gpu/allocations");
  },

  /** GPU 状态摘要 */
  getStatus() {
    return apiClient.get<GpuStatus>("/system/gpu/status");
  },

  /** 释放 GPU 内存分配 */
  releaseAllocation(allocationId: string) {
    return apiClient.post<{ message: string }>(
      `/system/gpu/allocations/${allocationId}/release`,
    );
  },
};
