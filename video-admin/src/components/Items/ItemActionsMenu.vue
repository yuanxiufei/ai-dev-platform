<script setup lang="ts">
import { ref } from "vue"
import type { ItemPublic } from "@/client"

defineProps<{
  item: ItemPublic
}>()

const _emit = defineEmits<{
  updated: []
  deleted: []
}>()

const _editOpen = ref(false)
const _deleteOpen = ref(false)
</script>

<template>
  <DropdownMenu>
    <DropdownMenuItem @click="editOpen = true">
      <Pencil class="mr-2 h-4 w-4" />
      Edit
    </DropdownMenuItem>
    <DropdownMenuDestructive @click="deleteOpen = true">
      <Trash2 class="mr-2 h-4 w-4" />
      Delete
    </DropdownMenuDestructive>
  </DropdownMenu>

  <EditItem :item="item" v-model:open="editOpen" @updated="emit('updated')" />
  <DeleteItem :item="item" v-model:open="deleteOpen" @deleted="emit('deleted')" />
</template>
