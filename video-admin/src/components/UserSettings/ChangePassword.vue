<script setup lang="ts">
import { toTypedSchema } from "@vee-validate/zod"
import { useForm } from "vee-validate"
import { ref } from "vue"
import { z } from "zod"
import { UsersService } from "@/client"
import { handleError, showSuccessToast } from "@/utils"
import Card from "@/components/ui/Card.vue"
import CardHeader from "@/components/ui/CardHeader.vue"
import CardTitle from "@/components/ui/CardTitle.vue"
import CardDescription from "@/components/ui/CardDescription.vue"
import CardContent from "@/components/ui/CardContent.vue"
import Alert from "@/components/ui/Alert.vue"
import FormItem from "@/components/ui/FormItem.vue"
import Label from "@/components/ui/Label.vue"
import PasswordInput from "@/components/ui/PasswordInput.vue"
import LoadingButton from "@/components/ui/LoadingButton.vue"

const schema = toTypedSchema(
  z
    .object({
      current_password: z.string().min(1, "Current password is required"),
      new_password: z.string().min(8, "Password must be at least 8 characters"),
      confirm_password: z.string(),
    })
    .refine((d) => d.new_password === d.confirm_password, {
      message: "Passwords do not match",
      path: ["confirm_password"],
    }),
)

const { handleSubmit, values, errors, isSubmitting } = useForm({
  validationSchema: schema,
})

const error = ref("")

const onSubmit = handleSubmit(async (formValues) => {
  error.value = ""
  try {
    await UsersService.updatePasswordMe({
      requestBody: {
        current_password: formValues.current_password,
        new_password: formValues.new_password,
      },
    })
    showSuccessToast("Password changed")
    values.current_password = ""
    values.new_password = ""
    values.confirm_password = ""
  } catch (err: any) {
    error.value = handleError(err, "Failed to change password") as string
  }
})
</script>

<template>
  <Card>
    <CardHeader>
      <CardTitle>Change Password</CardTitle>
      <CardDescription>Update your account password.</CardDescription>
    </CardHeader>
    <CardContent>
      <form @submit.prevent="onSubmit" class="space-y-4 max-w-sm">
        <Alert v-if="error" :message="error" type="destructive" />

        <FormItem htmlFor="current_password" :error="errors.current_password">
          <template #label><Label htmlFor="current_password">Current Password</Label></template>
          <PasswordInput id="current_password" :model-value="values.current_password" @update:model-value="(v: string) => values.current_password = v" autocomplete="current-password" />
        </FormItem>

        <FormItem htmlFor="new_password" :error="errors.new_password">
          <template #label><Label htmlFor="new_password">New Password</Label></template>
          <PasswordInput id="new_password" :model-value="values.new_password" @update:model-value="(v: string) => values.new_password = v" autocomplete="new-password" />
        </FormItem>

        <FormItem htmlFor="confirm_password" :error="errors.confirm_password">
          <template #label><Label htmlFor="confirm_password">Confirm New Password</Label></template>
          <PasswordInput id="confirm_password" :model-value="values.confirm_password" @update:model-value="(v: string) => values.confirm_password = v" autocomplete="new-password" />
        </FormItem>

        <LoadingButton type="submit" :loading="isSubmitting">Change Password</LoadingButton>
      </form>
    </CardContent>
  </Card>
</template>
