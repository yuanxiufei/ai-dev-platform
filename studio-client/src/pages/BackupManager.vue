<template>
  <div class="backup-page">
    <div class="page-header">
      <h2>备份管理</h2>
      <p class="subtitle">导出/导入系统数据，支持后台异步执行与进度追踪</p>
    </div>

    <!-- 操作区 -->
    <div class="action-section">
      <div class="action-card">
        <h3>导出</h3>
        <p>将数据库、配置、会话记录等打包为 ZIP，后台异步执行</p>
        <button class="btn btn-primary" @click="doExport" :disabled="exporting">
          {{ exporting ? '导出任务创建中...' : '创建导出任务' }}
        </button>
      </div>
      <div class="action-card">
        <h3>导入</h3>
        <p>上传 ZIP 备份文件，恢复系统数据</p>
        <div class="import-upload">
          <input ref="fileInput" type="file" accept=".zip" @change="onFileSelected" class="file-input" />
          <button class="btn btn-primary" @click="doImport" :disabled="!selectedFile || importing">
            {{ importing ? '导入中...' : '开始导入' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 任务列表 -->
    <div class="task-section">
      <div class="section-header">
        <h3>任务列表</h3>
        <button class="btn btn-sm" @click="fetchTasks">刷新</button>
      </div>

      <div v-if="tasksLoading" class="loading">加载中...</div>

      <div v-else-if="tasks.length === 0" class="empty">暂无备份任务</div>

      <div v-else class="task-list">
        <div v-for="t in tasks" :key="t.task_id" class="task-card">
          <div class="task-header">
            <span class="task-id">{{ t.task_id.slice(0, 8) }}...</span>
            <span :class="['badge', statusClass(t.status)]">{{ t.status }}</span>
            <span class="badge">{{ t.type }}</span>
          </div>
          <div class="task-progress">
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: (t.progress * 100) + '%' }"></div>
            </div>
            <span class="progress-text">{{ (t.progress * 100).toFixed(0) }}%</span>
          </div>
          <div v-if="t.message" class="task-msg">{{ t.message }}</div>
          <div v-if="t.error" class="task-error">{{ t.error }}</div>
          <div class="task-actions">
            <a v-if="t.status === 'completed' && t.type === 'export'" :href="downloadLink(t.task_id)"
              class="btn btn-sm btn-outline">下载</a>
          </div>
        </div>
      </div>
    </div>

    <!-- 备份文件 -->
    <div class="files-section">
      <div class="section-header">
        <h3>本地备份文件</h3>
        <button class="btn btn-sm" @click="fetchFiles">刷新</button>
      </div>

      <div v-if="files.length === 0" class="empty">暂无备份文件</div>

      <div v-else class="file-list">
        <div v-for="f in files" :key="f.filename" class="file-card">
          <span class="file-name">{{ f.filename }}</span>
          <span class="file-size">{{ f.size_mb.toFixed(2) }} MB</span>
          <span class="file-date">{{ formatDate(f.created_at) }}</span>
          <a :href="downloadLink(f.filename)" class="btn btn-sm">下载</a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { backupApi, type BackupTask, type BackupFile } from '@/api/backup'

const tasks = ref<BackupTask[]>([])
const files = ref<BackupFile[]>([])
const tasksLoading = ref(false)
const exporting = ref(false)
const importing = ref(false)
const selectedFile = ref<File | null>(null)
const fileInput = ref<HTMLInputElement>()

function formatDate(ts?: string) {
  if (!ts) return '-'
  return new Date(ts).toLocaleString()
}

function statusClass(s: string) {
  return {
    pending: 'badge-pending',
    running: 'badge-running',
    completed: 'badge-ok',
    failed: 'badge-error',
  }[s] ?? ''
}

function downloadLink(taskId: string) {
  return `/api/v1/system/backup/export/${taskId}`
}

async function fetchTasks() {
  tasksLoading.value = true
  try {
    const res = await backupApi.listTasks()
    tasks.value = res.data ?? []
  } finally {
    tasksLoading.value = false
  }
}

async function fetchFiles() {
  try {
    const res = await backupApi.listFiles()
    files.value = (res.data as any)?.backups ?? res.data ?? []
  } catch { /* ignore */ }
}

async function doExport() {
  exporting.value = true
  try {
    await backupApi.triggerExport()
    await fetchTasks()
  } catch (e: any) {
    alert(`导出失败: ${e?.message ?? e}`)
  } finally {
    exporting.value = false
  }
}

function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
}

async function doImport() {
  if (!selectedFile.value) return
  importing.value = true
  try {
    await backupApi.triggerImport(selectedFile.value)
    selectedFile.value = null
    if (fileInput.value) fileInput.value.value = ''
    await fetchTasks()
  } catch (e: any) {
    alert(`导入失败: ${e?.message ?? e}`)
  } finally {
    importing.value = false
  }
}

onMounted(() => {
  fetchTasks()
  fetchFiles()
})
</script>

<style scoped>
.backup-page {
  max-width: 1000px;
  margin: 0 auto;
  padding: 24px;
}

.page-header h2 { margin: 0; font-size: 22px; }
.subtitle { color: var(--color-ide-text-secondary); margin: 4px 0 16px; font-size: 14px; }

.action-section {
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 28px;
}
.action-card {
  padding: 16px; border: 1px solid var(--color-ide-border);
  border-radius: 8px; background: var(--color-ide-bg-secondary);
}
.action-card h3 { margin: 0 0 6px; font-size: 15px; }
.action-card p { font-size: 13px; color: var(--color-ide-text-secondary); margin: 0 0 12px; }

.import-upload { display: flex; gap: 8px; align-items: center; }
.file-input { font-size: 13px; }

.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px;
}
.section-header h3 { margin: 0; font-size: 16px; }

.task-section { margin-bottom: 28px; }
.task-list { display: grid; gap: 10px; }
.task-card {
  padding: 12px; border: 1px solid var(--color-ide-border);
  border-radius: 8px; background: var(--color-ide-bg-secondary);
}
.task-header { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; }
.task-id { font-family: monospace; font-size: 13px; font-weight: 600; }
.task-progress { display: flex; align-items: center; gap: 10px; margin: 6px 0; }
.progress-bar {
  flex: 1; height: 6px; background: var(--color-ide-bg-tertiary);
  border-radius: 3px; overflow: hidden;
}
.progress-fill {
  height: 100%; background: var(--color-ide-accent);
  border-radius: 3px; transition: width 0.3s;
}
.progress-text { font-size: 12px; color: var(--color-ide-text-secondary); min-width: 36px; }
.task-msg { font-size: 12px; color: var(--color-ide-text-secondary); }
.task-error { font-size: 12px; color: #e05555; }
.task-actions { margin-top: 6px; }

.files-section { }
.file-list { display: grid; gap: 8px; }
.file-card {
  display: flex; justify-content: space-between; align-items: center;
  padding: 10px 14px; border: 1px solid var(--color-ide-border);
  border-radius: 8px; background: var(--color-ide-bg-secondary);
  font-size: 13px;
}
.file-name { font-weight: 600; flex: 1; }
.file-size { margin: 0 12px; color: var(--color-ide-text-secondary); }
.file-date { margin-right: 12px; color: var(--color-ide-text-secondary); font-size: 12px; }

.badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  background: var(--color-ide-bg-tertiary); color: var(--color-ide-text-secondary);
}
.badge-pending { background: #3a3a3a; color: #aaa; }
.badge-running { background: #1e4a6e; color: #64b5f6; }
.badge-ok { background: #1e3a2e; color: #81c784; }
.badge-error { background: #3e1a1a; color: #e57373; }

.loading, .empty { text-align: center; padding: 30px; color: var(--color-ide-text-secondary); font-size: 13px; }

.btn {
  padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer;
  font-size: 13px; background: var(--color-ide-bg-tertiary);
  color: var(--color-ide-text-primary);
  transition: opacity 0.15s;
}
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-outline { border: 1px solid var(--color-ide-border); background: transparent; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
a.btn { text-decoration: none; display: inline-block; }
</style>
