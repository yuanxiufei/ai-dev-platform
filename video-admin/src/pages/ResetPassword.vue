<script setup lang="ts">
import { toTypedSchema } from "@vee-validate/zod"
import { useForm } from "vee-validate"
import { onMounted, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { z } from "zod"
import { LoginService } from "@/client"
import { handleError } from "@/utils"

import AuthLayout from "@/layouts/AuthLayout.vue"
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

const route = useRoute()
const router = useRouter()
const token = ref((route.query.token as string) || "")

const schema = toTypedSchema(
  z
    .object({
      new_password: z.string().min(8, "Password must be at least 8 characters"),
      confirm_password: z.string(),
    })
    .refine((data) => data.new_password === data.confirm_password, {
      message: "Passwords do not match",
      path: ["confirm_password"],
    }),
)

const { handleSubmit, values, errors, isSubmitting } = useForm({
  validationSchema: schema,
})

const error = ref("")
const success = ref("")
const tokenError = ref("")

onMounted(() => {
  if (!token.value) {
    tokenError.value = "Invalid or missing reset token"
  }
})

const onSubmit = handleSubmit(async (formValues) => {
  if (!token.value) return
  error.value = ""
  success.value = ""
  try {
    await LoginService.resetPassword({
      token: token.value,
      new_password: formValues.new_password,
    })
    success.value = "Password reset successfully! Redirecting to login..."
    setTimeout(() => router.push("/login"), 2000)
  } catch (err: any) {
    error.value = handleError(err, "Failed to reset password") as string
  }
})
</script>

<template>
  <AuthLayout>
    <Card>
      <CardHeader class="text-center">
        <CardTitle>Reset Password</CardTitle>
        <CardDescription>Enter your new password</CardDescription>
      </CardHeader>
      <CardContent>
        <Alert v-if="tokenError" :message="tokenError" type="destructive" />

        <form v-else @submit.prevent="onSubmit" class="space-y-4">
          <Alert v-if="success" :message="success" />
          <Alert v-if="error" :message="error" type="destructive" />

          <FormItem htmlFor="new_password" :error="errors.new_password">
            <template #label>
              <Label htmlFor="new_password">New Password</Label>
            </template>
            <PasswordInput id="new_password" v-model="values.new_password" placeholder="New password" autocomplete="new-password" />
          </FormItem>

          <FormItem htmlFor="confirm_password" :error="errors.confirm_password">
            <template #label>
              <Label htmlFor="confirm_password">Confirm Password</Label>
            </template>
            <PasswordInput id="confirm_password" v-model="values.confirm_password" placeholder="Confirm password" autocomplete="new-password" />
          </FormItem>

          <LoadingButton type="submit" :loading="isSubmitting" class="w-full">
            Reset Password
          </LoadingButton>
        </form>
      </CardContent>
    </Card>
  </AuthLayout>
</template>
