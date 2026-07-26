import { client } from './client'

export type FlagType = 'boolean' | 'percentage' | 'experiment'

export interface FeatureFlag {
  name: string
  description: string
  flag_type: FlagType
  enabled: boolean
  rollout_percent: number
  variants: Array<{ name: string; weight: number; config?: Record<string, any> }>
  target_user_ids: string[]
  target_groups: string[]
  created_at?: string
  updated_at?: string
}

export interface EvalResult {
  flag_name: string
  flag_type: string
  active: boolean
  variant: string
  config: Record<string, any>
  bucket?: number
}

export const featureFlagsApi = {
  list() {
    return client.get<FeatureFlag[]>('/api/v1/system/feature-flags')
  },

  get(name: string) {
    return client.get<FeatureFlag>(`/api/v1/system/feature-flags/${name}`)
  },

  createOrUpdate(flag: Partial<FeatureFlag>) {
    return client.post<FeatureFlag>('/api/v1/system/feature-flags', flag)
  },

  delete(name: string) {
    return client.delete(`/api/v1/system/feature-flags/${name}`)
  },

  evaluate(name: string, userId: string = 'default') {
    return client.post<EvalResult>(
      `/api/v1/system/feature-flags/${name}/evaluate`,
      null,
      { params: { user_id: userId } },
    )
  },
}
