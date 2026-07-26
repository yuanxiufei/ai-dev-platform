import { client } from './client'

export interface CliHistoryEntry {
  command: string
  exit_code: number
  stdout: string
  stderr: string
  duration_ms: number
  timestamp: string
  cwd: string
}

export const cliHistoryApi = {
  list(limit?: number, offset?: number) {
    return client.get<{
      entries: CliHistoryEntry[]
      total: number
      page_size: number
      success_count: number
      error_count: number
    }>('/api/v1/system/cli-history', { params: { limit, offset } })
  },
}
