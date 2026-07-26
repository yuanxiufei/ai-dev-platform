import { client } from './client'

export interface BackupTask {
  task_id: string
  type: 'export' | 'import'
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: number
  message: string
  result?: Record<string, any> | null
  error?: string | null
  created_at: string
  updated_at: string
}

export interface BackupFile {
  filename: string
  size_bytes: number
  size_mb: number
  created_at: string
}

export const backupApi = {
  /** 触发全量导出 */
  triggerExport() {
    return client.post<{ task_id: string; status: string; message: string }>('/api/v1/system/backup/export')
  },

  /** 下载导出 ZIP */
  getDownloadUrl(taskId: string) {
    return `/api/v1/system/backup/export/${taskId}`
  },

  /** 上传 ZIP 并恢复 */
  triggerImport(file: File) {
    const form = new FormData()
    form.append('file', file)
    return client.post<{ task_id: string; status: string; message: string }>(
      '/api/v1/system/backup/import',
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
  },

  /** 任务列表 */
  listTasks(params?: { task_type?: string; status?: string }) {
    return client.get<BackupTask[]>('/api/v1/system/backup/status', { params })
  },

  /** 单个任务状态 */
  getTask(taskId: string) {
    return client.get<BackupTask>(`/api/v1/system/backup/status/${taskId}`)
  },

  /** 本地备份文件列表 */
  listFiles() {
    return client.get<{ backups: BackupFile[]; total: number }>('/api/v1/system/backup/files')
  },
}
