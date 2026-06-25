<script setup lang="ts">
import { ref } from "vue"
import { UsersService } from "@/client"
import { useAuthStore } from "@/stores/auth"
import { handleError } from "@/utils"

const authStore = useAuthStore()
const confirmOpen = ref(false)
const isDeleting = ref(false)
const error = ref("")

async function _confirmDelete() {
  error.value = ""
  isDeleting.value = true
  try {
    await UsersService.deleteUserMe()
    confirmOpen.value = false
    authStore.logout()
  } catch (err: any) {
    error.value = handleError(err, "Failed to delete account") as string
  } finally {
    isDeleting.value = false
  }
}
</script>

<template>
  <Card class="border-destructive/50">
    <CardHeader>
      <CardTitle class="text-destructive">Delete Account</CardTitle>
      <CardDescription>
        Permanently delete your account and all associated data. This action cannot be undone.
      </CardDescription>
    </CardHeader>
    <CardContent>
      <Button variant="destructive" @click="confirmOpen = true">
        <Trash2 class="mr-2 h-4 w-4" />
        Delete Account
      </Button>

      <Dialog :open="confirmOpen" @update:open="confirmOpen = $event">
        <DialogHeader>
          <DialogTitle>Delete Account</DialogTitle>
          <DialogDescription>
            Are you absolutely sure? This action cannot be undone. This will permanently delete your
            account and all associated data.
          </DialogDescription>
        </DialogHeader>
        <div class="mt-4 space-y-4">
          <Alert v-if="error" :message="error" type="destructive" />
          <div class="flex justify-end gap-2">
            <Button variant="outline" @click="confirmOpen = false">Cancel</Button>
            <LoadingButton variant="destructive" :loading="isDeleting" @click="confirmDelete">
              Delete My Account
            </LoadingButton>
          </div>
        </div>
      </Dialog>
    </CardContent>
  </Card>
</template>
