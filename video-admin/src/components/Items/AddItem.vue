<script setup lang="ts">
import { toTypedSchema } from "@vee-validate/zod"
import { useForm } from "vee-validate"
import { ref, watch } from "vue"
import { z } from "zod"
import { ItemsService } from "@/client"
import { handleError } from "@/utils"
import Dialog from "@/components/ui/Dialog.vue"
import DialogHeader from "@/components/ui/DialogHeader.vue"
import DialogTitle from "@/components/ui/DialogTitle.vue"
import DialogDescription from "@/components/ui/DialogDescription.vue"
import Alert from "@/components/ui/Alert.vue"
import FormItem from "@/components/ui/FormItem.vue"
import Label from "@/components/ui/Label.vue"
import Input from "@/components/ui/Input.vue"
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
  z.object({
    title: z.string().min(1, "Title is required"),
    description: z.string().optional(),
  }),
)

const { handleSubmit, values, errors, isSubmitting } = useForm({
  validationSchema: schema,
})

const error = ref("")

watch(
  () => props.open,
  (val) => {
    if (!val) {
      values.title = ""
      values.description = ""
      error.value = ""
    }
  },
)

const onSubmit = handleSubmit(async (formValues) => {
  error.value = ""
  try {
    await ItemsService.createItem({
      requestBody: {
        title: formValues.title,
        description: formValues.description,
      },
    })
    emit("update:open", false)
    emit("created")
  } catch (err: any) {
    error.value = handleError(err, "Failed to create item") as string
  }
})
</script>

<template>
  <Dialog :open="open" @update:open="emit('update:open', $event)">
    <DialogHeader>
      <DialogTitle>Create Item</DialogTitle>
      <DialogDescription>Add a new item to the system.</DialogDescription>
    </DialogHeader>
    <form @submit.prevent="onSubmit" class="mt-4 space-y-4">
      <Alert v-if="error" :message="error" type="destructive" />

      <FormItem htmlFor="title" :error="errors.title">
        <template #label><Label htmlFor="title">Title</Label></template>
        <Input id="title" :model-value="values.title" @update:model-value="(v: string) => values.title = v" placeholder="Item title" />
      </FormItem>

      <FormItem htmlFor="description" :error="errors.description">
        <template #label><Label htmlFor="description">Description</Label></template>
        <Input id="description" :model-value="values.description" @update:model-value="(v: string) => values.description = v" placeholder="Optional description" />
      </FormItem>

      <div class="flex justify-end gap-2">
        <Button variant="outline" type="button" @click="emit('update:open', false)">Cancel</Button>
        <LoadingButton type="submit" :loading="isSubmitting">Create</LoadingButton>
      </div>
    </form>
  </Dialog>
</template>
