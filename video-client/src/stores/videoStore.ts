import { defineStore } from 'pinia'
import { ref } from 'vue'

export type VideoStatus = 'pending' | 'generating' | 'completed' | 'failed'

export interface VideoItem {
  id: string
  title: string
  prompt: string
  status: VideoStatus
  progress: number
  thumbnailUrl?: string
  videoUrl?: string
  duration: number
  style: string
  createdAt: string
}

export const useVideoStore = defineStore('video', () => {
  const videos = ref<VideoItem[]>([])
  const isGenerating = ref(false)

  function addVideo(video: VideoItem) {
    videos.value = [video, ...videos.value]
  }

  function updateVideo(id: string, updates: Partial<VideoItem>) {
    videos.value = videos.value.map((v) => (v.id === id ? { ...v, ...updates } : v))
  }

  function removeVideo(id: string) {
    videos.value = videos.value.filter((v) => v.id !== id)
  }

  function setGenerating(val: boolean) {
    isGenerating.value = val
  }

  return { videos, isGenerating, addVideo, updateVideo, removeVideo, setGenerating }
})
