import { client } from './client'

export interface CLIEntry {
  id?: string | number
  command: string
  exit_code: number
  stdout: string
  stderr: string
  duration_ms: number
  timestamp: string
  cwd: string
}

export interface CLIStats {
  total: number
  success: number
  failed: number
  avgDurationMs: number
}

export interface ListEntriesParams {
  limit: number
  offset: number
  search?: string
  exit_code?: number
  exit_not_zero?: boolean
}

export const cliHistoryApi = {
  /** 分⻚查询历史记录 */
  listEntries(params: ListEntriesParams) {
    return client.get<{ entries: CLIEntry[]; total: number; page_size: number; success_count: number; error_count: number }>(
      '/system/cli-history',
      { params }
    )
  },

  /** 获取统计摘要 (基于 entries 前端计算) */
  async getStats(): Promise<{ data: CLIStats }> {
    const r = await client.get<{ entries: CLIEntry[]; total: number }>('/system/cli-history', { params: { limit: 500, offset: 0 } })
    const entries = r.data.entries ?? []
    const total = entries.length
    const success = entries.filter(e => e.exit_code === 0).length
    const avg = total > 0 ? Math.round(entries.reduce((s, e) => s + (e.duration_ms || 0), 0) / total) : 0
    return {
      data: { total, success, failed: total - success, avgDurationMs: avg }
    }
  },
}
