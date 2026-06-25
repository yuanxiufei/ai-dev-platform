<script setup lang="ts">
import { AlertTriangle, Key, User } from "lucide-vue-next"
import { ref } from "vue"
import type { TabItem } from "@/components/ui/Tabs.vue"
import { useAuthStore } from "@/stores/auth"

const authStore = useAuthStore()
const user = authStore.userQuery.data
const isSuperuser = user.value?.is_superuser

const tabs: TabItem[] = [
  { value: "profile", label: "My profile", icon: User },
  { value: "password", label: "Password", icon: Key },
]
if (!isSuperuser) {
  tabs.push({ value: "danger", label: "Danger zone", icon: AlertTriangle })
}

const _activeTab = ref("profile")
</script>

<template>
  <div class="space-y-6">
    <h1 class="text-2xl font-bold tracking-tight">Settings</h1>

    <Tabs :model-value="activeTab" :tabs="tabs" @update:model-value="activeTab = $event">
      <template #default="{ activeTab }">
        <div v-if="activeTab === 'profile'" class="pt-4">
          <UserInformation />
        </div>
        <div v-if="activeTab === 'password'" class="pt-4 max-w-lg">
          <ChangePassword />
        </div>
        <div v-if="activeTab === 'danger'" class="pt-4 max-w-lg">
          <DeleteAccount />
        </div>
      </template>
    </Tabs>
  </div>
</template>
