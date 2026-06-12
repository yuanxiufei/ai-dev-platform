<script setup lang="ts">
import AppLayout from '@/components/layout/AppLayout.vue'
</script>

<template>
  <AppLayout>
    <div class="space-y-6">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">部署管理</h1>
        <p class="text-sm text-gray-500 mt-1">管理项目部署状态和环境</p>
      </div>

      <div class="py-20 text-center">
        <div class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-white/5 flex items-center justify-center">
          <RocketIcon class="w-8 h-8 text-gray-600" />
        </div>
        <p class="text-gray-400 text-lg">部署功能开发中</p>
        <p class="text-gray-600 text-sm mt-1">敬请期待</p>
      </div>
    </div>
  </AppLayout>
</template>

<script lang="ts">
import { Rocket } from 'lucide-vue-next'
const RocketIcon = Rocket
</script>
