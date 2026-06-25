<script setup lang="ts">
import { Home, Monitor, Moon, Package, Sun, Users } from "lucide-vue-next"
import { useI18n } from "vue-i18n"
import { useRoute, useRouter } from "vue-router"
import { useIsMobile } from "@/composables/useMobile"
import { useAuthStore } from "@/stores/auth"
import { useSidebarStore } from "@/stores/sidebar"
import { useThemeStore } from "@/stores/theme"

const _sidebar = useSidebarStore()
const _isMobile = useIsMobile()
const themeStore = useThemeStore()
const authStore = useAuthStore()
const { t, locale } = useI18n()
const _router = useRouter()
const _route = useRoute()

const _navItems = [
  { title: "Dashboard", to: "/", icon: Home },
  { title: "Items", to: "/items", icon: Package },
]

const _adminItem = { title: "Admin", to: "/admin", icon: Users }

const user = authStore.userQuery.data
const _isSuperuser = user.value?.is_superuser

function _toggleTheme() {
  const next: Record<string, "dark" | "light" | "system"> = {
    dark: "light",
    light: "system",
    system: "dark",
  }
  themeStore.setTheme(next[themeStore.theme])
}

const _themeIcon: Record<string, any> = {
  dark: Sun,
  light: Moon,
  system: Monitor,
}

function _toggleLang() {
  locale.value = locale.value === "en" ? "zh" : "en"
}
</script>

<template>
  <!-- Mobile Toggle -->
  <div v-if="isMobile.value" class="fixed left-4 top-3 z-50 lg:hidden">
    <Button variant="ghost" size="icon" @click="sidebar.setOpenMobile(!sidebar.openMobile)">
      <Menu class="h-5 w-5" />
    </Button>
  </div>

  <!-- Sidebar Overlay -->
  <div
    v-if="isMobile.value && sidebar.openMobile"
    class="fixed inset-0 z-40 bg-black/50 lg:hidden"
    @click="sidebar.setOpenMobile(false)"
  />

  <!-- Sidebar -->
  <aside
    :class="cn(
      'fixed left-0 top-0 z-50 flex h-screen flex-col border-r bg-background transition-all duration-300',
      sidebar.state === 'collapsed' ? 'w-16' : 'w-64',
      isMobile.value && !sidebar.openMobile ? '-translate-x-full' : 'translate-x-0',
      isMobile.value ? 'w-64' : '',
    )"
  >
    <!-- Logo -->
    <div :class="cn('flex h-14 items-center border-b px-4', sidebar.state === 'collapsed' && !isMobile.value ? 'justify-center' : 'justify-between')">
      <div v-if="sidebar.state === 'expanded' || isMobile.value" class="flex items-center gap-2">
        <img src="/assets/images/favicon.png" class="h-6 w-6" />
        <span class="font-semibold text-sm">FastAPI Admin</span>
      </div>
      <img v-else src="/assets/images/favicon.png" class="h-6 w-6" />
      <Button
        v-if="!isMobile.value"
        variant="ghost"
        size="icon"
        class="h-7 w-7"
        @click="sidebar.toggleSidebar()"
      >
        <ChevronLeft v-if="sidebar.state === 'expanded'" class="h-4 w-4" />
        <ChevronRight v-else class="h-4 w-4" />
      </Button>
    </div>

    <!-- Nav Items -->
    <nav class="flex-1 space-y-1 overflow-y-auto p-2">
      <Tooltip v-for="item in navItems" :key="item.to">
        <template #trigger>
          <router-link
            :to="item.to"
            :class="cn(
              'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground',
              route.path === item.to ? 'bg-accent text-accent-foreground' : 'text-muted-foreground',
              sidebar.state === 'collapsed' && !isMobile.value ? 'justify-center px-2' : '',
            )"
          >
            <Component :is="item.icon" class="h-4 w-4 shrink-0" />
            <span v-if="sidebar.state === 'expanded' || isMobile.value">{{ item.title }}</span>
          </router-link>
        </template>
        <template v-if="sidebar.state === 'collapsed' && !isMobile.value">
          {{ item.title }}
        </template>
      </Tooltip>

      <Tooltip v-if="isSuperuser">
        <template #trigger>
          <router-link
            to="/admin"
            :class="cn(
              'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground',
              route.path === '/admin' ? 'bg-accent text-accent-foreground' : 'text-muted-foreground',
              sidebar.state === 'collapsed' && !isMobile.value ? 'justify-center px-2' : '',
            )"
          >
            <Users class="h-4 w-4 shrink-0" />
            <span v-if="sidebar.state === 'expanded' || isMobile.value">{{ t('admin') }}</span>
          </router-link>
        </template>
        <template v-if="sidebar.state === 'collapsed' && !isMobile.value">
          {{ t('admin') }}
        </template>
      </Tooltip>
    </nav>

    <!-- Footer -->
    <div class="border-t p-2">
      <!-- Theme Toggle -->
      <Tooltip>
        <template #trigger>
          <Button variant="ghost" :size="'icon'" :class="cn('w-full', sidebar.state === 'expanded' || isMobile.value ? 'justify-start px-3' : 'justify-center')" @click="toggleTheme">
            <Component :is="themeIcon[themeStore.theme]" class="h-4 w-4" />
            <span v-if="sidebar.state === 'expanded' || isMobile.value" class="ml-3 text-sm">{{ themeStore.theme.charAt(0).toUpperCase() + themeStore.theme.slice(1) }}</span>
          </Button>
        </template>
        <template v-if="sidebar.state === 'collapsed' && !isMobile.value">
          {{ themeStore.theme.charAt(0).toUpperCase() + themeStore.theme.slice(1) }}
        </template>
      </Tooltip>

      <!-- Language Toggle -->
      <Tooltip>
        <template #trigger>
          <Button variant="ghost" :size="'icon'" :class="cn('w-full', sidebar.state === 'expanded' || isMobile.value ? 'justify-start px-3' : 'justify-center')" @click="toggleLang">
            <Languages class="h-4 w-4" />
            <span v-if="sidebar.state === 'expanded' || isMobile.value" class="ml-3 text-sm">{{ locale === 'en' ? 'English' : '中文' }}</span>
          </Button>
        </template>
        <template v-if="sidebar.state === 'collapsed' && !isMobile.value">
          {{ locale === 'en' ? 'English' : '中文' }}
        </template>
      </Tooltip>

      <!-- User Info -->
      <div :class="cn('flex items-center gap-2 rounded-md p-2', sidebar.state === 'collapsed' && !isMobile.value ? 'justify-center' : '')">
        <div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium">
          {{ getInitials(user?.full_name) }}
        </div>
        <div v-if="sidebar.state === 'expanded' || isMobile.value" class="flex-1 min-w-0 text-left">
          <p class="truncate text-xs font-medium">{{ user?.full_name }}</p>
          <p class="truncate text-xs text-muted-foreground">{{ user?.email }}</p>
        </div>
        <DropdownMenu>
          <template #trigger>
            <ChevronsUpDown v-if="sidebar.state === 'expanded' || isMobile.value" class="h-3 w-3 text-muted-foreground" />
          </template>
          <DropdownMenuItem @click="router.push('/settings')">
            <Settings class="mr-2 h-4 w-4" />
            Settings
          </DropdownMenuItem>
          <DropdownMenuItem @click="authStore.logout()">
            <LogOut class="mr-2 h-4 w-4" />
            Logout
          </DropdownMenuItem>
        </DropdownMenu>
      </div>
    </div>
  </aside>
</template>
