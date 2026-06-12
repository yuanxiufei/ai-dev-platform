<script setup lang="ts">
import Sidebar from './Sidebar.vue'
import Header from './Header.vue'
</script>

<template>
  <div class="flex h-screen w-screen overflow-hidden">
    <Sidebar />
    <div class="flex flex-1 flex-col min-w-0">
      <Header />
      <main class="flex-1 overflow-y-auto p-6">
        <router-view />
      </main>
    </div>
  </div>
</template>
