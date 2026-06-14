<script setup lang="ts">
import { toTypedSchema } from "@vee-validate/zod"
import { useForm } from "vee-validate"
import { ref, watch } from "vue"
import { z } from "zod"
import { Pencil, X } from "lucide-vue-next"
import { UsersService } from "@/client"
import { useAuthStore } from "@/stores/auth"
import { handleError, showSuccessToast } from "@/utils"
import Card from "@/components/ui/Card.vue"
import CardHeader from "@/components/ui/CardHeader.vue"
import CardTitle from "@/components/ui/CardTitle.vue"
import CardDescription from "@/components/ui/CardDescription.vue"
import CardContent from "@/components/ui/CardContent.vue"
import Button from "@/components/ui/Button.vue"
import Alert from "@/components/ui/Alert.vue"
import FormItem from "@/components/ui/FormItem.vue"
import Label from "@/components/ui/Label.vue"
import Input from "@/components/ui/Input.vue"
import LoadingButton from "@/components/ui/LoadingButton.vue"

const authStore = useAuthStore()
const user = authStore.userQuery.data

const schema = toTypedSchema(
  z.object({
    full_name: z.string().min(1, "Full name is required"),
    email: z.string().email("Invalid email"),
  }),
)

const { handleSubmit, values, errors, isSubmitting, setValues } = useForm({
  validationSchema: schema,
})

const isEditing = ref(false)
const error = ref("")

watch(
  user,
  (u) => {
    if (u) {
      setValues({ full_name: u.full_name || "", email: u.email })
    }
  },
  { immediate: true },
)

function startEdit() {
  if (user.value) {
    setValues({
      full_name: user.value.full_name || "",
      email: user.value.email,
    })
  }
  isEditing.value = true
}

const onSubmit = handleSubmit(async (formValues) => {
  error.value = ""
  try {
    const body: Record<string, any> = {}
    if (formValues.full_name !== user.value?.full_name)
      body.full_name = formValues.full_name
    if (formValues.email !== user.value?.email) body.email = formValues.email
    if (Object.keys(body).length === 0) {
      isEditing.value = false
      return
    }
    await UsersService.updateUserMe({ requestBody: body })
    authStore.userQuery.refetch()
    isEditing.value = false
    showSuccessToast("Profile updated")
  } catch (err: any) {
    error.value = handleError(err, "Failed to update profile") as string
  }
})
</script>

<template>
  <Card>
    <CardHeader>
      <div class="flex items-center justify-between">
        <div>
          <CardTitle>My profile</CardTitle>
          <CardDescription>Update your personal information.</CardDescription>
        </div>
        <Button v-if="!isEditing" variant="outline" size="sm" @click="startEdit">
          <Pencil class="mr-1 h-3 w-3" />
          Edit
        </Button>
      </div>
    </CardHeader>
    <CardContent>
      <form @submit.prevent="onSubmit" class="space-y-4">
        <Alert v-if="error" :message="error" type="destructive" />

        <FormItem htmlFor="full_name" :error="errors.full_name">
          <template #label><Label htmlFor="full_name">Full Name</Label></template>
          <Input
            id="full_name"
            :model-value="values.full_name"
            @update:model-value="(v: string) => values.full_name = v"
            :disabled="!isEditing"
          />
        </FormItem>

        <FormItem htmlFor="email" :error="errors.email">
          <template #label><Label htmlFor="email">Email</Label></template>
          <Input
            id="email"
            :model-value="values.email"
            @update:model-value="(v: string) => values.email = v"
            type="email"
            :disabled="!isEditing"
          />
        </FormItem>

        <div v-if="isEditing" class="flex justify-end gap-2">
          <Button variant="outline" type="button" @click="isEditing = false">
            <X class="mr-1 h-3 w-3" />
            Cancel
          </Button>
          <LoadingButton type="submit" :loading="isSubmitting">Save</LoadingButton>
        </div>
      </form>
    </CardContent>
  </Card>
</template>
