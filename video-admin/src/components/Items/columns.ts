import type { ColumnDef } from "@tanstack/vue-table"
import { h } from "vue"
import type { ItemPublic } from "@/client"
import ItemActionsMenu from "./ItemActionsMenu.vue"

export const itemsColumns: ColumnDef<ItemPublic, any>[] = [
  {
    id: "id",
    header: () => "ID",
    accessorFn: (row) => row.id,
    cell: ({ row }) => {
      return h("div", { class: "flex items-center gap-2" }, [
        h(
          "span",
          { class: "text-xs text-muted-foreground font-mono" },
          String(row.original.id),
        ),
      ])
    },
    meta: { className: "w-[100px]" } as any,
  },
  {
    id: "title",
    header: () => "Title",
    accessorFn: (row) => row.title,
  },
  {
    id: "description",
    header: () => "Description",
    accessorFn: (row) => row.description,
    cell: ({ getValue }) => {
      const val = getValue() as string
      return val ? (val.length > 60 ? `${val.slice(0, 60)}...` : val) : "—"
    },
  },
  {
    id: "actions",
    header: () => h("span", { class: "sr-only" }, "Actions"),
    cell: ({ row }) => h(ItemActionsMenu, { item: row.original }),
    meta: { className: "w-[50px] text-right" } as any,
  },
]
