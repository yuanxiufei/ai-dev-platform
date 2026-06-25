<script setup lang="ts">
import { ref } from "vue"
import type { UserPublic } from "@/client"
import { useAuthStore } from "@/stores/auth"

const props = defineProps<{
  user: UserPublic
}>()

const _emit = defineEmits<{
  updated: []
  deleted: []
}>()

const authStore = useAuthStore()
const currentUser = authStore.userQuery.data
const _isCurrentUser = currentUser.value?.id === props.user.id

const _editOpen = ref(false)
const _deleteOpen = ref(false)
</script>

<template>
  <DropdownMenu>
    <DropdownMenuItem @click="editOpen = true" :class="{ 'opacity-50 pointer-events-none': isCurrentUser }">
      <Pencil class="mr-2 h-4 w-4" />
      Edit
    </DropdownMenuItem>
    <DropdownMenuDestructive @click="deleteOpen = true" :class="{ 'opacity-50 pointer-events-none': isCurrentUser }">
      <Trash2 class="mr-2 h-4 w-4" />
      Delete
    </DropdownMenuDestructive>
  </DropdownMenu>

  <EditUser v-if="!isCurrentUser" :user="user" v-model:open="editOpen" @updated="emit('updated')" />
  <DeleteUser v-if="!isCurrentUser" :user="user" v-model:open="deleteOpen" @deleted="emit('deleted')" />
</template>
