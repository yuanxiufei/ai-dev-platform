<script setup lang="ts" generic="TData">
import type { ColumnDef } from "@tanstack/vue-table"
import { getCoreRowModel, useVueTable } from "@tanstack/vue-table"
import { computed, ref } from "vue"

const props = defineProps<{
  data: TData[]
  columns: ColumnDef<TData, any>[]
  emptyMessage?: string
}>()

const page = ref(1)
const pageSize = ref(10)
const _pageSizeOptions = [5, 10, 25, 50]

const totalPages = computed(() =>
  Math.max(1, Math.ceil(props.data.length / pageSize.value)),
)
const _currentPageStart = computed(() => (page.value - 1) * pageSize.value + 1)
const _currentPageEnd = computed(() =>
  Math.min(page.value * pageSize.value, props.data.length),
)

const paginatedData = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return props.data.slice(start, start + pageSize.value)
})

const _table = useVueTable({
  get data() {
    return paginatedData.value
  },
  get columns() {
    return props.columns
  },
  getCoreRowModel: getCoreRowModel(),
})

function _onPageChange(newPage: number) {
  page.value = Math.max(1, Math.min(newPage, totalPages.value))
}
</script>

<template>
  <div class="w-full space-y-4">
    <div class="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow
            v-for="headerGroup in table.getHeaderGroups()"
            :key="headerGroup.id"
          >
            <TableHead
              v-for="header in headerGroup.headers"
              :key="header.id"
              :class="header.column.columnDef.meta?.className as string || ''"
            >
              <FlexRender
                v-if="!header.isPlaceholder"
                :render="header.column.columnDef.header"
                :props="header.getContext()"
              />
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <template v-if="table.getRowModel().rows.length">
            <TableRow
              v-for="row in table.getRowModel().rows"
              :key="row.id"
            >
              <TableCell
                v-for="cell in row.getVisibleCells()"
                :key="cell.id"
              >
                <FlexRender
                  :render="cell.column.columnDef.cell"
                  :props="cell.getContext()"
                />
              </TableCell>
            </TableRow>
          </template>
          <TableRow v-else>
            <TableCell :colspan="columns.length" class="h-24 text-center text-muted-foreground">
              {{ emptyMessage || 'No data available.' }}
            </TableCell>
          </TableRow>
        </TableBody>
      </Table>
    </div>

    <!-- Pagination -->
    <Pagination
      v-if="data.length > 0"
      :page="page"
      :total-pages="totalPages"
      :on-page-change="onPageChange"
      :item-count="data.length"
      :page-size="pageSize"
      :current-page-start="currentPageStart"
      :current-page-end="currentPageEnd"
    />

    <!-- Page Size Selector -->
    <div v-if="data.length > 0" class="flex items-center gap-2 text-sm text-muted-foreground">
      <span>Rows per page:</span>
      <select
        v-model="pageSize"
        class="rounded-md border bg-background px-2 py-1 text-sm"
        @change="page = 1"
      >
        <option v-for="n in pageSizeOptions" :key="n" :value="n">{{ n }}</option>
      </select>
    </div>
  </div>
</template>
