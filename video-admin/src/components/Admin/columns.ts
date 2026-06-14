import type { ColumnDef } from "@tanstack/vue-table"
import { h } from "vue"
import type { UserPublic } from "@/client"
import { getInitials } from "@/utils"
import UserActionsMenu from "./UserActionsMenu.vue"

export const userColumns: ColumnDef<UserPublic, any>[] = [
  {
    id: "full_name",
    header: () => "Full Name",
    accessorFn: (row) => row.full_name || row.email,
    cell: ({ row, getValue }) => {
      const fullName = getValue() as string
      const email = row.original.email
      const currentUserEmail = localStorage.getItem("current_user_email")
      return h("div", { class: "flex items-center gap-2" }, [
        h(
          "span",
          {
            class:
              "flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium",
          },
          getInitials(fullName),
        ),
        h("span", null, fullName),
        email === currentUserEmail
          ? h(
              "span",
              {
                class:
                  "ml-1 inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground",
              },
              "You",
            )
          : null,
      ])
    },
  },
  {
    id: "email",
    header: () => "Email",
    accessorFn: (row) => row.email,
  },
  {
    id: "role",
    header: () => "Role",
    accessorFn: (row) => row.is_superuser,
    cell: ({ getValue }) => {
      const isSuperuser = getValue() as boolean
      return h(
        "span",
        {
          class: `inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${isSuperuser ? "bg-primary/10 text-primary" : "bg-muted text-muted-foreground"}`,
        },
        isSuperuser ? "Superuser" : "User",
      )
    },
  },
  {
    id: "status",
    header: () => "Status",
    accessorFn: (row) => row.is_active,
    cell: ({ getValue }) => {
      const isActive = getValue() as boolean
      return h("div", { class: "flex items-center gap-1.5" }, [
        h("span", {
          class: `h-2 w-2 rounded-full ${isActive ? "bg-green-500" : "bg-gray-400"}`,
        }),
        h("span", { class: "text-xs" }, isActive ? "Active" : "Inactive"),
      ])
    },
  },
  {
    id: "actions",
    header: () => h("span", { class: "sr-only" }, "Actions"),
    cell: ({ row }) => h(UserActionsMenu, { user: row.original }),
    meta: { className: "w-[50px] text-right" } as any,
  },
]
