<script setup lang="ts">
import { cn } from '@/lib/utils'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'

defineProps<{
  class?: string
  page?: number
  totalPages?: number
  onPageChange?: (page: number) => void
  itemCount?: number
  pageSize?: number
  currentPageStart?: number
  currentPageEnd?: number
}>()
</script>

<template>
  <div :class="cn('flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between py-4', $props.class)">
    <div v-if="itemCount !== undefined" class="text-xs text-muted-foreground">
      Showing {{ currentPageStart ?? 1 }} to {{ currentPageEnd ?? itemCount }} of {{ itemCount }} entries
    </div>
    <div class="flex items-center space-x-2">
      <button
        :disabled="!page || page <= 1"
        class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground h-8 w-8 p-0"
        @click="onPageChange?.((page || 1) - 1)"
      >
        <ChevronLeft class="h-4 w-4" />
      </button>
      <div class="flex items-center gap-1">
        <template v-if="totalPages && totalPages <= 7">
          <button
            v-for="p in totalPages"
            :key="p"
            :class="cn(
              'inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 h-8 w-8 p-0',
              p === (page || 1)
                ? 'bg-primary text-primary-foreground shadow hover:bg-primary/90'
                : 'border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground',
            )"
            @click="onPageChange?.(p)"
          >{{ p }}</button>
        </template>
        <template v-else>
          <button class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground h-8 w-8 p-0"
            @click="onPageChange?.(1)"
            :class="{ 'bg-primary text-primary-foreground': (page || 1) === 1 }">1</button>
          <span v-if="(page || 1) > 3">...</span>
          <template v-for="p in [page || 1]" :key="p">
            <button
              v-if="p > 1 && p < (totalPages || 1)"
              class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 bg-primary text-primary-foreground shadow hover:bg-primary/90 h-8 w-8 p-0"
            >{{ p }}</button>
          </template>
          <span v-if="(page || 1) < (totalPages || 1) - 2">...</span>
          <button class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground h-8 w-8 p-0"
            @click="onPageChange?.(totalPages!)"
            :class="{ 'bg-primary text-primary-foreground': (page || 1) === totalPages }">{{ totalPages }}</button>
        </template>
      </div>
      <button
        :disabled="!page || !totalPages || page >= totalPages"
        class="inline-flex items-center justify-center whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50 border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground h-8 w-8 p-0"
        @click="onPageChange?.((page || 1) + 1)"
      >
        <ChevronRight class="h-4 w-4" />
      </button>
    </div>
  </div>
</template>
