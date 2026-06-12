<script setup lang="ts">
import Header from './Header.vue'
</script>

<template>
  <div class="min-h-screen flex flex-col bg-gradient-to-b from-gray-950 via-gray-900 to-gray-950">
    <Header />
    <main class="flex-1 w-full max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pb-16">
      <slot />
    </main>
    <footer class="text-center py-6 text-gray-500 text-sm border-t border-white/5">
      © 2026 AI Video Studio · 让创意化作影像
    </footer>
  </div>
</template>
