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
  <div class="py-12 animate-fade-in-up">
    <div class="flex items-center justify-between mb-8">
      <div><h1 class="text-3xl font-bold text-white">作品画廊</h1><p class="text-gray-400 text-sm mt-1">你生成的所有短视频都在这里</p></div>
    </div>
    <div class="flex items-center gap-2 mb-8">
      <Filter class="w-4 h-4 text-gray-500" />
      <button v-for="f in filters" :key="f.key" @click="filterStatus = f.key"
        class="px-4 py-2 rounded-lg text-sm font-medium transition-all"
        :class="filterStatus === f.key ? 'bg-violet-500/20 text-violet-300 border border-violet-500/30' : 'bg-white/[0.02] text-gray-400 border border-white/[0.06] hover:border-white/15 hover:text-gray-200'">
        {{ f.label }}
      </button>
    </div>
    <div v-if="filtered.length === 0" class="flex flex-col items-center justify-center py-20 text-center">
      <div class="w-20 h-20 rounded-2xl bg-white/[0.03] border border-white/[0.06] flex items-center justify-center mb-4"><Play class="w-8 h-8 text-gray-600" /></div>
      <h3 class="text-lg font-medium text-gray-300 mb-1">还没有作品</h3>
      <p class="text-gray-500 text-sm mb-6">去首页生成你的第一个 AI 短视频吧</p>
      <RouterLink to="/" class="px-6 py-2.5 rounded-xl bg-violet-600 text-white font-medium hover:bg-violet-500 transition-colors">去生成</RouterLink>
    </div>
    <!-- 4列网格 -->
    <div v-else class="grid grid-cols-4 gap-4">
      <div v-for="v in filtered" :key="v.id" @click="v.status === 'completed' && router.push(`/play/${v.id}`)"
        class="group relative bg-white/[0.03] border border-white/10 rounded-xl overflow-hidden transition-all hover:-translate-y-1 hover:border-violet-500/30"
        :class="v.status === 'completed' ? 'cursor-pointer' : 'cursor-default'">
        <div class="aspect-[9/16] bg-gray-800 flex items-center justify-center relative">
          <img v-if="v.thumbnailUrl" :src="v.thumbnailUrl" :alt="v.title" class="w-full h-full object-cover" loading="lazy" />
          <Play v-else class="w-10 h-10 text-gray-600" />
          <span class="absolute top-2 right-2 px-2 py-0.5 rounded-md text-[10px] font-semibold uppercase"
            :class="{
              'bg-green-500/20 text-green-400 border border-green-500/30': v.status === 'completed',
              'bg-amber-500/20 text-amber-400 border border-amber-500/30': v.status === 'generating',
              'bg-red-500/20 text-red-400 border border-red-500/30': v.status === 'failed',
              'bg-gray-500/20 text-gray-400': v.status === 'pending',
            }">{{ { pending: '等待', generating: '生成中', completed: '完成', failed: '失败' }[v.status] }}</span>
          <div v-if="v.status === 'completed'" class="absolute inset-0 bg-black/0 group-hover:bg-black/50 transition-colors flex items-center justify-center">
            <Play class="w-12 h-12 text-white opacity-0 group-hover:opacity-100 transition-opacity" />
          </div>
          <div v-if="v.status === 'generating'" class="absolute bottom-0 left-0 right-0 h-1 bg-white/10">
            <div class="h-full bg-gradient-to-r from-violet-500 to-fuchsia-500 transition-all duration-300" :style="{ width: v.progress + '%' }" />
          </div>
        </div>
        <div class="p-3 space-y-1">
          <p class="text-sm font-medium text-white truncate">{{ v.title }}</p>
          <div class="flex items-center gap-2 text-xs text-gray-500"><Clock class="w-3 h-3" /><span>{{ v.duration }}s</span><span class="text-gray-600">·</span><span>{{ v.style }}</span></div>
        </div>
        <button @click.stop="store.removeVideo(v.id)" class="absolute top-2 left-2 p-1.5 rounded-lg bg-black/40 text-gray-400 opacity-0 group-hover:opacity-100 transition-all hover:text-red-400 hover:bg-black/60">
          <Trash2 class="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  </div>
</template>
