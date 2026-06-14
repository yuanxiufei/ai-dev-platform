<script setup lang="ts">
import { useAuthStore } from "@/stores/auth"

const authStore = useAuthStore()
const userName = authStore.userQuery.data.value?.full_name || "User"
</script>

<template>
  <div class="space-y-4">
    <h1 class="text-2xl font-bold tracking-tight">Dashboard</h1>
    <p class="text-muted-foreground">
      Welcome, {{ userName }} 👋
    </p>
  </div>
</template>
