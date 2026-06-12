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
  { id: 'cinematic', label: '电影质感', desc: '史诗级电影风格' },
  { id: 'anime', label: '动漫风', desc: '二次元手绘风格' },
  { id: 'realistic', label: '写实', desc: '照片级真实画质' },
  { id: '3d', label: '3D 渲染', desc: '三维建模质感' },
  { id: 'vlog', label: 'Vlog', desc: '生活记录风格' },
  { id: 'retro', label: '复古', desc: '80s 怀旧胶片感' },
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
  <div class="py-16">
    <!-- Hero -->
    <section class="text-center mb-20 animate-fade-in-up">
      <div class="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-violet-500/10 border border-violet-500/20 text-violet-300 text-sm mb-6">
        <Wand2 class="w-4 h-4" /> <span>AI 驱动 · 一句话生成短视频</span>
      </div>
      <h1 class="text-6xl font-bold leading-tight mb-4">
        <span class="bg-gradient-to-r from-violet-400 via-fuchsia-400 to-amber-400 bg-clip-text text-transparent">让创意化作影像</span>
      </h1>
      <p class="text-gray-400 text-lg max-w-xl mx-auto">输入你的想法，AI 自动生成高质感短视频，支持多种风格与比例</p>
    </section>

    <!-- 生成表单 -->
    <section class="max-w-3xl mx-auto mb-16 animate-fade-in-up" style="animation-delay: 0.15s">
      <div class="bg-white/[0.03] backdrop-blur-xl border border-white/10 rounded-2xl p-8 space-y-6">
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-2">描述你的视频创意</label>
          <textarea v-model="prompt" rows="3" placeholder="例如：一个宇航员在火星上种花的科幻短片，夕阳下的红色沙漠..." class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-violet-500/50 transition-all resize-none" />
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-3">视频风格</label>
          <div class="grid grid-cols-6 gap-2">
            <button v-for="s in styles" :key="s.id" @click="selectedStyle = s.id"
              class="flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-all"
              :class="selectedStyle === s.id ? 'bg-violet-500/15 border-violet-500/40 text-violet-300' : 'bg-white/[0.02] border-white/[0.06] text-gray-400 hover:border-white/15 hover:text-gray-200'">
              <span class="text-sm font-medium">{{ s.label }}</span>
              <span class="text-[10px] opacity-60">{{ s.desc }}</span>
            </button>
          </div>
        </div>
        <div>
          <label class="block text-sm font-medium text-gray-300 mb-2"><Clock class="w-4 h-4 inline mr-1" />时长：<span class="text-violet-400">{{ duration }}s</span></label>
          <input v-model.number="duration" type="range" min="5" max="60" step="5" class="w-full h-2 bg-white/10 rounded-lg accent-violet-500 cursor-pointer" />
          <div class="flex justify-between text-xs text-gray-500 mt-1"><span>5s</span><span>30s</span><span>60s</span></div>
        </div>
        <button :disabled="!prompt.trim() || isSubmitting" @click="handleGenerate"
          class="w-full py-4 rounded-xl font-semibold text-white flex items-center justify-center gap-2 transition-all"
          :class="!prompt.trim() || isSubmitting ? 'bg-white/5 text-gray-500 cursor-not-allowed' : 'bg-gradient-to-r from-violet-600 to-fuchsia-600 hover:from-violet-500 hover:to-fuchsia-500 shadow-lg shadow-violet-500/25 active:scale-[0.98]'">
          <Loader2 v-if="isSubmitting" class="w-5 h-5 animate-spin" />
          <Sparkles v-else class="w-5 h-5" />
          {{ isSubmitting ? '生成中...' : '开始生成' }}
        </button>
      </div>
    </section>

    <!-- 生成中任务 -->
    <section v-if="store.isGenerating" class="max-w-3xl mx-auto mb-16">
      <h2 class="text-lg font-semibold text-gray-300 mb-4">当前任务</h2>
      <div v-for="v in store.videos.filter(v => v.status === 'generating')" :key="v.id" class="bg-white/[0.03] border border-white/10 rounded-2xl p-6 backdrop-blur-xl animate-fade-in-up">
        <div class="flex items-center gap-4 mb-4">
          <div class="w-12 h-12 rounded-xl bg-violet-500/15 flex items-center justify-center"><Loader2 class="w-6 h-6 text-violet-400 animate-spin" /></div>
          <div class="flex-1 min-w-0"><p class="font-medium text-white truncate">{{ v.title }}</p><p class="text-sm text-gray-500">{{ v.style }} · {{ v.duration }}s</p></div>
          <span class="text-sm text-violet-400 font-mono">{{ Math.min(Math.floor(v.progress), 99) }}%</span>
        </div>
        <div class="w-full h-2 bg-white/5 rounded-full overflow-hidden"><div class="h-full bg-gradient-to-r from-violet-500 to-fuchsia-500 rounded-full transition-all duration-300" :style="{ width: v.progress + '%' }" /></div>
      </div>
    </section>

    <!-- 最近作品 -->
    <section v-if="hasResult" class="max-w-3xl mx-auto mb-16">
      <h2 class="text-lg font-semibold text-gray-300 mb-4">最近作品 <RouterLink to="/gallery" class="text-sm text-violet-400 hover:text-violet-300 ml-2 font-normal">查看全部 →</RouterLink></h2>
      <div class="grid grid-cols-2 gap-4">
        <div v-for="v in store.videos.filter(v => v.status === 'completed').slice(0, 4)" :key="v.id" @click="router.push(`/play/${v.id}`)" class="group relative bg-white/[0.03] border border-white/10 rounded-xl overflow-hidden cursor-pointer hover:border-violet-500/30 transition-all">
          <div class="aspect-[9/16] bg-gray-800 flex items-center justify-center relative">
            <Image v-if="!v.thumbnailUrl" class="w-12 h-12 text-gray-600" />
            <img v-else :src="v.thumbnailUrl" :alt="v.title" class="w-full h-full object-cover" loading="lazy" />
            <div class="absolute inset-0 bg-black/0 group-hover:bg-black/40 transition-colors flex items-center justify-center"><Play class="w-12 h-12 text-white opacity-0 group-hover:opacity-100 transition-opacity" /></div>
          </div>
          <div class="p-3"><p class="text-sm font-medium text-white truncate">{{ v.title }}</p><p class="text-xs text-gray-500 mt-1">{{ v.duration }}s · {{ v.style }}</p></div>
        </div>
      </div>
    </section>
  </div>
</template>
