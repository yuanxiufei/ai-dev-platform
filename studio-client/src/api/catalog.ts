import { client } from './client'

export interface ModelSet {
  id: number
  name: string
  description: string
  categories: string[]
  specs: Array<{
    source_key: string
    name: string
    parameter_count: string
    quantizations: string[]
  }>
}

export interface CatalogInfo {
  version: string
  updated: string
  model_sets_count: number
  draft_models_count: number
}

export const catalogApi = {
  listModels(params?: { page?: number; size?: number; category?: string; search?: string }) {
    return client.get<{ data: ModelSet[]; total: number; page: number; size: number }>(
      '/api/v1/system/catalog/models',
      { params },
    )
  },

  getModel(modelSetId: number) {
    return client.get<ModelSet>(`/api/v1/system/catalog/models/${modelSetId}`)
  },

  listDrafts() {
    return client.get<{ data: ModelSet[]; total: number }>('/api/v1/system/catalog/drafts')
  },

  getSpec(sourceKey: string) {
    return client.get(`/api/v1/system/catalog/specs/${encodeURIComponent(sourceKey)}`)
  },

  listCategories() {
    return client.get<{ data: string[]; total: number }>('/api/v1/system/catalog/categories')
  },

  getInfo() {
    return client.get<CatalogInfo>('/api/v1/system/catalog/info')
  },
}
