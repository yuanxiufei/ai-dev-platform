<script setup lang="ts">
import { computed, ref } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { Play, Trash2, Clock, Filter } from 'lucide-vue-next'
import { useVideoStore, type VideoStatus } from '../../stores/videoStore'

const store = useVideoStore()
const router = useRouter()
const filterStatus = ref<VideoStatus | 'all'>('all')

const filtered = computed(() => filterStatus.value === 'all' ? store.videos : store.videos.filter(v => v.status === filterStatus.value))

const filters: { key: VideoStatus | 'all'; label: string }[] = [
  { key: 'all', label: '全部' }, { key: 'completed', label: '已完成' },
  { key: 'generating', label: '生成中' }, { key: 'failed', label: '失败' },
]
</script>

<template>
  <div class="py-6 animate-fade-in-up">
    <div class="mb-6"><h1 class="text-2xl font-bold text-white">作品画廊</h1><p class="text-gray-400 text-xs mt-1">你生成的所有短视频都在这里</p></div>

    <!-- 可横向滚动过滤器 -->
    <div class="flex items-center gap-1.5 mb-6 overflow-x-auto pb-1 -mx-1 px-1 scrollbar-none">
      <Filter class="w-3.5 h-3.5 text-gray-500 shrink-0" />
      <button v-for="f in filters" :key="f.key" @click="filterStatus = f.key"
        class="px-3 py-1.5 rounded-lg text-xs font-medium transition-all whitespace-nowrap shrink-0"
        :class="filterStatus === f.key ? 'bg-violet-500/20 text-violet-300 border border-violet-500/30' : 'bg-white/[0.02] text-gray-400 border border-white/[0.06] active:bg-white/[0.06]'">
        {{ f.label }}
      </button>
    </div>

    <div v-if="filtered.length === 0" class="flex flex-col items-center justify-center py-20 text-center">
      <div class="w-16 h-16 rounded-2xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mb-4"><Play class="w-7 h-7 text-gray-600" /></div>
      <h3 class="text-base font-medium text-gray-300 mb-1">还没有作品</h3>
      <p class="text-gray-500 text-xs mb-5">去首页生成你的第一个 AI 短视频吧</p>
      <RouterLink to="/" class="px-5 py-2 rounded-xl bg-violet-600 text-white text-sm font-medium active:bg-violet-700 transition-colors">去生成</RouterLink>
    </div>

    <!-- 2列网格 移动端 -->
    <div v-else class="grid grid-cols-2 gap-3">
      <div v-for="v in filtered" :key="v.id" @click="v.status === 'completed' && router.push(`/play/${v.id}`)"
        class="relative bg-white/[0.03] border border-white/10 rounded-xl overflow-hidden transition-all active:scale-[0.98]"
        :class="v.status === 'completed' ? 'active:border-violet-500/40' : ''">
        <div class="aspect-[9/16] bg-gray-800 flex items-center justify-center relative">
          <img v-if="v.thumbnailUrl" :src="v.thumbnailUrl" :alt="v.title" class="w-full h-full object-cover" loading="lazy" />
          <Play v-else class="w-8 h-8 text-gray-600" />
          <span class="absolute top-1.5 right-1.5 px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase"
            :class="{
              'bg-green-500/20 text-green-400 border border-green-500/30': v.status === 'completed',
              'bg-amber-500/20 text-amber-400 border border-amber-500/30': v.status === 'generating',
              'bg-red-500/20 text-red-400 border border-red-500/30': v.status === 'failed',
              'bg-gray-500/20 text-gray-400': v.status === 'pending',
            }">{{ { pending: '等待', generating: '生成中', completed: '完成', failed: '失败' }[v.status] }}</span>
          <div v-if="v.status === 'generating'" class="absolute bottom-0 left-0 right-0 h-1 bg-white/10">
            <div class="h-full bg-gradient-to-r from-violet-500 to-fuchsia-500 transition-all duration-300" :style="{ width: v.progress + '%' }" />
          </div>
        </div>
        <div class="p-2.5 space-y-0.5">
          <p class="text-xs font-medium text-white truncate">{{ v.title }}</p>
          <div class="flex items-center gap-1.5 text-[10px] text-gray-500"><Clock class="w-2.5 h-2.5" /><span>{{ v.duration }}s</span><span class="text-gray-600">·</span><span>{{ v.style }}</span></div>
        </div>
        <button @click.stop="store.removeVideo(v.id)" class="absolute top-1.5 left-1.5 p-1 rounded-md bg-black/50 text-gray-400 active:text-red-400 active:bg-black/70 transition-colors">
          <Trash2 class="w-3 h-3" />
        </button>
      </div>
    </div>
  </div>
</template>
