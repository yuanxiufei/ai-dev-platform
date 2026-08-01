<template>
  <div class="fs-explorer-page">
    <div class="page-header">
      <h2>文件浏览器</h2>
      <p class="subtitle">浏览、编辑、管理项目文件</p>
    </div>

    <div class="toolbar">
      <div class="path-bar">
        <span class="path-prefix">路径：</span>
        <span v-for="(seg, i) in pathSegments" :key="i" class="path-seg">
          <span v-if="i > 0" class="sep">/</span>
          <a @click="navigateTo(i)">{{ seg }}</a>
        </span>
        <button class="btn btn-sm" @click="refreshDir" title="刷新">🔄</button>
      </div>
      <div class="actions">
        <button class="btn btn-sm btn-primary" @click="showMkdir = true">+ 新建目录</button>
        <button class="btn btn-sm" @click="showNewFile = true">+ 新建文件</button>
      </div>
    </div>

    <!-- 新建目录 -->
    <div v-if="showMkdir" class="inline-form">
      <input v-model="newDirName" placeholder="目录名" class="input" @keyup.enter="createDir" />
      <button class="btn btn-primary btn-sm" @click="createDir">创建</button>
      <button class="btn btn-sm" @click="showMkdir = false">取消</button>
    </div>

    <!-- 新建文件 -->
    <div v-if="showNewFile" class="inline-form">
      <input v-model="newFileName" placeholder="文件名 (如 hello.py)" class="input" @keyup.enter="createFile" />
      <button class="btn btn-primary btn-sm" @click="createFile">创建</button>
      <button class="btn btn-sm" @click="showNewFile = false">取消</button>
    </div>

    <!-- 文件列表 -->
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="entries.length === 0" class="empty">此目录为空</div>
    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th style="width:32px"></th>
            <th>名称</th>
            <th>大小</th>
            <th>修改时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in entries" :key="e.name" :class="{ 'row-hidden': e.is_hidden }">
            <td>
              <span class="entry-icon">{{ e.type === 'directory' ? '📁' : '📄' }}</span>
            </td>
            <td>
              <span v-if="e.type === 'directory'" class="entry-link" @click="enterDir(e.name)">
                {{ e.name }}/
              </span>
              <span v-else class="entry-name" @click="openFile(e.path || e.name)">
                {{ e.name }}
              </span>
            </td>
            <td class="size-cell">{{ e.type === 'directory' ? '—' : formatSize(e.size_bytes) }}</td>
            <td class="time-cell">{{ formatTime(e.modified_at) }}</td>
            <td class="actions-cell">
              <button v-if="e.type === 'directory'" class="btn btn-sm" @click="enterDir(e.name)">打开</button>
              <button v-else class="btn btn-sm" @click="openFile(e.path || e.name)">查看</button>
              <button class="btn btn-sm" @click="startRename(e)" v-if="!renaming || renaming.name !== e.name">重命名</button>
              <button class="btn btn-sm btn-danger" @click="deleteEntry(e)">删除</button>
            </td>
          </tr>
          <!-- 重命名行 -->
          <tr v-if="renaming">
            <td colspan="5" class="rename-row">
              <input v-model="renameTo" placeholder="新名称" class="input" @keyup.enter="doRename" />
              <button class="btn btn-primary btn-sm" @click="doRename">确认</button>
              <button class="btn btn-sm" @click="renaming = null">取消</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 文件内容预览弹窗 -->
    <div v-if="previewFile" class="modal-mask" @click.self="previewFile = null">
      <div class="modal-card wide">
        <div class="modal-header">
          <h4>{{ previewPath }}</h4>
          <div class="modal-header-actions">
            <button class="btn btn-sm" @click="toggleEdit" v-if="!editing">编辑</button>
            <button class="btn btn-primary btn-sm" @click="saveFile" v-if="editing">保存</button>
            <button class="btn btn-sm" @click="previewFile = null">关闭</button>
          </div>
        </div>
        <div v-if="previewLoading" class="loading">加载中...</div>
        <textarea v-else-if="editing" v-model="editContent" class="edit-area"></textarea>
        <pre v-else class="preview-content">{{ previewContent }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { filesystemApi, type FileEntry } from '@/api/filesystem'

const currentPath = ref('.')
const entries = ref<FileEntry[]>([])
const loading = ref(false)

const showMkdir = ref(false)
const newDirName = ref('')
const showNewFile = ref(false)
const newFileName = ref('')

const renaming = ref<FileEntry | null>(null)
const renameTo = ref('')

const previewFile = ref<string | null>(null)
const previewPath = ref('')
const previewContent = ref('')
const previewLoading = ref(false)
const editing = ref(false)
const editContent = ref('')

const pathSegments = computed(() => {
  return currentPath.value.replace(/\\/g, '/').split('/').filter(Boolean)
})

function formatSize(bytes?: number) {
  if (!bytes) return '—'
  return bytes >= 1024 * 1024 ? (bytes / (1024 * 1024)).toFixed(1) + ' MB' :
         bytes >= 1024 ? (bytes / 1024).toFixed(1) + ' KB' : bytes + ' B'
}

function formatTime(ts?: number) {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleString()
}

async function refreshDir() {
  loading.value = true
  try {
    const res = await filesystemApi.listDir(currentPath.value)
    entries.value = res.data?.entries ?? res.data ?? []
    // 目录在前，文件在后，按名称排序
    entries.value.sort((a: FileEntry, b: FileEntry) => {
      if (a.type !== b.type) return a.type === 'directory' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
  } finally {
    loading.value = false
  }
}

function navigateTo(i: number) {
  const segs = pathSegments.value.slice(0, i + 1)
  currentPath.value = segs.join('/') || '.'
  refreshDir()
}

function enterDir(name: string) {
  currentPath.value = currentPath.value === '.' ? name : currentPath.value + '/' + name
  refreshDir()
}

async function createDir() {
  if (!newDirName.value.trim()) return
  const target = currentPath.value === '.'
    ? newDirName.value
    : currentPath.value + '/' + newDirName.value
  await filesystemApi.mkdir(target)
  showMkdir.value = false
  newDirName.value = ''
  refreshDir()
}

async function createFile() {
  if (!newFileName.value.trim()) return
  const target = currentPath.value === '.'
    ? newFileName.value
    : currentPath.value + '/' + newFileName.value
  await filesystemApi.writeFile(target, '')
  showNewFile.value = false
  newFileName.value = ''
  refreshDir()
}

async function openFile(path: string) {
  previewPath.value = path
  previewLoading.value = true
  previewFile.value = path
  try {
    const res = await filesystemApi.readFile(path)
    previewContent.value = typeof res.data === 'string' ? res.data : res.data?.content ?? ''
  } catch {
    previewContent.value = '[读取失败]'
  } finally {
    previewLoading.value = false
  }
}

function toggleEdit() {
  editing.value = true
  editContent.value = previewContent.value
}

async function saveFile() {
  if (!previewFile.value) return
  await filesystemApi.writeFile(previewFile.value, editContent.value)
  editing.value = false
  previewContent.value = editContent.value
}

function startRename(e: FileEntry) {
  renaming.value = e
  renameTo.value = e.name
}

async function doRename() {
  if (!renaming.value || !renameTo.value.trim()) return
  const src = currentPath.value === '.' ? renaming.value.name : currentPath.value + '/' + renaming.value.name
  const dst = currentPath.value === '.' ? renameTo.value : currentPath.value + '/' + renameTo.value
  await filesystemApi.move(src, dst)
  renaming.value = null
  refreshDir()
}

async function deleteEntry(e: FileEntry) {
  if (!confirm(`确认删除 "${e.name}"？`)) return
  const path = currentPath.value === '.' ? e.name : currentPath.value + '/' + e.name
  await filesystemApi.delete(path, e.type === 'directory')
  refreshDir()
}

onMounted(() => refreshDir())
</script>

<style scoped>
.fs-explorer-page { padding: 24px; }
.page-header { margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 20px; }
.subtitle { color: var(--color-ide-fg-secondary); margin: 4px 0 0; font-size: 13px; }

.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.path-bar { display: flex; align-items: center; gap: 2px; font-family: monospace; font-size: 13px; }
.path-prefix { color: var(--color-ide-fg-secondary); }
.path-seg a { color: var(--color-ide-accent, #4fc1ff); cursor: pointer; text-decoration: none; }
.path-seg a:hover { text-decoration: underline; }
.sep { color: var(--color-ide-fg-secondary); margin: 0 2px; }
.actions { display: flex; gap: 6px; }

.inline-form { display: flex; gap: 8px; align-items: center; padding: 10px 14px; border: 1px solid var(--color-ide-accent); border-radius: 8px; margin-bottom: 12px; }

.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--color-ide-border); font-size: 13px; }
th { font-size: 12px; color: var(--color-ide-fg-secondary); font-weight: 600; }
.row-hidden { opacity: 0.45; }
.entry-icon { width: 24px; display: inline-block; text-align: center; }
.entry-link { color: var(--color-ide-accent, #4fc1ff); cursor: pointer; font-weight: 500; }
.entry-link:hover { text-decoration: underline; }
.entry-name { cursor: pointer; }
.size-cell, .time-cell { font-size: 12px; color: var(--color-ide-fg-secondary); white-space: nowrap; }
.actions-cell { display: flex; gap: 4px; flex-wrap: wrap; }
.rename-row { padding: 10px 12px; }
.rename-row .input { margin-right: 8px; }

.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-card { background: var(--color-ide-bg); border: 1px solid var(--color-ide-border); border-radius: 12px; padding: 24px; min-width: 500px; max-width: 90vw; max-height: 85vh; display: flex; flex-direction: column; }
.modal-card.wide { min-width: 700px; }
.modal-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.modal-header h4 { margin: 0; font-size: 15px; }
.modal-header-actions { display: flex; gap: 6px; }
.preview-content { font-size: 12px; line-height: 1.5; background: var(--color-ide-bg-secondary); padding: 14px; border-radius: 6px; overflow: auto; max-height: 60vh; font-family: monospace; white-space: pre-wrap; word-break: break-all; }
.edit-area { width: 100%; min-height: 400px; font-family: monospace; font-size: 13px; background: var(--color-ide-bg-secondary); color: var(--color-ide-fg); border: 1px solid var(--color-ide-border); border-radius: 6px; padding: 12px; resize: vertical; }

.loading, .empty { padding: 48px 0; text-align: center; color: var(--color-ide-fg-secondary); }

.input { background: var(--color-ide-bg-secondary); border: 1px solid var(--color-ide-border); border-radius: 6px; padding: 6px 10px; font-size: 13px; color: var(--color-ide-fg); }
.btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid var(--color-ide-border); background: var(--color-ide-bg); color: var(--color-ide-fg); }
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--color-ide-accent, #4fc1ff); color: #fff; border-color: var(--color-ide-accent, #4fc1ff); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-danger { color: #cf222e; border-color: #cf222e; background: transparent; }
</style>
