<script setup lang="ts">
import { onMounted, ref } from "vue"
import { type ImageGenResult, imageGenApi } from "@/api/image-gen"

const prompt = ref("")
const negativePrompt = ref("")
const size = ref("1024x1024")
const style = ref("natural")
const n = ref(1)
const engine = ref("")
const generating = ref(false)
const result = ref<ImageGenResult | null>(null)
const error = ref("")
const providers = ref<string[]>([])
const batchPrompts = ref("")
const batchResults = ref<
  {
    prompt: string
    success: boolean
    image?: { url: string; b64_json: string }
    error?: string
  }[]
>([])
const _showLightbox = ref<string>("")

const _sizes = [
  { value: "256x256", label: "256×256" },
  { value: "512x512", label: "512×512" },
  { value: "1024x1024", label: "1024×1024" },
  { value: "1024x1792", label: "1024×1792（竖版）" },
  { value: "1792x1024", label: "1792×1024（横版）" },
]

const _styles = [
  { value: "natural", label: "自然" },
  { value: "vivid", label: "鲜艳" },
  { value: "anime", label: "动漫" },
  { value: "photographic", label: "摄影" },
  { value: "digital-art", label: "数字艺术" },
]

onMounted(async () => {
  try {
    const { data } = await imageGenApi.providers()
    providers.value = data.providers
  } catch {
    // ignore
  }
})

async function _doGenerate() {
  if (!prompt.value.trim()) return
  generating.value = true
  error.value = ""
  result.value = null
  try {
    result.value = (
      await imageGenApi.generate({
        prompt: prompt.value,
        negative_prompt: negativePrompt.value,
        size: size.value,
        style: style.value,
        n: n.value,
        engine: engine.value,
      })
    ).data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "生成失败"
  } finally {
    generating.value = false
  }
}

async function _doBatch() {
  const prompts = batchPrompts.value.split("\n").filter((p) => p.trim())
  if (!prompts.length) return
  generating.value = true
  error.value = ""
  try {
    batchResults.value = (
      await imageGenApi.batchGenerate({
        prompts,
        size: size.value,
        engine: engine.value,
      })
    ).data.results
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "批量生成失败"
  } finally {
    generating.value = false
  }
}

function _downloadB64(b64: string, index: number) {
  const a = document.createElement("a")
  a.href = `data:image/png;base64,${b64}`
  a.download = `ai-generated-${Date.now()}-${index + 1}.png`
  a.click()
}
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto">
    <header class="mb-6">
      <h1 class="text-2xl font-bold text-white flex items-center gap-2">
        <Image class="w-6 h-6 text-brand-400" />
        图像生成
      </h1>
      <p class="text-sm text-gray-400 mt-1">
        通过 AI 生成图像 — 支持 DALL-E / Stability / ComfyUI 多引擎自动选择
      </p>
    </header>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- 左侧控制面板 -->
      <div
        class="bg-surface-800/60 rounded-xl p-5 border border-white/10 space-y-4 lg:col-span-1"
      >
        <label class="block space-y-1.5">
          <span class="text-sm text-gray-300 font-medium">描述词 (Prompt)</span>
          <textarea
            v-model="prompt"
            rows="4"
            class="w-full bg-black/30 border border-white/10 rounded-lg p-3 text-sm text-gray-200 focus:outline-none focus:border-brand-500 resize-none placeholder:text-gray-600"
            placeholder="描述你想生成的图像，如：一只赛博朋克风格的猫，霓虹灯背景..."
          />
        </label>

        <label class="block space-y-1.5">
          <span class="text-sm text-gray-300 font-medium">排除词 (Negative Prompt)</span>
          <input
            v-model="negativePrompt"
            class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-brand-500 placeholder:text-gray-600"
            placeholder="模糊, 低质量, 畸形, extra fingers"
          />
        </label>

        <div class="grid grid-cols-2 gap-3">
          <label class="space-y-1.5">
            <span class="text-xs text-gray-400">尺寸</span>
            <select
              v-model="size"
              class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none"
            >
              <option v-for="s in sizes" :key="s.value" :value="s.value">
                {{ s.label }}
              </option>
            </select>
          </label>
          <label class="space-y-1.5">
            <span class="text-xs text-gray-400">风格</span>
            <select
              v-model="style"
              class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none"
            >
              <option v-for="s in styles" :key="s.value" :value="s.value">
                {{ s.label }}
              </option>
            </select>
          </label>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <label class="space-y-1.5">
            <span class="text-xs text-gray-400">数量</span>
            <input
              v-model.number="n"
              type="number"
              min="1"
              max="4"
              class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none"
            />
          </label>
          <label class="space-y-1.5">
            <span class="text-xs text-gray-400">引擎</span>
            <select
              v-model="engine"
              class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none"
            >
              <option value="">自动选择</option>
              <option v-for="p in providers" :key="p" :value="p">
                {{ p }}
              </option>
            </select>
          </label>
        </div>

        <button
          @click="doGenerate"
          :disabled="generating || !prompt.trim()"
          class="w-full py-3 rounded-lg bg-brand-500 hover:bg-brand-600 text-white font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          <RefreshCw v-if="generating" class="w-4 h-4 animate-spin" />
          {{ generating ? '生成中...' : '生成图像' }}
        </button>

        <p v-if="error" class="text-red-400 text-sm px-2">{{ error }}</p>
      </div>

      <!-- 右侧结果区域 -->
      <div class="lg:col-span-2 space-y-4">
        <!-- 单张结果 -->
        <template v-if="result">
          <div
            class="flex items-center justify-between px-1"
          >
            <span class="text-xs text-gray-500">
              引擎: {{ result.provider_used }} · 耗时: {{ result.latency_ms.toFixed(0) }}ms
            </span>
          </div>
          <div
            class="grid gap-4"
            :class="result.images.length > 1 ? 'grid-cols-2' : 'grid-cols-1'"
          >
            <div
              v-for="(img, i) in result.images"
              :key="i"
              class="bg-surface-800/60 rounded-xl border border-white/10 overflow-hidden group cursor-pointer hover:border-brand-500/30 transition"
              @click="showLightbox = img.b64_json || img.url"
            >
              <img
                v-if="img.b64_json"
                :src="'data:image/png;base64,' + img.b64_json"
                class="w-full object-cover aspect-square"
              />
              <img
                v-else-if="img.url"
                :src="img.url"
                class="w-full object-cover aspect-square"
              />
              <div class="p-3 flex items-center justify-between">
                <span
                  v-if="img.revised_prompt"
                  class="text-xs text-gray-500 truncate max-w-[80%]"
                >
                  改写: {{ img.revised_prompt.slice(0, 50) }}...
                </span>
                <span v-else class="text-xs text-gray-600">{{ img.width }}×{{ img.height }}</span>
                <button
                  v-if="img.b64_json"
                  @click.stop="downloadB64(img.b64_json, i)"
                  class="p-1.5 rounded-lg hover:bg-white/10 transition"
                  title="下载"
                >
                  <Download class="w-3.5 h-3.5 text-gray-400" />
                </button>
              </div>
            </div>
          </div>
        </template>

        <!-- 空状态提示 -->
        <div
          v-if="!result && !generating"
          class="flex flex-col items-center justify-center py-16 text-gray-500"
        >
          <div
            class="w-20 h-20 rounded-2xl bg-surface-800 flex items-center justify-center mb-4"
          >
            <Image class="w-10 h-10 text-gray-600" />
          </div>
          <p class="mb-1">输入描述词后点击「生成图像」</p>
          <p class="text-sm text-gray-600">
            支持 DALL-E · Stable Diffusion · ComfyUI
          </p>
        </div>

        <!-- 批量生成折叠区 -->
        <details
          class="bg-surface-800/60 rounded-xl border border-white/10 mt-4"
        >
          <summary class="p-4 cursor-pointer text-sm font-medium text-gray-300 select-none hover:text-white transition">
            批量生成
          </summary>
          <div class="px-4 pb-4 space-y-3">
            <textarea
              v-model="batchPrompts"
              rows="4"
              class="w-full bg-black/30 border border-white/10 rounded-lg p-3 text-sm text-gray-200 focus:outline-none focus:border-brand-500 resize-none placeholder:text-gray-600"
              placeholder="每行一个 Prompt..."
            />
            <button
              @click="doBatch"
              :disabled="generating"
              class="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-sm text-gray-300 transition-colors disabled:opacity-50"
            >
              提交批量
            </button>
            <div
              v-if="batchResults.length"
              class="grid grid-cols-2 sm:grid-cols-3 gap-3"
            >
              <div
                v-for="(r, i) in batchResults"
                :key="i"
                class="bg-black/30 rounded-lg p-3"
              >
                <p class="text-xs text-gray-300 mb-2 truncate">
                  {{ r.prompt.slice(0, 50) }}
                </p>
                <img
                  v-if="r.success && r.image?.b64_json"
                  :src="'data:image/png;base64,' + r.image.b64_json"
                  class="w-full aspect-square object-cover rounded"
                />
                <p
                  v-else-if="r.success && r.image?.url"
                  class="text-xs text-green-400"
                >
                  已生成
                </p>
                <p v-else class="text-xs text-red-400">{{ r.error }}</p>
              </div>
            </div>
          </div>
        </details>
      </div>
    </div>

    <!-- 图片灯箱 -->
    <Teleport to="body">
      <div
        v-if="showLightbox"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 cursor-pointer"
        @click="showLightbox = ''"
      >
        <button
          class="absolute top-4 right-4 p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white transition"
          @click="showLightbox = ''"
        >
          <X class="w-5 h-5" />
        </button>
        <img
          :src="showLightbox.startsWith('data:') ? showLightbox : 'data:image/png;base64,' + showLightbox"
          class="max-w-[90vw] max-h-[90vh] rounded-xl shadow-2xl"
        />
      </div>
    </Teleport>
  </div>
</template>
