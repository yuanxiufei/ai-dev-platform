<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { imageGenApi, type ImageGenResult } from '@/api/model-features'

const prompt = ref('')
const negativePrompt = ref('')
const size = ref('1024x1024')
const engine = ref('')
const style = ref('natural')
const n = ref(1)
const generating = ref(false)
const result = ref<ImageGenResult | null>(null)
const error = ref('')
const providers = ref<string[]>([])
const batchPrompts = ref('')
const batchResults = ref<any[]>([])

const sizes = [
  { value: '256x256', label: '256×256' },
  { value: '512x512', label: '512×512' },
  { value: '1024x1024', label: '1024×1024' },
  { value: '1024x1792', label: '1024×1792' },
  { value: '1792x1024', label: '1792×1024' },
]

const styles = [
  { value: 'natural', label: '自然' },
  { value: 'vivid', label: '鲜艳' },
  { value: 'anime', label: '动漫' },
  { value: 'photographic', label: '摄影' },
  { value: 'digital-art', label: '数字艺术' },
]

onMounted(async () => {
  try {
    const { data } = await imageGenApi.providers()
    providers.value = data.providers
  } catch {}
})

async function doGenerate() {
  if (!prompt.value.trim()) return
  generating.value = true
  error.value = ''
  result.value = null
  try {
    result.value = (await imageGenApi.generate({
      prompt: prompt.value,
      negative_prompt: negativePrompt.value,
      size: size.value,
      style: style.value,
      n: n.value,
      engine: engine.value,
    })).data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '生成失败'
  } finally {
    generating.value = false
  }
}

async function doBatch() {
  const prompts = batchPrompts.value.split('\n').filter(p => p.trim())
  if (!prompts.length) return
  generating.value = true
  try {
    batchResults.value = (await imageGenApi.batchGenerate({
      prompts,
      size: size.value,
      engine: engine.value,
    })).data.results
  } catch (e: any) {
    error.value = e?.response?.data?.detail || '批量生成失败'
  } finally {
    generating.value = false
  }
}

function downloadB64(b64: string, index: number) {
  const a = document.createElement('a')
  a.href = `data:image/png;base64,${b64}`
  a.download = `generated-${index + 1}.png`
  a.click()
}
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto space-y-6">
    <div>
      <h1 class="text-2xl font-bold text-white">图像生成</h1>
      <p class="text-sm text-gray-400 mt-1">DALL-E / Stability / ComfyUI 三引擎 — 自动选择或指定</p>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Controls -->
      <div class="bg-white/5 rounded-xl p-5 border border-white/10 space-y-4 lg:col-span-1">
        <label class="block space-y-1">
          <span class="text-sm text-gray-300">Prompt</span>
          <textarea v-model="prompt" rows="3"
            class="w-full bg-black/30 border border-white/10 rounded-lg p-3 text-sm text-gray-200 focus:outline-none focus:border-brand-500 resize-none"
            placeholder="一只赛博朋克风格的猫，霓虹灯背景..."></textarea>
        </label>

        <label class="block space-y-1">
          <span class="text-sm text-gray-300">Negative Prompt</span>
          <input v-model="negativePrompt"
            class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-brand-500"
            placeholder="模糊, 低质量, 畸形" />
        </label>

        <div class="grid grid-cols-2 gap-3">
          <label class="space-y-1">
            <span class="text-xs text-gray-400">尺寸</span>
            <select v-model="size"
              class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none">
              <option v-for="s in sizes" :key="s.value" :value="s.value">{{ s.label }}</option>
            </select>
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-400">风格</span>
            <select v-model="style"
              class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none">
              <option v-for="s in styles" :key="s.value" :value="s.value">{{ s.label }}</option>
            </select>
          </label>
        </div>

        <div class="grid grid-cols-2 gap-3">
          <label class="space-y-1">
            <span class="text-xs text-gray-400">数量</span>
            <input v-model.number="n" type="number" min="1" max="4"
              class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none" />
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-400">引擎</span>
            <select v-model="engine"
              class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none">
              <option value="">自动</option>
              <option v-for="p in providers" :key="p" :value="p">{{ p }}</option>
            </select>
          </label>
        </div>

        <button @click="doGenerate" :disabled="generating || !prompt.trim()"
          class="w-full py-3 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
          {{ generating ? '生成中...' : '生成图像' }}
        </button>
        <p v-if="error" class="text-red-400 text-sm">{{ error }}</p>
      </div>

      <!-- Results -->
      <div class="lg:col-span-2 space-y-4">
        <div v-if="result" class="space-y-4">
          <div class="flex items-center justify-between">
            <span class="text-sm text-gray-400">引擎: {{ result.provider_used }} | 延迟: {{ result.latency_ms.toFixed(0) }}ms</span>
          </div>
          <div class="grid gap-4" :class="result.images.length > 1 ? 'grid-cols-2' : 'grid-cols-1'">
            <div v-for="(img, i) in result.images" :key="i"
              class="bg-white/5 rounded-xl border border-white/10 overflow-hidden group">
              <img v-if="img.b64_json" :src="'data:image/png;base64,' + img.b64_json"
                class="w-full object-cover aspect-square" />
              <img v-else-if="img.url" :src="img.url" class="w-full object-cover aspect-square" />
              <div class="p-3 flex items-center justify-between">
                <span class="text-xs text-gray-400" v-if="img.revised_prompt">改写: {{ img.revised_prompt.slice(0, 40) }}...</span>
                <button v-if="img.b64_json" @click="downloadB64(img.b64_json, i)"
                  class="px-3 py-1.5 rounded bg-white/10 hover:bg-white/20 text-xs text-gray-300 transition-colors">下载</button>
              </div>
            </div>
          </div>
        </div>

        <!-- Batch -->
        <details class="bg-white/5 rounded-xl border border-white/10">
          <summary class="p-4 cursor-pointer text-sm font-semibold text-white select-none">批量生成</summary>
          <div class="px-4 pb-4 space-y-3">
            <textarea v-model="batchPrompts" rows="4"
              class="w-full bg-black/30 border border-white/10 rounded-lg p-3 text-sm text-gray-200 focus:outline-none focus:border-brand-500 resize-none"
              placeholder="每行一个 Prompt..."></textarea>
            <button @click="doBatch" :disabled="generating"
              class="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-sm text-gray-200 transition-colors">提交批量</button>
            <div v-if="batchResults.length" class="grid grid-cols-2 gap-3">
              <div v-for="(r, i) in batchResults" :key="i" class="bg-black/30 rounded-lg p-3">
                <p class="text-xs text-gray-300 mb-2 truncate">{{ r.prompt.slice(0, 50) }}</p>
                <img v-if="r.success && r.image?.b64_json" :src="'data:image/png;base64,' + r.image.b64_json"
                  class="w-full aspect-square object-cover rounded" />
                <p v-else-if="r.success && r.image?.url" class="text-xs text-green-400">生成成功</p>
                <p v-else class="text-xs text-red-400">{{ r.error }}</p>
              </div>
            </div>
          </div>
        </details>
      </div>
    </div>
  </div>
</template>
