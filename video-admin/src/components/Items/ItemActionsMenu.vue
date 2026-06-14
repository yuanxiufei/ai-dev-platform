<script setup lang="ts">
import { ref } from "vue"
import { Pencil, Trash2 } from "lucide-vue-next"
import type { ItemPublic } from "@/client"
import DropdownMenu from "@/components/ui/DropdownMenu.vue"
import DropdownMenuItem from "@/components/ui/DropdownMenuItem.vue"
import DropdownMenuDestructive from "@/components/ui/DropdownMenuDestructive.vue"
import EditItem from "@/components/Items/EditItem.vue"
import DeleteItem from "@/components/Items/DeleteItem.vue"

defineProps<{
  item: ItemPublic
}>()

const emit = defineEmits<{
  updated: []
  deleted: []
}>()

const editOpen = ref(false)
const deleteOpen = ref(false)
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
