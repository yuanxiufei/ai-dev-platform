<script setup lang="ts">
import { ref, computed } from 'vue'
import { Sparkles, Loader2, Wand2, Clock, Image, Play } from 'lucide-vue-next'
import { RouterLink, useRouter } from 'vue-router'
import { useVideoStore } from '../../stores/videoStore'

const store = useVideoStore()
const router = useRouter()

const prompt = ref('')
const selectedStyle = ref('cinematic')
const duration = ref(15)

const styles = [
  { id: 'cinematic', label: '电影质感' },
  { id: 'anime', label: '动漫风' },
  { id: 'realistic', label: '写实' },
  { id: '3d', label: '3D' },
  { id: 'vlog', label: 'Vlog' },
  { id: 'retro', label: '复古' },
]

const isSubmitting = ref(false)

async function handleGenerate() {
  if (!prompt.value.trim() || isSubmitting.value) return
  isSubmitting.value = true
  const id = Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
  store.addVideo({
    id, title: prompt.value.slice(0, 40), prompt: prompt.value,
    status: 'generating', progress: 0, duration: duration.value,
    style: selectedStyle.value, createdAt: new Date().toISOString(),
  })
  const timer = setInterval(() => {
    const v = store.videos.find(v => v.id === id)
    if (!v) { clearInterval(timer); return }
    if (v.progress >= 100) {
      clearInterval(timer)
      store.updateVideo(id, { status: 'completed', videoUrl: `https://example.com/video/${id}.mp4`, thumbnailUrl: `https://picsum.photos/seed/${id}/480/854` })
      store.setGenerating(false); isSubmitting.value = false; return
    }
    store.updateVideo(id, { progress: v.progress + Math.random() * 15 + 3 })
  }, 500)
  store.setGenerating(true)
}

const hasResult = computed(() => store.videos.filter(v => v.status === 'completed').length > 0)
</script>

<template>
  <div class="py-6 px-1">
    <!-- Hero 移动端紧凑 -->
    <section class="text-center mb-10 animate-fade-in-up">
      <div class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-300 text-xs mb-5">
        <Wand2 class="w-3.5 h-3.5" /> <span>AI 驱动 · 一句话生成短视频</span>
      </div>
      <h1 class="text-3xl font-bold leading-tight mb-3">
        <span class="bg-gradient-to-r from-violet-400 via-fuchsia-400 to-amber-400 bg-clip-text text-transparent">让创意化作影像</span>
      </h1>
      <p class="text-gray-400 text-sm px-4">输入你的想法，AI 自动生成高质感短视频</p>
    </section>

    <!-- 生成表单 移动端全宽 -->
    <section class="mb-12 animate-fade-in-up" style="animation-delay: 0.15s">
      <div class="bg-white/[0.03] backdrop-blur-xl border border-white/10 rounded-2xl p-5 space-y-5">
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-2">描述你的视频创意</label>
          <textarea v-model="prompt" rows="4" placeholder="例如：一个宇航员在火星上种花的科幻短片..." class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-violet-500/50 transition-all resize-none" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-3">视频风格</label>
          <div class="grid grid-cols-3 gap-2">
            <button v-for="s in styles" :key="s.id" @click="selectedStyle = s.id"
              class="flex items-center justify-center py-3 px-2 rounded-xl border text-sm font-medium transition-all active:scale-95"
              :class="selectedStyle === s.id ? 'bg-violet-500/15 border-violet-500/40 text-violet-300' : 'bg-white/[0.02] border-white/[0.06] text-gray-400'">
              {{ s.label }}
            </button>
          </div>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-2"><Clock class="w-4 h-4 inline mr-1" />时长：<span class="text-violet-400">{{ duration }}s</span></label>
          <input v-model.number="duration" type="range" min="5" max="60" step="5" class="w-full h-2 bg-white/10 rounded-lg accent-violet-500 cursor-pointer" />
          <div class="flex justify-between text-xs text-gray-500 mt-1"><span>5s</span><span>30s</span><span>60s</span></div>
        </div>
        <button :disabled="!prompt.trim() || isSubmitting" @click="handleGenerate"
          class="w-full py-4 rounded-xl font-semibold text-white flex items-center justify-center gap-2 transition-all active:scale-[0.97]"
          :class="!prompt.trim() || isSubmitting ? 'bg-white/5 text-gray-500 cursor-not-allowed' : 'bg-gradient-to-r from-violet-600 to-fuchsia-600 shadow-lg shadow-violet-500/25'">
          <Loader2 v-if="isSubmitting" class="w-5 h-5 animate-spin" />
          <Sparkles v-else class="w-5 h-5" />
          {{ isSubmitting ? '生成中...' : '开始生成' }}
        </button>
      </div>
    </section>

    <!-- 生成中 -->
    <section v-if="store.isGenerating" class="mb-12">
      <h2 class="text-base font-semibold text-gray-300 mb-3">当前任务</h2>
      <div v-for="v in store.videos.filter(v => v.status === 'generating')" :key="v.id" class="bg-white/[0.03] border border-white/10 rounded-2xl p-4 backdrop-blur-xl animate-fade-in-up">
        <div class="flex items-center gap-3 mb-3">
          <div class="w-10 h-10 rounded-xl bg-violet-500/15 flex items-center justify-center shrink-0"><Loader2 class="w-5 h-5 text-violet-400 animate-spin" /></div>
          <div class="flex-1 min-w-0"><p class="font-medium text-white text-sm truncate">{{ v.title }}</p><p class="text-xs text-gray-500">{{ v.style }} · {{ v.duration }}s</p></div>
          <span class="text-sm text-violet-400 font-mono">{{ Math.min(Math.floor(v.progress), 99) }}%</span>
        </div>
        <div class="w-full h-1.5 bg-white/5 rounded-full overflow-hidden"><div class="h-full bg-gradient-to-r from-violet-500 to-fuchsia-500 rounded-full transition-all duration-300" :style="{ width: v.progress + '%' }" /></div>
      </div>
    </section>

    <!-- 最近作品 2列 -->
    <section v-if="hasResult" class="mb-12">
      <h2 class="text-base font-semibold text-gray-300 mb-3">最近作品 <RouterLink to="/gallery" class="text-sm text-violet-400 ml-2 font-normal">查看全部 →</RouterLink></h2>
      <div class="grid grid-cols-2 gap-3">
        <div v-for="v in store.videos.filter(v => v.status === 'completed').slice(0, 6)" :key="v.id" @click="router.push(`/play/${v.id}`)" class="relative bg-white/[0.03] border border-white/10 rounded-xl overflow-hidden active:scale-[0.98] transition-all">
          <div class="aspect-[9/16] bg-gray-800 flex items-center justify-center relative">
            <Image v-if="!v.thumbnailUrl" class="w-10 h-10 text-gray-600" />
            <img v-else :src="v.thumbnailUrl" :alt="v.title" class="w-full h-full object-cover" loading="lazy" />
          </div>
          <div class="p-2.5"><p class="text-xs font-medium text-white truncate">{{ v.title }}</p><p class="text-[10px] text-gray-500 mt-0.5">{{ v.duration }}s · {{ v.style }}</p></div>
        </div>
      </div>
    </section>
  </div>
</template>
