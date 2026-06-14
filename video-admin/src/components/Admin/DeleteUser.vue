<script setup lang="ts">
import { ref } from "vue"
import { type UserPublic, UsersService } from "@/client"
import { handleError } from "@/utils"
import Dialog from "@/components/ui/Dialog.vue"
import DialogHeader from "@/components/ui/DialogHeader.vue"
import DialogTitle from "@/components/ui/DialogTitle.vue"
import DialogDescription from "@/components/ui/DialogDescription.vue"
import Alert from "@/components/ui/Alert.vue"
import Button from "@/components/ui/Button.vue"
import LoadingButton from "@/components/ui/LoadingButton.vue"

const props = defineProps<{
  user: UserPublic
  open: boolean
}>()

const emit = defineEmits<{
  "update:open": [value: boolean]
  deleted: []
}>()

const isSubmitting = ref(false)
const error = ref("")

async function onDelete() {
  error.value = ""
  isSubmitting.value = true
  try {
    await UsersService.deleteUser({ userId: props.user.id })
    emit("update:open", false)
    emit("deleted")
  } catch (err: any) {
    error.value = handleError(err, "Failed to delete user") as string
  } finally {
    isSubmitting.value = false
  }
}
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogHeader>
      <DialogTitle>Delete User</DialogTitle>
      <DialogDescription>
        Are you sure you want to delete "{{ user.full_name || user.email }}"? All items associated with this user will also be permanently deleted. This action cannot be undone.
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
