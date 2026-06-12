<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft, Download, Share2, Heart, Clock, Sparkles } from 'lucide-vue-next'
import { useVideoStore } from '../../stores/videoStore'

const route = useRoute()
const router = useRouter()
const store = useVideoStore()
const video = computed(() => store.videos.find(v => v.id === route.params.id))
const isLiked = ref(false)
function goBack() { router.push('/gallery') }
</script>

<template>
  <div class="py-12 animate-fade-in-up">
    <div v-if="!video" class="flex flex-col items-center justify-center py-20 text-center">
      <Sparkles class="w-12 h-12 text-gray-600 mb-4" /><h2 class="text-xl font-semibold text-gray-300 mb-2">视频未找到</h2>
      <p class="text-gray-500 mb-6">该视频可能已被删除</p>
      <button @click="goBack" class="px-6 py-2.5 rounded-xl bg-violet-600 text-white font-medium hover:bg-violet-500 transition-colors">返回画廊</button>
    </div>
    <template v-else>
      <div class="flex items-center justify-between mb-8">
        <button @click="goBack" class="flex items-center gap-2 text-gray-400 hover:text-white transition-colors"><ArrowLeft class="w-5 h-5" /><span class="text-sm font-medium">返回</span></button>
        <div class="flex items-center gap-2">
          <button @click="isLiked = !isLiked" class="p-2.5 rounded-xl bg-white/[0.03] border border-white/[0.06] text-gray-400 hover:border-white/15 transition-all" :class="{ '!text-rose-500 !border-rose-500/30 !bg-rose-500/10': isLiked }"><Heart class="w-5 h-5" :fill="isLiked ? 'currentColor' : 'none'" /></button>
          <button class="p-2.5 rounded-xl bg-white/[0.03] border border-white/[0.06] text-gray-400 hover:border-white/15 transition-all"><Share2 class="w-5 h-5" /></button>
          <button class="p-2.5 rounded-xl bg-white/[0.03] border border-white/[0.06] text-gray-400 hover:border-white/15 transition-all"><Download class="w-5 h-5" /></button>
        </div>
      </div>
      <!-- PC 双列布局 -->
      <div class="grid grid-cols-2 gap-8">
        <div class="relative bg-black rounded-2xl overflow-hidden aspect-[9/16]" style="max-height: 80vh">
          <img v-if="video.thumbnailUrl" :src="video.thumbnailUrl" :alt="video.title" class="w-full h-full object-cover" />
          <div v-else class="w-full h-full bg-gray-900 flex items-center justify-center"><span class="text-gray-600">视频预览</span></div>
          <div v-if="video.status === 'generating'" class="absolute inset-0 bg-black/60 flex flex-col items-center justify-center gap-4">
            <div class="w-16 h-16 rounded-full border-4 border-violet-500/30 border-t-violet-500 animate-spin" />
            <p class="text-white font-medium">生成中 {{ Math.min(Math.floor(video.progress), 99) }}%</p>
          </div>
        </div>
        <div class="space-y-6">
          <div><h1 class="text-2xl font-bold text-white mb-2">{{ video.title }}</h1><p class="text-gray-400 text-sm leading-relaxed">{{ video.prompt }}</p></div>
          <div class="grid grid-cols-2 gap-3">
            <div class="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4"><div class="flex items-center gap-2 text-gray-500 text-xs mb-1"><Clock class="w-3.5 h-3.5" /><span>时长</span></div><p class="text-white font-semibold">{{ video.duration }}s</p></div>
            <div class="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4"><div class="flex items-center gap-2 text-gray-500 text-xs mb-1"><Sparkles class="w-3.5 h-3.5" /><span>风格</span></div><p class="text-white font-semibold capitalize">{{ video.style }}</p></div>
          </div>
          <div class="bg-white/[0.03] border border-white/[0.06] rounded-xl p-4"><p class="text-xs text-gray-500 mb-1">状态</p>
            <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-sm font-medium"
              :class="{
                'bg-green-500/10 text-green-400 border border-green-500/20': video.status === 'completed',
                'bg-amber-500/10 text-amber-400 border border-amber-500/20': video.status === 'generating',
                'bg-red-500/10 text-red-400 border border-red-500/20': video.status === 'failed',
                'bg-gray-500/10 text-gray-400 border border-gray-500/20': video.status === 'pending',
              }">{{ { pending: '待生成', generating: '生成中', completed: '已完成', failed: '失败' }[video.status] }}</span>
          </div>
          <p class="text-xs text-gray-600">创建于 {{ new Date(video.createdAt).toLocaleString('zh-CN') }}</p>
        </div>
      </div>
    </template>
  </div>
</template>
