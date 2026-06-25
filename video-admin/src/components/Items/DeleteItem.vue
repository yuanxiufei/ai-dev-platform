<script setup lang="ts">
import { ref } from "vue"
import { type ItemPublic, ItemsService } from "@/client"
import { handleError } from "@/utils"

const props = defineProps<{
  item: ItemPublic
  open: boolean
}>()

const emit = defineEmits<{
  "update:open": [value: boolean]
  deleted: []
}>()

const isSubmitting = ref(false)
const error = ref("")

async function _onDelete() {
  error.value = ""
  isSubmitting.value = true
  try {
    await ItemsService.deleteItem({ id: props.item.id })
    emit("update:open", false)
    emit("deleted")
  } catch (err: any) {
    error.value = handleError(err, "Failed to delete item") as string
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogHeader>
      <DialogTitle>Delete Item</DialogTitle>
      <DialogDescription>
        Are you sure you want to delete "{{ item.title }}"? This action cannot be undone.
      </DialogDescription>
    </DialogHeader>
    <div class="mt-4 space-y-4">
      <Alert v-if="error" :message="error" type="destructive" />
      <div class="flex justify-end gap-2">
        <Button variant="outline" @click="emit('update:open', false)">Cancel</Button>
        <LoadingButton variant="destructive" :loading="isSubmitting" @click="onDelete">Delete</LoadingButton>
      </div>
    </div>
  </Dialog>
</template>
