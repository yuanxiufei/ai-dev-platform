<script setup lang="ts">
import { useToast } from "@/composables/useToast"
import { useThemeStore } from "@/stores/theme"

const themeStore = useThemeStore()
themeStore.applyTheme()

const { toasts } = useToast()
</script>

<template>
  <RouterView />
  <ToastProvider :toasts="toasts" />
</template>
