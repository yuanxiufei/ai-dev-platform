import apiClient from "./client"

// ============================================
// 模型管理 API — 模型列表/下载/加载/卸载/提供商/统计
// ============================================

export const modelsApi = {
  /** 列出所有可用模型（本地 + 远程 API），支持按能力筛选 */
  listAll: (capability?: string) =>
    apiClient.get("/system/models", { params: capability ? { capability } : {} }),

  /** 获取单个模型详情 */
  getDetail: (modelName: string) =>
    apiClient.get(`/system/models/${modelName}`),

  /** 触发模型下载（异步，返回 task_id） */
  startDownload: (modelName: string, source = "huggingface") =>
    apiClient.post("/system/models/download", { model_name: modelName, source }),

  /** 查询下载进度 */
  getDownloadStatus: (taskId: string) =>
    apiClient.get(`/system/models/download/${taskId}`),

  /** 删除本地模型 */
  deleteModel: (modelName: string) =>
    apiClient.delete(`/system/models/${modelName}`),

  /** 加载模型到内存/显存 */
  loadModel: (modelName: string) =>
    apiClient.post(`/system/models/${modelName}/load`),

  /** 卸载模型，释放资源 */
  unloadModel: (modelName: string) =>
    apiClient.post(`/system/models/${modelName}/unload`),

  /** 列出当前已加载到内存的模型 */
  listLoaded: () =>
    apiClient.get("/system/models/loaded"),

  /** 列出支持的 API 提供商 */
  listProviders: () =>
    apiClient.get("/system/models/providers"),

  /** 配置 API 提供商密钥（AES 加密存储） */
  configureProvider: (provider: string, apiKey: string, endpoint?: string) =>
    apiClient.post("/system/models/providers", { provider, api_key: apiKey, endpoint }),

  /** 获取模型使用统计 */
  getUsageStats: (params?: { model_name?: string; days?: number }) =>
    apiClient.get("/system/models/usage-stats", { params }),

  /** 触发自动优化 */
  triggerOptimize: (days = 7) =>
    apiClient.post("/system/models/optimize", null, { params: { days } }),
}
