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

const schema = toTypedSchema(
  z
    .object({
      full_name: z.string().min(1, "Full name is required"),
      email: z.string().email("Invalid email address"),
      password: z.string().min(8, "Password must be at least 8 characters"),
      confirm_password: z.string(),
    })
    .refine((data) => data.password === data.confirm_password, {
      message: "Passwords do not match",
      path: ["confirm_password"],
    }),
)

const { handleSubmit, values, errors, isSubmitting } = useForm({
  validationSchema: schema,
})

const signupError = ref("")
const signupSuccess = ref("")

const onSubmit = handleSubmit(async (formValues) => {
  signupError.value = ""
  signupSuccess.value = ""
  try {
    await authStore.signUpMutation.mutateAsync({
      full_name: formValues.full_name,
      email: formValues.email,
      password: formValues.password,
    } as any)
    signupSuccess.value =
      "Account created successfully! Redirecting to login..."
    setTimeout(() => {
      router.push("/login")
    }, 2000)
  } catch (err: any) {
    signupError.value = handleError(err, "Signup failed") as string
  }
})

const router = useRouter()
</script>

<template>
  <AuthLayout>
    <Card>
      <CardHeader class="text-center">
        <CardTitle>Sign Up</CardTitle>
        <CardDescription>Create an account to get started</CardDescription>
      </CardHeader>
      <CardContent>
        <form @submit.prevent="onSubmit" class="space-y-4">
          <Alert v-if="signupSuccess" :message="signupSuccess" />
          <Alert v-if="signupError" :message="signupError" type="destructive" />

          <FormItem htmlFor="full_name" :error="errors.full_name">
            <template #label>
              <Label htmlFor="full_name">Full Name</Label>
            </template>
            <Input id="full_name" v-model="values.full_name" placeholder="John Doe" />
          </FormItem>

          <FormItem htmlFor="email" :error="errors.email">
            <template #label>
              <Label htmlFor="email">Email</Label>
            </template>
            <Input id="email" v-model="values.email" type="email" placeholder="email@example.com" autocomplete="username" />
          </FormItem>

          <FormItem htmlFor="password" :error="errors.password">
            <template #label>
              <Label htmlFor="password">Password</Label>
            </template>
            <PasswordInput id="password" v-model="values.password" placeholder="Create a password" autocomplete="new-password" />
          </FormItem>

          <FormItem htmlFor="confirm_password" :error="errors.confirm_password">
            <template #label>
              <Label htmlFor="confirm_password">Confirm Password</Label>
            </template>
            <PasswordInput id="confirm_password" v-model="values.confirm_password" placeholder="Confirm password" autocomplete="new-password" />
          </FormItem>

          <LoadingButton type="submit" :loading="isSubmitting" class="w-full">
            Create Account
          </LoadingButton>
        </form>
      </CardContent>
      <CardFooter class="flex justify-center text-sm">
        <span class="text-muted-foreground">Already have an account?</span>
        <router-link to="/login" class="ml-1 text-primary hover:underline">Sign in</router-link>
      </CardFooter>
    </Card>
  </AuthLayout>
</template>
