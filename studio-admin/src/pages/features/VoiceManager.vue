<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { voiceApi, type VoiceInfo, type TTSResult, type STTResult } from '@/api/model-features'

// TTS
const ttsText = ref('')
const ttsVoice = ref('nova')
const ttsSpeed = ref(1.0)
const ttsResult = ref<TTSResult | null>(null)
const ttsLoading = ref(false)
const ttsError = ref('')
const audioPlayer = ref<HTMLAudioElement | null>(null)

// STT
const sttFile = ref<File | null>(null)
const sttUrl = ref('')
const sttResult = ref<STTResult | null>(null)
const sttLoading = ref(false)
const sttError = ref('')

// Voices
const openaiVoices = ref<VoiceInfo[]>([])
const edgeVoices = ref<VoiceInfo[]>([])
const status = ref<{ tts_available: boolean; stt_available: boolean }>({ tts_available: false, stt_available: false })

onMounted(async () => {
  try {
    const [v, s] = await Promise.all([voiceApi.voices(), voiceApi.status()])
    openaiVoices.value = v.data.openai_tts || []
    edgeVoices.value = v.data.edge_tts || []
    status.value = s.data
  } catch {}
})

async function doTTS() {
  if (!ttsText.value.trim()) return
  ttsLoading.value = true
  ttsError.value = ''
  ttsResult.value = null
  try {
    ttsResult.value = (await voiceApi.tts({
      text: ttsText.value,
      voice: ttsVoice.value,
      speed: ttsSpeed.value,
    })).data
  } catch (e: any) {
    ttsError.value = e?.response?.data?.detail || '合成失败'
  } finally {
    ttsLoading.value = false
  }
}

function playAudio(b64: string) {
  if (audioPlayer.value) audioPlayer.value.pause()
  const audio = new Audio(`data:audio/mpeg;base64,${b64}`)
  audio.play()
  audioPlayer.value = audio
}

function onFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files?.[0]) sttFile.value = input.files[0]
}

async function doSTT() {
  if (!sttFile.value) return
  sttLoading.value = true
  sttError.value = ''
  sttResult.value = null
  try {
    sttResult.value = (await voiceApi.stt(sttFile.value)).data
  } catch (e: any) {
    sttError.value = e?.response?.data?.detail || '转录失败'
  } finally {
    sttLoading.value = false
  }
}

async function doSTTUrl() {
  if (!sttUrl.value.trim()) return
  sttLoading.value = true
  sttError.value = ''
  sttResult.value = null
  try {
    sttResult.value = (await voiceApi.sttByUrl(sttUrl.value)).data
  } catch (e: any) {
    sttError.value = e?.response?.data?.detail || '转录失败'
  } finally {
    sttLoading.value = false
  }
}

const allVoices = [
  ...openaiVoices.value.map(v => ({ ...v, provider: 'OpenAI' })),
  ...edgeVoices.value.map(v => ({ ...v, provider: 'Edge TTS' })),
]
</script>

<template>
  <div class="p-6 max-w-6xl mx-auto space-y-6">
    <div>
      <h1 class="text-2xl font-bold text-white">语音服务</h1>
      <p class="text-sm text-gray-400 mt-1">TTS 文字转语音 | STT 语音转文字</p>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <!-- TTS -->
      <div class="bg-white/5 rounded-xl p-5 border border-white/10 space-y-4">
        <h2 class="text-base font-semibold text-white flex items-center gap-2">
          🔊 文字转语音
          <span :class="['px-2 py-0.5 rounded text-xs', status.tts_available ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400']">
            {{ status.tts_available ? '可用' : '不可用' }}
          </span>
        </h2>

        <label class="block space-y-1">
          <span class="text-xs text-gray-400">输入文本</span>
          <textarea v-model="ttsText" rows="4"
            class="w-full bg-black/30 border border-white/10 rounded-lg p-3 text-sm text-gray-200 focus:outline-none focus:border-brand-500 resize-none"
            placeholder="你好，这是语音合成测试..."></textarea>
        </label>

        <div class="grid grid-cols-2 gap-3">
          <label class="space-y-1">
            <span class="text-xs text-gray-400">语音</span>
            <select v-model="ttsVoice"
              class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none">
              <option v-for="v in allVoices" :key="v.id" :value="v.id">{{ v.name }} ({{ v.provider }})</option>
            </select>
          </label>
          <label class="space-y-1">
            <span class="text-xs text-gray-400">语速: {{ ttsSpeed }}x</span>
            <input v-model.number="ttsSpeed" type="range" min="0.25" max="4.0" step="0.25"
              class="w-full accent-brand-500" />
          </label>
        </div>

        <button @click="doTTS" :disabled="ttsLoading || !ttsText.trim()"
          class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-sm transition-colors disabled:opacity-50">
          {{ ttsLoading ? '合成中...' : '合成语音' }}
        </button>
        <p v-if="ttsError" class="text-red-400 text-sm">{{ ttsError }}</p>

        <div v-if="ttsResult" class="bg-black/30 rounded-lg p-4 space-y-2">
          <div class="flex items-center justify-between text-xs text-gray-400">
            <span>延迟: {{ ttsResult.latency_ms.toFixed(0) }}ms | 时长: {{ ttsResult.duration_seconds.toFixed(1) }}s</span>
            <button @click="playAudio(ttsResult.audio_base64)"
              class="px-3 py-1.5 rounded bg-brand-600 hover:bg-brand-700 text-white text-xs transition-colors">播放</button>
          </div>
        </div>
      </div>

      <!-- STT -->
      <div class="bg-white/5 rounded-xl p-5 border border-white/10 space-y-4">
        <h2 class="text-base font-semibold text-white flex items-center gap-2">
          🎙 语音转文字
          <span :class="['px-2 py-0.5 rounded text-xs', status.stt_available ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400']">
            {{ status.stt_available ? '可用' : '不可用' }}
          </span>
        </h2>

        <label class="block space-y-1">
          <span class="text-xs text-gray-400">上传音频文件 (mp3/wav/flac/ogg/m4a/webm)</span>
          <input type="file" accept="audio/*" @change="onFileChange"
            class="w-full text-sm text-gray-300 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-brand-600 file:text-white file:text-sm file:font-medium hover:file:bg-brand-700 file:cursor-pointer" />
        </label>

        <button @click="doSTT" :disabled="sttLoading || !sttFile"
          class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-sm transition-colors disabled:opacity-50">
          {{ sttLoading ? '转录中...' : '上传并转录' }}
        </button>

        <div class="flex items-center gap-2">
          <div class="flex-1 h-px bg-white/10"></div>
          <span class="text-xs text-gray-500">或通过 URL</span>
          <div class="flex-1 h-px bg-white/10"></div>
        </div>

        <div class="flex gap-2">
          <input v-model="sttUrl"
            class="flex-1 bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-brand-500"
            placeholder="https://example.com/audio.mp3" />
          <button @click="doSTTUrl" :disabled="sttLoading || !sttUrl.trim()"
            class="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-sm text-gray-200 transition-colors disabled:opacity-50">转录</button>
        </div>
        <p v-if="sttError" class="text-red-400 text-sm">{{ sttError }}</p>

        <div v-if="sttResult" class="bg-black/30 rounded-lg p-4 space-y-2">
          <div class="flex items-center justify-between text-xs text-gray-400">
            <span>语言: {{ sttResult.language || '自动' }} | 延迟: {{ sttResult.latency_ms.toFixed(0) }}ms</span>
          </div>
          <p class="text-sm text-gray-200 leading-relaxed">{{ sttResult.text }}</p>
          <div v-if="sttResult.segments?.length" class="space-y-1">
            <p class="text-xs text-gray-500">片段:</p>
            <p v-for="(seg, i) in sttResult.segments" :key="i" class="text-xs text-gray-400">
              [{{ seg.start?.toFixed(1) }}s-{{ seg.end?.toFixed(1) }}s] {{ seg.text }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
