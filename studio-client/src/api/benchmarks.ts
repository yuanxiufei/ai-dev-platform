import { client } from './client'

export interface BenchmarkTask {
  task_id: string
  model_name: string
  capability: string
  dataset: string
  num_requests: number
  concurrency: number
  max_tokens: number
  state: string
  progress: number
  metrics: {
    tokens_per_second: number
    latency_avg_ms: number
  }
  logs: string[]
  created_at: string
  updated_at: string
}

export const benchmarkApi = {
  create(params: {
    model_name: string
    capability?: string
    dataset?: string
    num_requests?: number
    concurrency?: number
    max_tokens?: number
  }) {
    return client.post<BenchmarkTask>('/api/v1/system/benchmarks', null, { params })
  },

  list(state?: string) {
    return client.get<BenchmarkTask[]>('/api/v1/system/benchmarks', { params: state ? { state } : undefined })
  },

  get(taskId: string) {
    return client.get<BenchmarkTask>(`/api/v1/system/benchmarks/${taskId}`)
  },

  submit(taskId: string) {
    return client.post(`/api/v1/system/benchmarks/${taskId}/submit`)
  },

  stop(taskId: string) {
    return client.post(`/api/v1/system/benchmarks/${taskId}/stop`)
  },

  exportYaml(taskId: string) {
    return client.get<{ yaml: string; task_id: string }>(`/api/v1/system/benchmarks/${taskId}/export`)
  },

  /** WebSocket URL, 使用时需拼接 token */
  wsUrl(taskId: string, token: string) {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${location.host}/api/v1/system/benchmarks/${taskId}/ws?token=${token}`
  },
}
