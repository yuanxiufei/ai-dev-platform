<script setup lang="ts">
/**
 * BrowserPreview — VSCode Simple Browser 对标
 * Session 42: 内置 webview 浏览器，HTML 实时预览
 */
import { ref, computed } from "vue"
import { Globe, RefreshCw, ArrowLeft, ArrowRight, X, Star, Monitor, Smartphone, Tablet, ExternalLink } from "lucide-vue-next"

const props = defineProps<{ visible: boolean; filePath?: string }>()
const emit = defineEmits<{ (e: "close"): void }>()

const url = ref("http://localhost:3000")
const urlInput = ref("")
const isLoading = ref(false)
const canGoBack = ref(false)
const canGoForward = ref(false)
const history = ref<string[]>([])
const historyIdx = ref(-1)
const deviceMode = ref<"desktop" | "tablet" | "mobile">("desktop")
const bookmarks = ref([{ url: "http://localhost:3000", title: "本地开发" }, { url: "http://localhost:5173", title: "Vite Dev" }])

const iframeWidth = computed(() => ({ desktop: "100%", tablet: "768px", mobile: "375px" }[deviceMode.value]))

function navigate(): void {
  let t = urlInput.value || url.value
  if (!t.startsWith("http")) t = "https://" + t
  url.value = t; urlInput.value = t; isLoading.value = true
  history.value = [...history.value.slice(0, historyIdx.value + 1), t]
  historyIdx.value = history.value.length - 1
  canGoBack.value = historyIdx.value > 0; canGoForward.value = false
}
function goBack() { if (historyIdx.value > 0) { historyIdx.value--; url.value = history.value[historyIdx.value]; urlInput.value = url.value; canGoBack.value = historyIdx.value > 0; canGoForward.value = true; isLoading.value = true } }
function goForward() { if (historyIdx.value < history.value.length - 1) { historyIdx.value++; url.value = history.value[historyIdx.value]; urlInput.value = url.value; canGoForward.value = historyIdx.value < history.value.length - 1; canGoBack.value = true; isLoading.value = true } }
function refresh() { isLoading.value = true; if (iframeRef.value) iframeRef.value.src = url.value }
function addBookmark() { if (!bookmarks.value.find(b => b.url === url.value)) bookmarks.value.push({ url: url.value, title: new URL(url.value).hostname }) }
const iframeRef = ref<HTMLIFrameElement | null>(null)
</script>

<template>
  <div v-if="visible" class="flex flex-col h-full" style="background: var(--color-ide-bg);">
    <div class="flex items-center gap-1 px-2 py-1 border-b" style="border-color: var(--color-ide-border); background: var(--color-ide-bg-tertiary);">
      <button @click="goBack" :disabled="!canGoBack" :style="{ opacity: canGoBack ? 1 : 0.3 }" class="p-1 rounded"><ArrowLeft :size="14" style="color: var(--color-ide-text-dim);" /></button>
      <button @click="goForward" :disabled="!canGoForward" :style="{ opacity: canGoForward ? 1 : 0.3 }" class="p-1 rounded"><ArrowRight :size="14" style="color: var(--color-ide-text-dim);" /></button>
      <button @click="refresh" class="p-1 rounded"><RefreshCw :size="14" :class="{ 'animate-spin': isLoading }" style="color: var(--color-ide-text-dim);" /></button>
      <div class="flex-1 flex items-center gap-2 px-2 py-1 mx-1 rounded" style="background: var(--color-ide-bg); border: 1px solid var(--color-ide-border);">
        <Globe :size="12" style="color: var(--color-ide-accent); opacity: 0.6;" />
        <input v-model="urlInput" class="flex-1 bg-transparent text-[12px] outline-none font-mono" style="color: var(--color-ide-text);" placeholder="输入 URL..." @keydown.enter="navigate" />
        <ExternalLink :size="12" style="color: var(--color-ide-text-dim); cursor: pointer;" @click="window.open(url, '_blank')" />
      </div>
      <div class="flex items-center gap-0.5">
        <button v-for="m in [{ id: 'desktop' as const, Icon: Monitor, t: '桌面' }, { id: 'tablet' as const, Icon: Tablet, t: '平板' }, { id: 'mobile' as const, Icon: Smartphone, t: '手机' }]" :key="m.id"
          :class="['p-1 rounded', deviceMode === m.id ? 'bg-white/10' : '']" :title="m.t" @click="deviceMode = m.id">
          <component :is="m.Icon" :size="14" :style="{ color: deviceMode === m.id ? 'var(--color-ide-accent)' : 'var(--color-ide-text-dim)' }" />
        </button>
      </div>
      <button @click="addBookmark" class="p-1 rounded" title="收藏"><Star :size="14" style="color: var(--color-ide-text-dim);" /></button>
      <button @click="emit('close')" class="p-1 rounded"><X :size="14" style="color: var(--color-ide-text-dim);" /></button>
    </div>
    <div v-if="bookmarks.length" class="flex items-center gap-1 px-2 py-0.5 border-b overflow-x-auto" style="border-color: var(--color-ide-border); background: var(--color-ide-bg-secondary);">
      <button v-for="b in bookmarks" :key="b.url" class="text-[10px] px-2 py-0.5 rounded whitespace-nowrap hover:bg-white/5 shrink-0" style="color: var(--color-ide-text-dim);" @click="url = b.url; urlInput = b.url; navigate()">{{ b.title }}</button>
    </div>
    <div class="flex-1 flex justify-center" style="background: #fff;">
      <iframe ref="iframeRef" :src="url" :style="{ width: iframeWidth, border: 'none' }" class="h-full" sandbox="allow-scripts allow-same-origin allow-forms" @load="isLoading = false" />
    </div>
  </div>
</template>
