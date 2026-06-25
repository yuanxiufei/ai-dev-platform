<script setup lang="ts">
import { toTypedSchema } from "@vee-validate/zod"
import { useForm } from "vee-validate"
import { ref } from "vue"
import { z } from "zod"
import { LoginService } from "@/client"
import { handleError } from "@/utils"

const schema = toTypedSchema(
  z.object({
    email: z.string().email("Invalid email address"),
  }),
)

const { handleSubmit, values, errors, isSubmitting } = useForm({
  validationSchema: schema,
})

const error = ref("")
const success = ref("")

const _onSubmit = handleSubmit(async (formValues) => {
  error.value = ""
  success.value = ""
  try {
    await LoginService.recoverPassword(formValues.email)
    success.value = "Password recovery email sent. Check your inbox."
  } catch (err: any) {
    error.value = handleError(err, "Failed to send recovery email") as string
  }
})
</script>

<template>
  <AuthLayout>
    <Card>
      <CardHeader class="text-center">
        <CardTitle>Recover Password</CardTitle>
        <CardDescription>Enter your email to receive a password reset link</CardDescription>
      </CardHeader>
      <CardContent>
        <form @submit.prevent="onSubmit" class="space-y-4">
          <Alert v-if="success" :message="success" />
          <Alert v-if="error" :message="error" type="destructive" />

          <FormItem htmlFor="email" :error="errors.email">
            <template #label>
              <Label htmlFor="email">Email</Label>
            </template>
            <Input id="email" v-model="values.email" type="email" placeholder="email@example.com" />
          </FormItem>

          <LoadingButton type="submit" :loading="isSubmitting" class="w-full">
            Send Recovery Email
          </LoadingButton>
        </form>
      </CardContent>
    </Card>
  </AuthLayout>
</template>
