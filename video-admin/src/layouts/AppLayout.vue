<script setup lang="ts">
import { computed } from "vue"
import { useIsMobile } from "@/composables/useMobile"
import { useAuthStore } from "@/stores/auth"
import { useSidebarStore } from "@/stores/sidebar"
import { useThemeStore } from "@/stores/theme"

const sidebar = useSidebarStore()
const isMobile = useIsMobile()
const themeStore = useThemeStore()
const _authStore = useAuthStore()

const _mainStyles = computed(() => {
  if (isMobile.value) return "ml-0"
  return sidebar.state === "collapsed" ? "ml-16" : "ml-64"
})

const _toggleTheme = () => {
  if (themeStore.theme === "light") {
    themeStore.setTheme("dark")
  } else if (themeStore.theme === "dark") {
    themeStore.setTheme("system")
  } else {
    themeStore.setTheme("light")
  }
}

const _toggleLanguage = () => {
  // For now, just toggle between English and Chinese
  // In a real app, this would be more sophisticated
  const currentLocale = import.meta.env.VITE_APP_LOCALE || "en"
  const newLocale = currentLocale === "en" ? "zh" : "en"
  import.meta.env.VITE_APP_LOCALE = newLocale
  // This would need to be implemented more properly with a proper i18n switcher
}
</script>

<template>
  <div class="flex min-h-screen">
    <AppSidebar />

    <!-- Overlay for mobile sidebar - clicking this closes the sidebar -->
    <div
      v-if="isMobile.value && sidebar.openMobile"
      class="fixed inset-0 z-40 bg-black/50"
      @click="sidebar.setOpenMobile(false)"
    />

    <main
      :class="cn(
        'flex flex-1 flex-col transition-all duration-300',
        mainStyles,
      )"
    >
      <!-- Sticky header -->
      <header class="sticky top-0 z-30 flex h-14 items-center gap-4 border-b bg-background px-4 sm:px-6">
        <div class="flex flex-1 items-center justify-end">
          <!-- Theme toggle -->
          <button
            @click="toggleTheme"
            class="mr-2 flex items-center rounded-md p-2 hover:bg-muted"
            :title="$t('theme.toggle')"
          >
            <Sun v-if="themeStore.resolvedTheme === 'light'" class="h-5 w-5" />
            <Moon v-else class="h-5 w-5" />
          </button>

          <!-- Language switcher -->
          <button
            @click="toggleLanguage"
            class="mr-2 flex items-center rounded-md p-2 hover:bg-muted"
            :title="$t('language.toggle')"
          >
            <Languages class="h-5 w-5" />
          </button>

          <!-- User dropdown -->
          <DropdownMenu>
            <DropdownMenuTrigger class="flex items-center rounded-md p-2 hover:bg-muted">
              <Avatar class="h-8 w-8" :alt="authStore.userQuery.data?.full_name || 'User'" />
              <ChevronDown class="ml-1 h-4 w-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent class="w-56">
              <DropdownMenuItem>
                <User class="mr-2 h-4 w-4" />
                <span>{{ $t('user.profile') }}</span>
              </DropdownMenuItem>
              <DropdownMenuItem>
                <Settings class="mr-2 h-4 w-4" />
                <span>{{ $t('user.settings') }}</span>
              </DropdownMenuItem>
              <div class="border-t my-1"></div>
              <DropdownMenuItem @click="authStore.logout">
                <LogOut class="mr-2 h-4 w-4" />
                <span>{{ $t('user.logout') }}</span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      <!-- Page content -->
      <div class="flex-1 px-4 py-6 sm:px-6 lg:px-8">
        <div class="mx-auto max-w-7xl">
          <RouterView />
        </div>
      </div>

      <!-- Footer -->
      <footer class="border-t py-4 text-center text-xs text-muted-foreground">
        &copy; {{ new Date().getFullYear() }} Full Stack FastAPI Template
      </footer>
    </main>
  </div>
</template>
