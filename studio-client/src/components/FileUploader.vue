<script setup lang="ts">
/**
 * 文件上传组件 — 增强版
 *
 * 借鉴 RAGFlow FileUpload (1429-line) 的设计思路：
 * - 拖拽区域带视觉反馈（高亮边框 + 背景色变化）
 * - 文件列表：名称、大小、类型图标、进度条、状态徽章
 * - 单个文件移除 / 清空全部
 * - 剪贴板粘贴支持
 * - per-file 状态管理 (idle → uploading → done / error)
 *
 * ...existing patterns...
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue"
import {
  AlertCircle,
  CheckCircle2,
  File as FileIcon,
  FileJson,
  FileText,
  Image,
  Loader2,
  Upload,
  X,
} from "lucide-vue-next"

/* ========== Props / Emits ========== */

const props = defineProps<{
  accept?: string
  multiple?: boolean
  maxSizeMb?: number
  /** 自定义上传函数，返回 { ok, error } */
  onUpload: (files: File[]) => Promise<{ ok: number; errors: { filename: string; error: string }[] }>
}>()

const emit = defineEmits<{
  (e: "complete", result: { ok: number; errors: { filename: string; error: string }[] }): void
  (e: "files-changed", files: File[]): void
}>()

/* ========== 文件条目 ========== */

type FileStatus = "idle" | "uploading" | "done" | "error"

interface FileEntry {
  id: string
  file: File
  status: FileStatus
  progress: number
  error?: string
  result?: { chunks: number }
}

const entries = ref<FileEntry[]>([])

/* ========== 状态 ========== */

const uploading = ref(false)
const dragOver = ref(false)
const dropZone = ref<HTMLDivElement>()
const fileInput = ref<HTMLInputElement>()
const progressTotal = ref(0)
const progressCurrent = ref(0)

const dropZoneClass = computed(() => ({
  "file-uploader__zone": true,
  "file-uploader__zone--over": dragOver.value,
  "file-uploader__zone--has-files": entries.value.length > 0,
}))

const formatSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** 根据文件名返回图标组件 */
function fileTypeIcon(filename: string) {
  const ext = filename.split(".").pop()?.toLowerCase() ?? ""
  if (["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp"].includes(ext)) return Image
  if (["json"].includes(ext)) return FileJson
  if (["md", "txt", "csv", "log"].includes(ext)) return FileText
  return FileIcon
}

/* ========== 文件管理 ========== */

const maxSize = computed(() => (props.maxSizeMb ?? 10) * 1024 * 1024)

function addFiles(files: File[]) {
  const valid: File[] = []
  for (const f of files) {
    if (f.size > maxSize.value) {
      entries.value.push({
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        file: f,
        status: "error",
        progress: 1,
        error: `文件超过 ${props.maxSizeMb ?? 10}MB 限制`,
      })
      continue
    }
    // 去重
    if (entries.value.some((e) => e.file.name === f.name && e.file.size === f.size)) continue
    valid.push(f)
    entries.value.push({
      id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      file: f,
      status: "idle",
      progress: 0,
    })
  }
  if (valid.length > 0) emit("files-changed", valid)
}

function removeEntry(id: string) {
  entries.value = entries.value.filter((e) => e.id !== id)
}

function clearAll() {
  entries.value = []
}

const readyFiles = computed(() =>
  entries.value.filter((e) => e.file instanceof File && e.status === "idle"),
)

/* ========== 文件输入 ========== */

function triggerFileDialog() {
  fileInput.value?.click()
}

function onInputChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.length) {
    addFiles(Array.from(input.files))
    input.value = ""
  }
}

/* ========== 拖拽 ========== */

function onDragOver(e: DragEvent) {
  e.preventDefault()
  dragOver.value = true
}

function onDragLeave(e: DragEvent) {
  e.preventDefault()
  dragOver.value = false
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  dragOver.value = false
  const files = e.dataTransfer?.files
  if (files?.length) addFiles(Array.from(files))
}

/* ========== 剪贴板粘贴 ========== */

function onPaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  const files: File[] = []
  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    if (item.kind === "file") {
      const f = item.getAsFile()
      if (f) files.push(f)
    }
  }
  if (files.length > 0) {
    e.preventDefault()
    addFiles(files)
  }
}

/* ========== 上传 ========== */

async function doUpload() {
  if (uploading.value || readyFiles.value.length === 0) return
  uploading.value = true

  // 标记所有待上传文件
  for (const e of readyFiles.value) {
    e.status = "uploading"
    e.progress = 0
    e.error = undefined
  }

  // 模拟进度栏（后端不支持分块上传进度，所以用模拟动画）
  const progressInterval = startProgressAnimation()

  try {
    const files = readyFiles.value.map((e) => e.file)
    const result = await props.onUpload(files)

    // 更新状态
    for (const e of readyFiles.value) {
      e.progress = 1
      const matchErr = result.errors.find((err) => err.filename === e.file.name)
      if (matchErr) {
        e.status = "error"
        e.error = matchErr.error
      } else {
        e.status = "done"
        e.result = { chunks: 0 }
      }
    }

    emit("complete", result)
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : "上传失败"
    for (const e of readyFiles.value) {
      e.status = "error"
      e.error = msg
      e.progress = 1
    }
    emit("complete", { ok: 0, errors: [{ filename: "", error: msg }] })
  } finally {
    clearInterval(progressInterval)
    progressTotal.value = 1
    progressCurrent.value = 1
    uploading.value = false
  }
}

/** 模拟进度，给用户视觉反馈 */
function startProgressAnimation() {
  return setInterval(() => {
    for (const e of readyFiles.value) {
      // 最多到 90%，剩余 10% 留给实际结果
      e.progress = Math.min(e.progress + Math.random() * 0.1, 0.9)
    }
  }, 300)
}

/* ========== 生命周期 ========== */

onMounted(() => {
  document.addEventListener("paste", onPaste)
})

onBeforeUnmount(() => {
  document.removeEventListener("paste", onPaste)
})

defineExpose({ entries, addFiles, clearAll, doUpload })
</script>

<template>
  <div class="file-uploader" @paste="onPaste">
    <!-- 拖拽区域 -->
    <div
      ref="dropZone"
      :class="dropZoneClass"
      @dragover.prevent="onDragOver"
      @dragleave.prevent="onDragLeave"
      @drop.prevent="onDrop"
      @click="triggerFileDialog"
    >
      <input
        ref="fileInput"
        type="file"
        class="file-uploader__input"
        :accept="accept"
        :multiple="multiple ?? true"
        @change="onInputChange"
      />

      <div class="file-uploader__zone-content">
        <div class="file-uploader__zone-icon">
          <Upload :size="28" />
        </div>
        <p class="file-uploader__zone-title">
          拖拽文件到此处，或<span class="file-uploader__zone-link">点击这里选择文件</span>
        </p>
        <p class="file-uploader__zone-hint">
          支持粘贴（Ctrl+V）、拖拽或点击选择 · 单个文件最大 {{ maxSizeMb ?? 10 }}MB
          <template v-if="accept"> · {{ accept }}</template>
        </p>
      </div>
    </div>

    <!-- 文件列表 -->
    <div v-if="entries.length > 0" class="file-uploader__list">
      <!-- 列表头 -->
      <div class="file-uploader__list-header">
        <span class="file-uploader__list-count">
          {{ entries.length }} 个文件
          <template v-if="readyFiles.length > 0 && !uploading">
            · {{ readyFiles.length }} 个待上传
          </template>
        </span>
        <div class="file-uploader__list-actions">
          <button
            v-if="!uploading"
            class="file-uploader__btn-clear"
            @click="clearAll"
          >
            清空全部
          </button>
        </div>
      </div>

      <!-- 文件条目 -->
      <TransitionGroup name="file-list" tag="div" class="space-y-1.5">
        <div
          v-for="entry in entries"
          :key="entry.id"
          class="file-uploader__item"
          :class="`file-uploader__item--${entry.status}`"
        >
          <!-- 图标 -->
          <component :is="fileTypeIcon(entry.file.name)" :size="18" class="file-uploader__item-icon shrink-0" />

          <!-- 文件信息 -->
          <div class="file-uploader__item-info">
            <p class="file-uploader__item-name">{{ entry.file.name }}</p>
            <p class="file-uploader__item-size">{{ formatSize(entry.file.size) }}</p>
          </div>

          <!-- 进度条 -->
          <div class="file-uploader__item-progress-wrap">
            <div
              class="file-uploader__item-progress"
              :class="{
                'file-uploader__item-progress--done': entry.status === 'done',
                'file-uploader__item-progress--error': entry.status === 'error',
              }"
              :style="{ width: `${entry.progress * 100}%` }"
            />
          </div>

          <!-- 状态 / 错误 -->
          <div v-if="entry.status === 'uploading'" class="file-uploader__item-status file-uploader__item-status--loading">
            <Loader2 :size="14" class="animate-spin" />
          </div>
          <div v-else-if="entry.status === 'done'" class="file-uploader__item-status file-uploader__item-status--done">
            <CheckCircle2 :size="14" />
          </div>
          <div v-else-if="entry.status === 'error'" class="file-uploader__item-status file-uploader__item-status--error" :title="entry.error">
            <AlertCircle :size="14" />
          </div>

          <!-- 移除按钮（仅 idle/error 可移除） -->
          <button
            v-if="entry.status === 'idle' || entry.status === 'error'"
            class="file-uploader__item-remove"
            @click.stop="removeEntry(entry.id)"
          >
            <X :size="14" />
          </button>
        </div>
      </TransitionGroup>

      <!-- 上传按钮 -->
      <div v-if="readyFiles.length > 0 && !uploading" class="file-uploader__upload-bar">
        <button
          class="file-uploader__btn-upload"
          @click="doUpload"
        >
          <Upload :size="16" />
          上传 {{ readyFiles.length }} 个文件
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ======== 组件容器 ======== */
.file-uploader {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

/* ======== 拖拽区域 ======== */
.file-uploader__zone {
  position: relative;
  border: 2px dashed var(--color-ide-border);
  border-radius: 12px;
  padding: 32px 24px;
  text-align: center;
  cursor: pointer;
  transition: all 0.2s ease;
  background: var(--color-ide-panel-bg);
}
.file-uploader__zone:hover {
  border-color: var(--color-ide-accent);
  background: var(--color-ide-bg);
}
.file-uploader__zone--over {
  border-color: var(--color-ide-accent);
  background: color-mix(in srgb, var(--color-ide-accent) 6%, var(--color-ide-bg));
  box-shadow: 0 0 20px color-mix(in srgb, var(--color-ide-accent) 12%, transparent);
}
.file-uploader__zone--has-files {
  padding: 16px 24px;
}

.file-uploader__input {
  position: absolute;
  inset: 0;
  opacity: 0;
  cursor: pointer;
}

.file-uploader__zone-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.file-uploader__zone-icon {
  color: var(--color-ide-text-secondary);
  opacity: 0.6;
}

.file-uploader__zone-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-ide-text);
  margin: 0;
}

.file-uploader__zone-link {
  color: var(--color-ide-accent);
  text-decoration: underline;
  text-underline-offset: 2px;
}

.file-uploader__zone-hint {
  font-size: 11px;
  color: var(--color-ide-text-secondary);
  margin: 0;
  line-height: 1.4;
}

/* ======== 文件列表 ======== */
.file-uploader__list {
  border: 1px solid var(--color-ide-border);
  border-radius: 12px;
  background: var(--color-ide-panel-bg);
  overflow: hidden;
}

.file-uploader__list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--color-ide-border);
}

.file-uploader__list-count {
  font-size: 12px;
  color: var(--color-ide-text-secondary);
  font-weight: 500;
}

.file-uploader__btn-clear {
  font-size: 11px;
  color: var(--color-ide-text-secondary);
  padding: 2px 8px;
  border-radius: 4px;
  transition: all 0.15s;
}
.file-uploader__btn-clear:hover {
  color: var(--color-ide-error);
  background: color-mix(in srgb, var(--color-ide-error) 10%, transparent);
}

/* ======== 文件条目 ======== */
.file-uploader__item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  transition: background 0.15s;
}
.file-uploader__item:hover {
  background: var(--color-ide-hover);
}

.file-uploader__item-icon {
  color: var(--color-ide-text-secondary);
}

.file-uploader__item-info {
  flex: 1;
  min-width: 0;
}

.file-uploader__item-name {
  font-size: 13px;
  color: var(--color-ide-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin: 0;
  line-height: 1.4;
}

.file-uploader__item-size {
  font-size: 11px;
  color: var(--color-ide-text-secondary);
  margin: 0;
}

/* ======== 进度条 ======== */
.file-uploader__item-progress-wrap {
  width: 80px;
  height: 4px;
  background: var(--color-ide-border);
  border-radius: 2px;
  overflow: hidden;
  flex-shrink: 0;
}

.file-uploader__item-progress {
  height: 100%;
  background: var(--color-ide-accent);
  border-radius: 2px;
  transition: width 0.3s ease;
  width: 0;
}

.file-uploader__item-progress--done {
  background: #22c55e;
}

.file-uploader__item-progress--error {
  background: var(--color-ide-error);
}

/* ======== 状态图标 ======== */
.file-uploader__item-status {
  flex-shrink: 0;
  width: 20px;
  display: flex;
  justify-content: center;
}
.file-uploader__item-status--loading {
  color: var(--color-ide-accent);
}
.file-uploader__item-status--done {
  color: #22c55e;
}
.file-uploader__item-status--error {
  color: var(--color-ide-error);
}

/* ======== 移除按钮 ======== */
.file-uploader__item-remove {
  flex-shrink: 0;
  color: var(--color-ide-text-secondary);
  padding: 2px;
  border-radius: 4px;
  opacity: 0;
  transition: all 0.15s;
}
.file-uploader__item:hover .file-uploader__item-remove {
  opacity: 1;
}
.file-uploader__item-remove:hover {
  color: var(--color-ide-error);
  background: color-mix(in srgb, var(--color-ide-error) 10%, transparent);
}

/* ======== 错误条目高亮 ======== */
.file-uploader__item--error {
  background: color-mix(in srgb, var(--color-ide-error) 4%, transparent);
}

/* ======== 上传按钮 ======== */
.file-uploader__upload-bar {
  padding: 10px 14px;
  border-top: 1px solid var(--color-ide-border);
}

.file-uploader__btn-upload {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  background: var(--color-ide-accent);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  border-radius: 8px;
  transition: all 0.2s;
}
.file-uploader__btn-upload:hover {
  opacity: 0.9;
  transform: scale(1.01);
}
.file-uploader__btn-upload:active {
  transform: scale(0.98);
}

/* ======== 列表动画 ======== */
.file-list-enter-active,
.file-list-leave-active {
  transition: all 0.25s ease;
}
.file-list-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}
.file-list-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
.file-list-move {
  transition: transform 0.25s ease;
}
</style>
