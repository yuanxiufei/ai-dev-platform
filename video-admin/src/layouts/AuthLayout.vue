<script setup lang="ts">
import { useI18n } from "vue-i18n"
import { useThemeStore } from "@/stores/theme"

const { t, locale } = useI18n()
const themeStore = useThemeStore()

const _toggleLanguage = () => {
  // Toggle between English and Chinese
  const newLocale = locale.value === "en" ? "zh" : "en"
  locale.value = newLocale
  // Update the locale in localStorage for persistence
  localStorage.setItem("locale", newLocale)
}

const _toggleTheme = () => {
  if (themeStore.theme === "light") {
    themeStore.setTheme("dark")
  } else if (themeStore.theme === "dark") {
    themeStore.setTheme("system")
  } else {
    themeStore.setTheme("light")
  }
}
</script>

<template>
  <div class="grid min-h-svh lg:grid-cols-2">
    <div class="flex flex-col gap-4 p-6 md:p-10">
      <div class="flex justify-center gap-2 md:justify-start">
        <img src="/assets/images/favicon.png" class="h-8 w-8" />
        <span class="text-lg font-semibold">FastAPI Admin</span>
      </div>
      <div class="flex flex-1 items-center justify-center">
        <div class="w-full max-w-xs">
          <slot />
        </div>
      </div>
    </div>
    <div class="relative hidden bg-muted lg:block">
      <div class="absolute inset-0 flex items-center justify-center">
        <img
          src="/assets/images/fastapi-logo.svg"
          alt="FastAPI"
          class="h-1/2 w-1/2 object-contain dark:brightness-[0.2] dark:grayscale"
        />
      </div>
      <!-- Top right corner buttons -->
      <div class="absolute top-4 right-4 flex gap-2">
        <!-- Theme toggle -->
        <button
          @click="toggleTheme"
          class="flex items-center rounded-md p-2 hover:bg-muted"
          :title="t('theme.toggle')"
        >
          <Sun v-if="themeStore.resolvedTheme === 'light'" class="h-5 w-5" />
          <Moon v-else class="h-5 w-5" />
        </button>
        
        <!-- Language switcher -->
        <button
          @click="toggleLanguage"
          class="flex items-center rounded-md p-2 hover:bg-muted"
          :title="t('language.toggle')"
        >
          <Languages class="h-5 w-5" />
        </button>
      </div>
    </div>
  </div>
</template>
