<script setup lang="ts">
import { onMounted, ref } from "vue"
import {
  type STTResult,
  type TTSResult,
  type VoiceInfo,
  voiceApi,
} from "@/api/model-features"
import { Mic, Upload, Volume2 } from "lucide-vue-next"

const ttsText = ref("")
const ttsVoice = ref("nova")
const ttsSpeed = ref(1.0)
const ttsResult = ref<TTSResult | null>(null)
const ttsLoading = ref(false)

const sttFile = ref<File | null>(null)
const sttUrl = ref("")
const sttResult = ref<STTResult | null>(null)
const sttLoading = ref(false)

const openaiVoices = ref<VoiceInfo[]>([])
const edgeVoices = ref<VoiceInfo[]>([])
const status = ref({ tts_available: false, stt_available: false })
const error = ref("")

onMounted(async () => {
  try {
    const [v, s] = await Promise.all([voiceApi.voices(), voiceApi.status()])
    openaiVoices.value = v.data.openai_tts || []
    edgeVoices.value = v.data.edge_tts || []
    status.value = s.data
  } catch {}
})

const allVoices = [
  ...openaiVoices.value.map((v) => ({ ...v, provider: "OpenAI" })),
  ...edgeVoices.value.map((v) => ({ ...v, provider: "Edge TTS" })),
]

async function doTTS() {
  if (!ttsText.value.trim()) return
  ttsLoading.value = true
  error.value = ""
  try {
    ttsResult.value = (
      await voiceApi.tts({
        text: ttsText.value,
        voice: ttsVoice.value,
        speed: ttsSpeed.value,
      })
    ).data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "合成失败"
  } finally {
    ttsLoading.value = false
  }
}

function playAudio(b64: string) {
  const audio = new Audio(`data:audio/mpeg;base64,${b64}`)
  audio.play()
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.[0]) sttFile.value = input.files[0]
}

async function doSTT() {
  if (!sttFile.value) return
  sttLoading.value = true
  error.value = ""
  try {
    sttResult.value = (await voiceApi.stt(sttFile.value)).data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "转录失败"
  } finally {
    sttLoading.value = false
  }
}

async function doSTTUrl() {
  if (!sttUrl.value.trim()) return
  sttLoading.value = true
  error.value = ""
  try {
    sttResult.value = (await voiceApi.sttByUrl(sttUrl.value)).data
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "转录失败"
  } finally {
    sttLoading.value = false
  }
}
</script>

<template>
  <div class="p-6 max-w-5xl mx-auto space-y-6">
    <header>
      <h1 class="text-3xl font-bold text-white">语音服务</h1>
      <p class="text-gray-400 mt-2">文字转语音 (TTS) · 语音转文字 (STT)</p>
    </header>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- TTS -->
      <div class="bg-gray-900/50 rounded-2xl p-6 border border-gray-800/50 space-y-4">
        <h2 class="font-semibold text-white flex items-center gap-2">
          <Volume2 class="w-5 h-5 text-brand-400" /> 文字转语音
          <span :class="['ml-auto px-2 py-0.5 rounded text-xs', status.tts_available ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400']">{{ status.tts_available ? '可用' : '不可用' }}</span>
        </h2>
        <textarea v-model="ttsText" rows="4" class="w-full bg-gray-800 border border-gray-700/50 rounded-xl p-3 text-sm text-gray-200 outline-none focus:border-brand-500/50 resize-none" placeholder="输入要合成的文字..."></textarea>
        <div class="grid grid-cols-2 gap-3">
          <label class="space-y-1">
            <span class="text-xs text-gray-400">语音</span>
            <select v-model="ttsVoice" class="w-full bg-gray-800 border border-gray-700/50 rounded-xl px-3 py-2 text-sm text-gray-200 outline-none">
              <option v-for="v in allVoices" :key="v.id" :value="v.id">{{ v.name }} ({{ v.provider }})</option>
            </select>
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-400">语速: {{ ttsSpeed }}x</span>
            <input v-model.number="ttsSpeed" type="range" min="0.25" max="4.0" step="0.25" class="w-full accent-brand-500" />
          </label>
        </div>
        <button @click="doTTS" :disabled="ttsLoading || !ttsText.trim()" class="w-full py-3 rounded-xl bg-gradient-to-r from-brand-500 to-purple-500 text-white font-medium disabled:opacity-50">{{ ttsLoading ? '合成中...' : '合成语音' }}</button>
        <p v-if="error" class="text-red-400 text-sm">{{ error }}</p>
        <div v-if="ttsResult" class="bg-gray-800/50 rounded-xl p-4 flex items-center justify-between">
          <span class="text-xs text-gray-400">时长 {{ ttsResult.duration_seconds.toFixed(1) }}s</span>
          <button @click="playAudio(ttsResult.audio_base64)" class="px-4 py-2 rounded-xl bg-brand-500/20 text-brand-400 text-sm hover:bg-brand-500/30 transition">播放</button>
        </div>
      </div>

      <!-- STT -->
      <div class="bg-gray-900/50 rounded-2xl p-6 border border-gray-800/50 space-y-4">
        <h2 class="font-semibold text-white flex items-center gap-2">
          <Mic class="w-5 h-5 text-purple-400" /> 语音转文字
          <span :class="['ml-auto px-2 py-0.5 rounded text-xs', status.stt_available ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400']">{{ status.stt_available ? '可用' : '不可用' }}</span>
        </h2>
        <label class="block">
          <span class="text-xs text-gray-400 mb-2 block">上传音频文件</span>
          <div class="flex items-center gap-3 border-2 border-dashed border-gray-700/50 rounded-xl p-6 text-center hover:border-purple-500/30 transition cursor-pointer">
            <Upload class="w-5 h-5 text-gray-500" />
            <span class="text-sm text-gray-500">{{ sttFile ? sttFile.name : '点击选择 mp3/wav/flac/ogg' }}</span>
            <input type="file" accept="audio/*" @change="onFileChange" class="hidden" />
          </div>
        </label>
        <button @click="doSTT" :disabled="sttLoading || !sttFile" class="w-full py-3 rounded-xl bg-purple-500 hover:bg-purple-600 text-white font-medium disabled:opacity-50">{{ sttLoading ? '转录中...' : '上传并转录' }}</button>

        <div class="flex items-center gap-3">
          <div class="flex-1 h-px bg-gray-700/50" />
          <span class="text-xs text-gray-500">或通过 URL</span>
          <div class="flex-1 h-px bg-gray-700/50" />
        </div>

        <div class="flex gap-2">
          <input v-model="sttUrl" class="flex-1 bg-gray-800 border border-gray-700/50 rounded-xl px-3 py-2 text-sm text-gray-200 outline-none" placeholder="https://..." />
          <button @click="doSTTUrl" :disabled="sttLoading || !sttUrl.trim()" class="px-4 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-sm text-gray-300 transition">转录</button>
        </div>

        <div v-if="sttResult" class="bg-gray-800/50 rounded-xl p-4 space-y-2">
          <p class="text-sm text-gray-200 leading-relaxed">{{ sttResult.text }}</p>
          <div v-if="sttResult.segments?.length" class="text-xs text-gray-500">
            片段: {{ sttResult.segments.length }} · 语言: {{ sttResult.language || '自动' }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
