<script setup lang="ts">
import Sidebar from './Sidebar.vue'
</script>

<template>
  <div class="flex h-screen w-screen overflow-hidden bg-surface-950">
    <Sidebar />
    <div class="flex flex-1 flex-col min-w-0">
      <main class="flex-1 overflow-y-auto">
        <router-view v-slot="{ Component }">
          <transition
            enter-active-class="transition-all duration-300 ease-out"
            enter-from-class="opacity-0 translate-y-4"
            enter-to-class="opacity-100 translate-y-0"
            leave-active-class="transition-all duration-200 ease-in"
            leave-from-class="opacity-100 translate-y-0"
            leave-to-class="opacity-0 -translate-y-4"
            mode="out-in"
          >
            <component :is="Component" />
          </transition>
        </router-view>
      </main>
    </div>
  </div>
</template>
