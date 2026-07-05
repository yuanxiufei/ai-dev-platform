<script setup lang="ts">
/**
 * ImageCarousel — 图片/视频轮播查看器
 *
 * 对标 VSCode 内置图片查看器 (imagePreview custom editor)
 * 支持: 缩放/拖拽/导航/键盘/缩略图条
 */
import { computed, onMounted, onUnmounted, ref, watch } from "vue"
import { useImageCarouselStore } from "@/stores/useImageCarouselStore"
import { useThemeStore } from "@/stores/useThemeStore"
import {
  X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut,
  RotateCw, Maximize2, Minimize2, Play,
} from "lucide-vue-next"

const store = useImageCarouselStore()
const themeStore = useThemeStore()

const imageRef = ref<HTMLImageElement | null>(null)
const videoRef = ref<HTMLVideoElement | null>(null)
const containerRef = ref<HTMLDivElement | null>(null)
const imageLoaded = ref(false)
const imageError = ref(false)
const imageNaturalSize = ref({ width: 0, height: 0 })

// 缩略图滚动位置
const thumbnailScrollRef = ref<HTMLDivElement | null>(null)

const fitLabel = computed(() => {
  const m: Record<string, string> = { contain: "适应", cover: "裁剪填充", fill: "拉伸填充" }
  return m[store.fitMode] ?? "适应"
})

const zoomPercent = computed(() => Math.round(store.zoom * 100) + "%")

const canZoomIn = computed(() => store.zoom < 5)
const canZoomOut = computed(() => store.zoom > 0.1)

function onImageLoad(): void {
  imageLoaded.value = true
  imageError.value = false
  if (imageRef.value) {
    imageNaturalSize.value = {
      width: imageRef.value.naturalWidth,
      height: imageRef.value.naturalHeight,
    }
  }
}

function onImageError(): void {
  imageLoaded.value = false
  imageError.value = true
}

function onZoomWheel(e: WheelEvent): void {
  if (e.ctrlKey || e.metaKey) {
    e.preventDefault()
    if (e.deltaY < 0) store.zoomIn()
    else store.zoomOut()
  }
}

// 键盘控制
function onKeydown(e: KeyboardEvent): void {
  if (!store.visible) return

  switch (e.key) {
    case "Escape":
      store.close()
      break
    case "ArrowLeft":
      if (store.hasPrev) store.prev()
      break
    case "ArrowRight":
      if (store.hasNext) store.next()
      break
    case "+":
    case "=":
      store.zoomIn()
      break
    case "-":
      store.zoomOut()
      break
    case "0":
      store.resetZoom()
      break
    case "f":
    case "F":
      if (!e.ctrlKey && !e.metaKey) store.toggleFitMode()
      break
  }
}

let overlayTimer: ReturnType<typeof setTimeout> | null = null
function onMouseMove(): void {
  // 鼠标移动时显示工具栏（由 CSS :hover 处理，此处保留扩展点）
}

// 缩略图自动滚动到当前项
watch(() => store.currentIndex, () => {
  if (thumbnailScrollRef.value) {
    const thumb = thumbnailScrollRef.value.children[store.currentIndex] as HTMLElement | undefined
    if (thumb) {
      thumb.scrollIntoView({ behavior: "smooth", inline: "center", block: "nearest" })
    }
  }
})

// 全局键盘监听
watch(() => store.visible, (v) => {
  if (v) {
    window.addEventListener("keydown", onKeydown)
    document.body.style.overflow = "hidden"
  } else {
    window.removeEventListener("keydown", onKeydown)
    document.body.style.overflow = ""
  }
})

onUnmounted(() => {
  window.removeEventListener("keydown", onKeydown)
  document.body.style.overflow = ""
})
</script>

<template>
  <Teleport to="body">
    <div
      v-if="store.visible"
      ref="containerRef"
      class="fixed inset-0 z-[9999] flex flex-col select-none"
      style="background: rgba(0, 0, 0, 0.92); backdrop-filter: blur(8px);"
      @click.self="store.close()"
      @wheel.prevent="onZoomWheel"
    >
      <!-- ═══ Top Toolbar ═══ -->
      <div
        class="flex items-center justify-between px-4 py-2 shrink-0 z-10"
        style="
          background: linear-gradient(to bottom, rgba(0,0,0,0.7), transparent);
          color: #CCCCCC; font-size: 13px;
        "
      >
        <!-- Left: file info -->
        <div class="flex items-center gap-3">
          <span class="text-white/90 font-medium truncate max-w-[400px]">
            {{ store.currentItem?.name ?? "" }}
          </span>
          <span class="text-white/50 text-[12px]">
            {{ store.currentIndex + 1 }} / {{ store.totalCount }}
          </span>
          <span
            v-if="imageNaturalSize.width > 0 && store.currentItem?.type === 'image'"
            class="text-white/40 text-[12px]"
          >
            {{ imageNaturalSize.width }} × {{ imageNaturalSize.height }}
          </span>
        </div>

        <!-- Right: zoom controls + close -->
        <div class="flex items-center gap-1">
          <!-- Zoom controls -->
          <button
            class="carousel-btn" title="缩小 (-)" :disabled="!canZoomOut"
            @click="store.zoomOut()"
          ><ZoomOut :size="16" /></button>
          <span
            class="text-white/70 text-[12px] px-1 min-w-[42px] text-center"
          >{{ zoomPercent }}</span>
          <button
            class="carousel-btn" title="放大 (+)" :disabled="!canZoomIn"
            @click="store.zoomIn()"
          ><ZoomIn :size="16" /></button>

          <!-- Fit mode -->
          <button
            class="carousel-btn" :title="'填充模式: ' + fitLabel"
            @click="store.toggleFitMode()"
          >
            <Maximize2 v-if="store.fitMode === 'contain'" :size="16" />
            <Minimize2 v-else :size="16" />
            <span class="text-[10px] ml-1 hidden sm:inline">{{ fitLabel }}</span>
          </button>

          <!-- Reset zoom -->
          <button
            class="carousel-btn" title="重置缩放 (0)"
            @click="store.resetZoom()"
          ><RotateCw :size="16" /></button>

          <!-- Close -->
          <button
            class="carousel-btn ml-2" title="关闭 (Esc)"
            @click="store.close()"
          ><X :size="18" /></button>
        </div>
      </div>

      <!-- ═══ Main Content ═══ -->
      <div class="flex-1 flex items-center justify-center min-h-0 relative overflow-hidden px-16">

        <!-- Left arrow -->
        <button
          v-if="store.hasPrev"
          class="carousel-nav-btn absolute left-4 top-1/2 -translate-y-1/2 z-10"
          @click.stop="store.prev()"
          title="上一张 (←)"
        >
          <ChevronLeft :size="36" />
        </button>

        <!-- Image -->
        <img
          v-if="store.currentItem?.type === 'image'"
          ref="imageRef"
          :src="store.getMediaUrl()"
          :class="[
            'max-w-full max-h-full transition-transform duration-150',
            imageLoaded ? 'opacity-100' : 'opacity-0',
          ]"
          :style="{
            objectFit: store.fitMode as any,
            transform: `scale(${store.zoom})`,
          }"
          draggable="false"
          @load="onImageLoad()"
          @error="onImageError()"
          @dblclick="store.resetZoom()"
        />

        <!-- Video -->
        <video
          v-if="store.currentItem?.type === 'video'"
          ref="videoRef"
          :src="store.getMediaUrl()"
          class="max-w-full max-h-full rounded"
          controls
          autoplay
          loop
          :style="{ transform: `scale(${store.zoom})` }"
        />

        <!-- Error state -->
        <div
          v-if="imageError && store.currentItem?.type === 'image'"
          class="flex flex-col items-center gap-2 text-white/50"
        >
          <Play :size="48" class="opacity-40" />
          <span class="text-[14px]">无法加载图片</span>
          <span class="text-[12px] opacity-60">{{ store.currentItem?.path }}</span>
        </div>

        <!-- Right arrow -->
        <button
          v-if="store.hasNext"
          class="carousel-nav-btn absolute right-4 top-1/2 -translate-y-1/2 z-10"
          @click.stop="store.next()"
          title="下一张 (→)"
        >
          <ChevronRight :size="36" />
        </button>
      </div>

      <!-- ═══ Bottom Thumbnail Strip ═══ -->
      <div
        v-if="store.totalCount > 1"
        ref="thumbnailScrollRef"
        class="flex items-center gap-1.5 px-4 py-2.5 overflow-x-auto shrink-0 justify-center z-10"
        style="
          background: linear-gradient(to top, rgba(0,0,0,0.6), transparent);
          scrollbar-width: thin;
          scrollbar-color: rgba(255,255,255,0.15) transparent;
        "
      >
        <div
          v-for="(item, idx) in store.items"
          :key="item.path"
          :class="[
            'shrink-0 w-12 h-9 rounded overflow-hidden cursor-pointer border-2 transition-all duration-150',
            idx === store.currentIndex
              ? 'border-[var(--color-ide-accent)] opacity-100 scale-110'
              : 'border-transparent opacity-50 hover:opacity-80',
          ]"
          @click="store.currentIndex = idx"
        >
          <img
            v-if="item.type === 'image'"
            :src="item.path"
            class="w-full h-full object-cover"
            loading="lazy"
          />
          <div
            v-else
            class="w-full h-full flex items-center justify-center bg-white/10"
          >
            <Play :size="12" class="text-white/70" />
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.carousel-btn {
  display: flex;
  align-items: center;
  padding: 4px 6px;
  border-radius: 4px;
  color: rgba(255, 255, 255, 0.7);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: all 0.15s;
}
.carousel-btn:hover {
  color: white;
  background: rgba(255, 255, 255, 0.1);
}
.carousel-btn:disabled {
  opacity: 0.3;
  cursor: default;
}

.carousel-nav-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  color: rgba(255, 255, 255, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.05);
  cursor: pointer;
  transition: all 0.2s;
  backdrop-filter: blur(8px);
}
.carousel-nav-btn:hover {
  background: rgba(255, 255, 255, 0.16);
  color: white;
  transform: translateY(-50%) scale(1.1);
}
</style>
