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
function goBack() { router.back() }
</script>

<template>
  <div class="py-6 animate-fade-in-up">
    <div v-if="!video" class="flex flex-col items-center justify-center py-20 text-center">
      <Sparkles class="w-12 h-12 text-gray-600 mb-4" /><h2 class="text-xl font-semibold text-gray-300 mb-2">视频未找到</h2>
      <p class="text-gray-500 mb-6">该视频可能已被删除</p>
      <button @click="goBack" class="px-6 py-2.5 rounded-xl bg-violet-600 text-white font-medium active:bg-violet-700 transition-colors">返回</button>
    </div>
    <template v-else>
      <!-- 移动端：视频全屏 + 信息在下方 -->
      <div class="flex flex-col gap-5">
        <!-- 导航 -->
        <div class="flex items-center justify-between">
          <button @click="goBack" class="flex items-center gap-1.5 text-gray-400 active:text-white transition-colors"><ArrowLeft class="w-5 h-5" /></button>
          <div class="flex items-center gap-1.5">
            <button @click="isLiked = !isLiked" class="p-2 rounded-lg bg-white/[0.03] border border-white/[0.06] text-gray-400 active:scale-95 transition-all" :class="{ '!text-rose-500 !border-rose-500/30 !bg-rose-500/10': isLiked }"><Heart class="w-4 h-4" :fill="isLiked ? 'currentColor' : 'none'" /></button>
            <button class="p-2 rounded-lg bg-white/[0.03] border border-white/[0.06] text-gray-400 active:scale-95 transition-all"><Share2 class="w-4 h-4" /></button>
            <button class="p-2 rounded-lg bg-white/[0.03] border border-white/[0.06] text-gray-400 active:scale-95 transition-all"><Download class="w-4 h-4" /></button>
          </div>
        </div>

        <!-- 竖屏视频 -->
        <div class="relative bg-black rounded-2xl overflow-hidden aspect-[9/16] w-full">
          <img v-if="video.thumbnailUrl" :src="video.thumbnailUrl" :alt="video.title" class="w-full h-full object-cover" />
          <div v-else class="w-full h-full bg-gray-900 flex items-center justify-center"><span class="text-gray-600 text-sm">视频预览</span></div>
          <div v-if="video.status === 'generating'" class="absolute inset-0 bg-black/60 flex flex-col items-center justify-center gap-4">
            <div class="w-14 h-14 rounded-full border-4 border-violet-500/30 border-t-violet-500 animate-spin" />
            <p class="text-white font-medium text-sm">生成中 {{ Math.min(Math.floor(video.progress), 99) }}%</p>
          </div>
        </div>

        <!-- 信息区 -->
        <div class="space-y-4">
          <div><h1 class="text-xl font-bold text-white mb-1.5">{{ video.title }}</h1><p class="text-gray-400 text-xs leading-relaxed">{{ video.prompt }}</p></div>
          <div class="grid grid-cols-2 gap-2.5">
            <div class="bg-white/[0.03] border border-white/[0.06] rounded-xl p-3"><div class="flex items-center gap-1.5 text-gray-500 text-[10px] mb-1"><Clock class="w-3 h-3" /><span>时长</span></div><p class="text-white font-semibold text-sm">{{ video.duration }}s</p></div>
            <div class="bg-white/[0.03] border border-white/[0.06] rounded-xl p-3"><div class="flex items-center gap-1.5 text-gray-500 text-[10px] mb-1"><Sparkles class="w-3 h-3" /><span>风格</span></div><p class="text-white font-semibold text-sm capitalize">{{ video.style }}</p></div>
          </div>
          <div class="bg-white/[0.03] border border-white/[0.06] rounded-xl p-3"><p class="text-[10px] text-gray-500 mb-1">状态</p>
            <span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-lg text-xs font-medium"
              :class="{
                'bg-green-500/10 text-green-400 border border-green-500/20': video.status === 'completed',
                'bg-amber-500/10 text-amber-400 border border-amber-500/20': video.status === 'generating',
                'bg-red-500/10 text-red-400 border border-red-500/20': video.status === 'failed',
                'bg-gray-500/10 text-gray-400 border border-gray-500/20': video.status === 'pending',
              }">{{ { pending: '待生成', generating: '生成中', completed: '已完成', failed: '失败' }[video.status] }}</span>
          </div>
          <p class="text-[10px] text-gray-600">创建于 {{ new Date(video.createdAt).toLocaleString('zh-CN') }}</p>
        </div>
      </div>
    </template>
  </div>
</template>
