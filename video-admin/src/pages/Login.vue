<script setup lang="ts">
import { toTypedSchema } from "@vee-validate/zod"
import { useForm } from "vee-validate"
import { ref } from "vue"
import { useRouter } from "vue-router"
import { z } from "zod"
import { useAuthStore } from "@/stores/auth"
import { handleError } from "@/utils"

import AuthLayout from "@/layouts/AuthLayout.vue"
import Card from "@/components/ui/Card.vue"
import CardHeader from "@/components/ui/CardHeader.vue"
import CardTitle from "@/components/ui/CardTitle.vue"
import CardDescription from "@/components/ui/CardDescription.vue"
import CardContent from "@/components/ui/CardContent.vue"
import CardFooter from "@/components/ui/CardFooter.vue"
import Alert from "@/components/ui/Alert.vue"
import FormItem from "@/components/ui/FormItem.vue"
import Label from "@/components/ui/Label.vue"
import Input from "@/components/ui/Input.vue"
import PasswordInput from "@/components/ui/PasswordInput.vue"
import LoadingButton from "@/components/ui/LoadingButton.vue"

const authStore = useAuthStore()
const router = useRouter()

const schema = toTypedSchema(
  z.object({
    email: z.string().email("Invalid email address"),
    password: z.string().min(8, "Password must be at least 8 characters"),
  }),
)

const { handleSubmit, values, setFieldValue, errors, isSubmitting } = useForm({
  validationSchema: schema,
})

const loginError = ref("")

const onSubmit = handleSubmit(async (formValues) => {
  loginError.value = ""
  try {
    await authStore.loginMutation.mutateAsync({
      username: formValues.email,
      password: formValues.password,
    } as any)
  } catch (err: any) {
    loginError.value = handleError(err, "Login failed") as string
  }
})
</script>

<template>
  <AuthLayout>
    <Card>
      <CardHeader class="text-center">
        <CardTitle>Login</CardTitle>
        <CardDescription>Enter your credentials to sign in</CardDescription>
      </CardHeader>
      <CardContent>
        <form @submit.prevent="onSubmit" class="space-y-4">
          <Alert v-if="loginError" :message="loginError" type="destructive" />

          <FormItem htmlFor="email" :error="errors.email">
            <template #label>
              <Label htmlFor="email">Email</Label>
            </template>
            <Input
              id="email"
              v-model="values.email"
              type="email"
              placeholder="email@example.com"
              autocomplete="username"
            />
          </FormItem>

          <FormItem htmlFor="password" :error="errors.password">
            <template #label>
              <Label htmlFor="password">Password</Label>
            </template>
            <PasswordInput
              id="password"
              v-model="values.password"
              placeholder="Enter your password"
              autocomplete="current-password"
            />
          </FormItem>

          <LoadingButton type="submit" :loading="isSubmitting" class="w-full">
            Sign In
          </LoadingButton>
        </form>
      </CardContent>
      <CardFooter class="flex justify-center gap-2 text-sm">
        <router-link to="/recover-password" class="text-primary hover:underline">Forgot password?</router-link>
        <span class="text-muted-foreground">|</span>
        <router-link to="/signup" class="text-primary hover:underline">Sign up</router-link>
      </CardFooter>
    </Card>
  </AuthLayout>
</template>
