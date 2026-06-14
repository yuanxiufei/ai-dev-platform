<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query"
import { computed, ref } from "vue"
import { type UserPublic, UsersService } from "@/client"
import { handleError } from "@/utils"
import { userColumns } from "@/components/Admin/columns"

import Button from "@/components/ui/Button.vue"
import { UserPlus, Users } from "lucide-vue-next"
import DataTable from "@/components/Common/DataTable.vue"
import AddUser from "@/components/Admin/AddUser.vue"

const addOpen = ref(false)

const query = useQuery({
  queryKey: ["users"],
  queryFn: async () => {
    const { data } = await UsersService.readUsers()
    return data as { data: UserPublic[]; count: number }
  },
})

const users = computed(() => query.data.value?.data || [])
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold tracking-tight">Admin</h1>
      <Button variant="default" @click="addOpen = true">
        <UserPlus class="mr-2 h-4 w-4" />
        Add User
      </Button>
    </div>

    <!-- Loading skeleton -->
    <div v-if="query.isLoading.value" class="space-y-3">
      <div v-for="i in 5" :key="i" class="flex items-center gap-4 rounded-md border p-4">
        <div class="h-4 w-24 animate-pulse rounded bg-muted" />
        <div class="flex-1 h-4 animate-pulse rounded bg-muted" />
        <div class="h-4 w-16 animate-pulse rounded bg-muted" />
        <div class="h-4 w-16 animate-pulse rounded bg-muted" />
        <div class="h-4 w-8 animate-pulse rounded bg-muted" />
      </div>
    </div>

    <!-- Error -->
    <div
      v-else-if="query.isError.value"
      class="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive"
    >
      {{ handleError(query.error.value, 'Failed to load users') }}
    </div>

    <!-- Empty -->
    <div v-else-if="users.length === 0" class="flex flex-col items-center justify-center py-12 text-center">
      <Users class="h-12 w-12 text-muted-foreground/50" />
      <h3 class="mt-4 text-lg font-semibold">No users yet</h3>
      <p class="mt-2 text-sm text-muted-foreground">Add users to the system.</p>
    </div>

    <!-- Data Table -->
    <DataTable
      v-else
      :data="users"
      :columns="userColumns"
      empty-message="No users found."
    />

    <!-- Add User Dialog -->
    <AddUser v-model:open="addOpen" @created="query.refetch()" />
  </div>
</template>
