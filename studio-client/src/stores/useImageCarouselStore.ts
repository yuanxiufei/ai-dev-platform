/**
 * useImageCarouselStore — 图片轮播编辑器
 *
 * 对标 VSCode 内置图片查看器 (customEditor for images)
 * 支持: 缩放、前后导航、键盘控制、缩略图条
 */
import { defineStore } from "pinia"
import { computed, ref } from "vue"

/** 支持的图片扩展名 */
export const IMAGE_EXTENSIONS = new Set([
  ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
  ".bmp", ".ico", ".tiff", ".tif", ".avif", ".apng",
])

/** 支持的视频扩展名 */
export const VIDEO_EXTENSIONS = new Set([
  ".mp4", ".webm", ".ogg", ".mov", ".avi", ".mkv",
])

/** 判断是否为可预览的媒体文件 */
export function isMediaFile(name: string): boolean {
  const ext = "." + (name.split(".").pop()?.toLowerCase() ?? "")
  return IMAGE_EXTENSIONS.has(ext) || VIDEO_EXTENSIONS.has(ext)
}

export function isImageFile(name: string): boolean {
  const ext = "." + (name.split(".").pop()?.toLowerCase() ?? "")
  return IMAGE_EXTENSIONS.has(ext)
}

export function isVideoFile(name: string): boolean {
  const ext = "." + (name.split(".").pop()?.toLowerCase() ?? "")
  return VIDEO_EXTENSIONS.has(ext)
}

export interface MediaItem {
  path: string
  name: string
  type: "image" | "video"
}

export const useImageCarouselStore = defineStore("imageCarousel", () => {
  const visible = ref(false)
  const items = ref<MediaItem[]>([])
  const currentIndex = ref(0)
  const zoom = ref(1)
  const fitMode = ref<"contain" | "cover" | "fill">("contain")

  const currentItem = computed<MediaItem | null>(() =>
    items.value.length > 0 && currentIndex.value >= 0 && currentIndex.value < items.value.length
      ? items.value[currentIndex.value]
      : null,
  )

  const hasPrev = computed(() => currentIndex.value > 0)
  const hasNext = computed(() => currentIndex.value < items.value.length - 1)
  const totalCount = computed(() => items.value.length)

  /** 从同目录收集所有媒体文件并打开 */
  function open(filePath: string, allFiles?: { name: string; path: string; isDir: boolean }[]): void {
    const fileName = filePath.split(/[/\\]/).pop() ?? filePath
    const dirPath = filePath.replace(/[/\\][^/\\]+$/, "")

    let mediaItems: MediaItem[] = []

    if (allFiles && allFiles.length > 0) {
      // 从提供的文件列表中筛选同目录媒体文件
      mediaItems = allFiles
        .filter((f) => !f.isDir && isMediaFile(f.name))
        .sort((a, b) => a.name.toLowerCase().localeCompare(b.name.toLowerCase()))
        .map((f) => ({
          path: f.path,
          name: f.name,
          type: isVideoFile(f.name) ? "video" : "image",
        } as MediaItem))
    }

    // 回退：仅当前文件
    if (mediaItems.length === 0) {
      mediaItems = [{
        path: filePath,
        name: fileName,
        type: isVideoFile(fileName) ? "video" : "image",
      }]
    }

    const targetIdx = mediaItems.findIndex((m) => m.path === filePath)
    items.value = mediaItems
    currentIndex.value = targetIdx >= 0 ? targetIdx : 0
    zoom.value = 1
    fitMode.value = "contain"
    visible.value = true
  }

  function close(): void {
    visible.value = false
    items.value = []
    currentIndex.value = 0
  }

  function next(): void {
    if (hasNext.value) {
      currentIndex.value++
      zoom.value = 1
    }
  }

  function prev(): void {
    if (hasPrev.value) {
      currentIndex.value--
      zoom.value = 1
    }
  }

  function zoomIn(): void {
    zoom.value = Math.min(5, zoom.value + 0.25)
  }

  function zoomOut(): void {
    zoom.value = Math.max(0.1, zoom.value - 0.25)
  }

  function resetZoom(): void {
    zoom.value = 1
    fitMode.value = "contain"
  }

  function toggleFitMode(): void {
    const modes: Array<"contain" | "cover" | "fill"> = ["contain", "cover", "fill"]
    const idx = modes.indexOf(fitMode.value)
    fitMode.value = modes[(idx + 1) % modes.length]
  }

  /** 若打开的视频文件，创建 blob URL + 回退到原始路径 */
  function getMediaUrl(): string {
    const item = currentItem.value
    if (!item) return ""
    // 对于本地文件路径，直接使用路径（由后端静态文件服务或 base64 处理）
    // 此处直接返回文件路径，实际渲染时按需获取
    return item.path
  }

  return {
    visible,
    items,
    currentIndex,
    zoom,
    fitMode,
    currentItem,
    hasPrev,
    hasNext,
    totalCount,
    open,
    close,
    next,
    prev,
    zoomIn,
    zoomOut,
    resetZoom,
    toggleFitMode,
    getMediaUrl,
  }
})
