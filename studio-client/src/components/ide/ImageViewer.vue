<template>
  <div class="image-viewer" ref="containerRef">
    <!-- 工具栏 -->
    <div class="image-toolbar" v-if="!loading && !error">
      <button @click="zoomIn" :disabled="scale >= MAX_SCALE" title="Zoom In">🔍+</button>
      <button @click="zoomOut" :disabled="scale <= MIN_SCALE" title="Zoom Out">🔍-</button>
      <button @click="resetZoom" title="Reset">1:1</button>
      <button @click="fitToScreen" title="Fit">📐</button>
      <span class="image-info">{{ Math.round(scale * 100) }}% | {{ naturalWidth }}×{{ naturalHeight }}</span>
      <button v-if="canCopy" @click="copyImage" title="Copy">📋</button>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="image-placeholder">Loading image...</div>

    <!-- 错误 -->
    <div v-else-if="error" class="image-placeholder error">{{ error }}</div>

    <!-- 图片 (可缩放/拖拽) -->
    <div
      v-else
      class="image-canvas"
      @wheel.prevent="onWheel"
      @mousedown="startDrag"
      @mousemove="onDrag"
      @mouseup="endDrag"
      @mouseleave="endDrag"
      :style="{ cursor: dragging ? 'grabbing' : 'grab' }"
    >
      <img
        ref="imgRef"
        :src="src"
        :alt="alt"
        :style="imgStyle"
        @load="onLoad"
        @error="onError"
        draggable="false"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ImageViewer — 图片查看器 (缩放/拖拽/复制)
 *
 * 对标: VSCode image preview with zoom + pan
 * 用法:
 *   <ImageViewer src="file:///path/to/image.png" alt="screenshot" />
 */

import { ref, computed, onMounted, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  src: string
  alt?: string
  maxZoom?: number
  minZoom?: number
}>(), {
  alt: '',
  maxZoom: 5,
  minZoom: 0.1,
})

const MAX_SCALE = props.maxZoom
const MIN_SCALE = props.minZoom

const containerRef = ref<HTMLDivElement | null>(null)
const imgRef = ref<HTMLImageElement | null>(null)
const loading = ref(true)
const error = ref('')
const scale = ref(1)
const offsetX = ref(0)
const offsetY = ref(0)
const naturalWidth = ref(0)
const naturalHeight = ref(0)
const dragging = ref(false)
const dragStart = ref({ x: 0, y: 0 })
const posStart = ref({ x: 0, y: 0 })

const canCopy = computed(() => typeof ClipboardItem !== 'undefined')

const imgStyle = computed(() => ({
  transform: `translate(${offsetX.value}px, ${offsetY.value}px) scale(${scale.value})`,
  transformOrigin: '0 0',
  transition: dragging.value ? 'none' : 'transform 0.1s ease',
  maxWidth: 'none',
  maxHeight: 'none',
}))

function onLoad() {
  loading.value = false
  const img = imgRef.value
  if (img) {
    naturalWidth.value = img.naturalWidth
    naturalHeight.value = img.naturalHeight
  }
  fitToScreen()
}

function onError() {
  loading.value = false
  error.value = 'Failed to load image'
}

function zoomIn() {
  scale.value = Math.min(MAX_SCALE, scale.value * 1.25)
}

function zoomOut() {
  scale.value = Math.max(MIN_SCALE, scale.value / 1.25)
}

function resetZoom() {
  scale.value = 1
  offsetX.value = 0
  offsetY.value = 0
}

function fitToScreen() {
  const container = containerRef.value
  if (!container || !imgRef.value) return
  const cw = container.clientWidth - 16
  const ch = container.clientHeight - 56
  if (naturalWidth.value === 0 || naturalHeight.value === 0) return
  const fitScale = Math.min(cw / naturalWidth.value, ch / naturalHeight.value, 1)
  scale.value = fitScale
  offsetX.value = (cw - naturalWidth.value * fitScale) / 2
  offsetY.value = (ch - naturalHeight.value * fitScale) / 2
}

function onWheel(e: WheelEvent) {
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  const newScale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale.value * delta))

  // Zoom centered on mouse position
  const rect = containerRef.value?.getBoundingClientRect()
  if (rect) {
    const mx = e.clientX - rect.left - offsetX.value
    const my = e.clientY - rect.top - offsetY.value
    const ratio = newScale / scale.value
    offsetX.value = e.clientX - rect.left - mx * ratio
    offsetY.value = e.clientY - rect.top - my * ratio
  }
  scale.value = newScale
}

function startDrag(e: MouseEvent) {
  if (scale.value <= 1 && offsetX.value === 0 && offsetY.value === 0) return
  dragging.value = true
  dragStart.value = { x: e.clientX, y: e.clientY }
  posStart.value = { x: offsetX.value, y: offsetY.value }
}

function onDrag(e: MouseEvent) {
  if (!dragging.value) return
  offsetX.value = posStart.value.x + (e.clientX - dragStart.value.x)
  offsetY.value = posStart.value.y + (e.clientY - dragStart.value.y)
}

function endDrag() { dragging.value = false }

async function copyImage() {
  try {
    const img = imgRef.value
    if (!img) return
    const canvas = document.createElement('canvas')
    canvas.width = img.naturalWidth
    canvas.height = img.naturalHeight
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    ctx.drawImage(img, 0, 0)
    const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve))
    if (!blob) return
    await navigator.clipboard.write([new ClipboardItem({ [blob.type]: blob })])
  } catch { /* 复制失败静默处理 */ }
}

function onResize() {
  if (scale.value <= 1) fitToScreen()
}

onMounted(() => window.addEventListener('resize', onResize))
onUnmounted(() => window.removeEventListener('resize', onResize))
</script>

<style scoped>
.image-viewer {
  width: 100%; height: 100%;
  background: #12121a;
  display: flex; flex-direction: column;
  overflow: hidden;
}
.image-toolbar {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 12px;
  background: #1a1a2e; border-bottom: 1px solid #2e2e44;
  flex-shrink: 0;
}
.image-toolbar button {
  background: #2a2a44; border: none; color: #c0c0d8;
  padding: 4px 10px; border-radius: 6px; cursor: pointer; font-size: 13px;
}
.image-toolbar button:hover:not(:disabled) { background: #3b3b6e; }
.image-toolbar button:disabled { opacity: 0.35; cursor: default; }
.image-info {
  margin-left: auto; font-size: 12px; color: #8888a8;
}
.image-canvas {
  flex: 1; overflow: hidden; position: relative;
  display: flex; align-items: flex-start; justify-content: flex-start;
}
.image-canvas img {
  user-select: none;
  image-rendering: auto;
}
.image-placeholder {
  flex: 1; display: flex; align-items: center; justify-content: center;
  color: #6e6e88; font-size: 14px;
}
.image-placeholder.error { color: #d96666; }
</style>
