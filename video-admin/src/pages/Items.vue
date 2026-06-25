<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query"
import { computed, ref } from "vue"
import { type ItemPublic, ItemsService } from "@/client"

const _addOpen = ref(false)

const query = useQuery({
  queryKey: ["items"],
  queryFn: async () => {
    const { data } = await ItemsService.readItems()
    return data as { data: ItemPublic[]; count: number }
  },
})

const _items = computed(() => query.data.value?.data || [])
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center justify-between">
      <h1 class="text-2xl font-bold tracking-tight">Items</h1>
      <Button variant="default" @click="addOpen = true">
        <Plus class="mr-2 h-4 w-4" />
        Add Item
      </Button>
    </div>

    <!-- Loading skeleton -->
    <div v-if="query.isLoading.value" class="space-y-3">
      <div v-for="i in 5" :key="i" class="flex items-center gap-4 rounded-md border p-4">
        <div class="h-4 w-8 animate-pulse rounded bg-muted" />
        <div class="flex-1 h-4 animate-pulse rounded bg-muted" />
        <div class="h-4 w-24 animate-pulse rounded bg-muted" />
      </div>
    </div>

    <!-- Error -->
    <div
      v-else-if="query.isError.value"
      class="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive"
    >
      {{ handleError(query.error.value, 'Failed to load items') }}
    </div>

    <!-- Empty -->
    <div v-else-if="items.length === 0" class="flex flex-col items-center justify-center py-12 text-center">
      <Package class="h-12 w-12 text-muted-foreground/50" />
      <h3 class="mt-4 text-lg font-semibold">No items yet</h3>
      <p class="mt-2 text-sm text-muted-foreground">Create your first item to get started.</p>
      <Button class="mt-4" @click="addOpen = true">
        <Plus class="mr-2 h-4 w-4" />
        Add Item
      </Button>
    </div>

    <!-- Data Table -->
    <DataTable
      v-else
      :data="items"
      :columns="itemsColumns"
      empty-message="No items found."
    />

    <!-- Add Item Dialog -->
    <AddItem v-model:open="addOpen" @created="query.refetch()" />
  </div>
</template>
