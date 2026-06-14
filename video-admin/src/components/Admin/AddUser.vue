<script setup lang="ts">
import { toTypedSchema } from "@vee-validate/zod"
import { useForm } from "vee-validate"
import { ref, watch } from "vue"
import { z } from "zod"
import { UsersService } from "@/client"
import { handleError } from "@/utils"
import Dialog from "@/components/ui/Dialog.vue"
import DialogHeader from "@/components/ui/DialogHeader.vue"
import DialogTitle from "@/components/ui/DialogTitle.vue"
import DialogDescription from "@/components/ui/DialogDescription.vue"
import Alert from "@/components/ui/Alert.vue"
import FormItem from "@/components/ui/FormItem.vue"
import Label from "@/components/ui/Label.vue"
import Input from "@/components/ui/Input.vue"
import PasswordInput from "@/components/ui/PasswordInput.vue"
import Checkbox from "@/components/ui/Checkbox.vue"
import Button from "@/components/ui/Button.vue"
import LoadingButton from "@/components/ui/LoadingButton.vue"

const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  "update:open": [value: boolean]
  created: []
}>()

const schema = toTypedSchema(
  z
    .object({
      email: z.string().email("Invalid email"),
      full_name: z.string().min(1, "Full name is required"),
      password: z.string().min(8, "Password must be at least 8 characters"),
      confirm_password: z.string(),
      is_superuser: z.boolean(),
      is_active: z.boolean(),
    })
    .refine((d) => d.password === d.confirm_password, {
      message: "Passwords do not match",
      path: ["confirm_password"],
    }),
)

const { handleSubmit, values, errors, isSubmitting } = useForm({
  validationSchema: schema,
  initialValues: { is_superuser: false, is_active: true },
})

const error = ref("")

watch(
  () => props.open,
  (val) => {
    if (!val) error.value = ""
  },
)

const onSubmit = handleSubmit(async (formValues) => {
  error.value = ""
  try {
    await UsersService.createUser({
      requestBody: {
        email: formValues.email,
        full_name: formValues.full_name,
        password: formValues.password,
        is_superuser: formValues.is_superuser,
        is_active: formValues.is_active,
      },
    })
    emit("update:open", false)
    emit("created")
  } catch (err: any) {
    error.value = handleError(err, "Failed to create user") as string
  }
})
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogHeader>
      <DialogTitle>Add User</DialogTitle>
      <DialogDescription>Create a new user account.</DialogDescription>
    </DialogHeader>
    <form @submit.prevent="onSubmit" class="mt-4 space-y-4">
      <Alert v-if="error" :message="error" type="destructive" />

      <FormItem htmlFor="email" :error="errors.email">
        <template #label><Label htmlFor="email">Email</Label></template>
        <Input id="email" :model-value="values.email" @update:model-value="(v: string) => values.email = v" type="email" placeholder="email@example.com" />
      </FormItem>

      <FormItem htmlFor="full_name" :error="errors.full_name">
        <template #label><Label htmlFor="full_name">Full Name</Label></template>
        <Input id="full_name" :model-value="values.full_name" @update:model-value="(v: string) => values.full_name = v" placeholder="John Doe" />
      </FormItem>

      <FormItem htmlFor="password" :error="errors.password">
        <template #label><Label htmlFor="password">Password</Label></template>
        <PasswordInput id="password" :model-value="values.password" @update:model-value="(v: string) => values.password = v" placeholder="Min 8 characters" />
      </FormItem>

      <FormItem htmlFor="confirm_password" :error="errors.confirm_password">
        <template #label><Label htmlFor="confirm_password">Confirm Password</Label></template>
        <PasswordInput id="confirm_password" :model-value="values.confirm_password" @update:model-value="(v: string) => values.confirm_password = v" placeholder="Confirm password" />
      </FormItem>

      <div class="flex items-center gap-2">
        <Checkbox id="is_superuser" :model-value="values.is_superuser" @update:model-value="(v: boolean) => values.is_superuser = v" />
        <Label htmlFor="is_superuser">Superuser</Label>
      </div>

      <div class="flex items-center gap-2">
        <Checkbox id="is_active" :model-value="values.is_active" @update:model-value="(v: boolean) => values.is_active = v" />
        <Label htmlFor="is_active">Active</Label>
      </div>

      <div class="flex justify-end gap-2">
        <Button variant="outline" type="button" @click="emit('update:open', false)">Cancel</Button>
        <LoadingButton type="submit" :loading="isSubmitting">Create</LoadingButton>
      </div>
    </form>
  </Dialog>
</template>
