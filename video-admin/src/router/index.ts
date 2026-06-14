import { createRouter, createWebHistory } from "vue-router"
import { useAuthStore } from "@/stores/auth"

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/login",
      name: "login",
      component: () => import("@/pages/Login.vue"),
      beforeEnter: () => {
        const auth = useAuthStore()
        if (auth.isLoggedIn) return "/"
      },
    },
    {
      path: "/signup",
      name: "signup",
      component: () => import("@/pages/Signup.vue"),
      beforeEnter: () => {
        const auth = useAuthStore()
        if (auth.isLoggedIn) return "/"
      },
    },
    {
      path: "/recover-password",
      name: "recover-password",
      component: () => import("@/pages/RecoverPassword.vue"),
      beforeEnter: () => {
        const auth = useAuthStore()
        if (auth.isLoggedIn) return "/"
      },
    },
    {
      path: "/reset-password",
      name: "reset-password",
      component: () => import("@/pages/ResetPassword.vue"),
    },
    {
      path: "/",
      component: () => import("@/layouts/AppLayout.vue"),
      beforeEnter: (_to, _from, next) => {
        const auth = useAuthStore()
        if (!auth.isLoggedIn) return next("/login")
        next()
      },
      children: [
        {
          path: "",
          name: "dashboard",
          component: () => import("@/pages/Dashboard.vue"),
        },
        {
          path: "items",
          name: "items",
          component: () => import("@/pages/Items.vue"),
        },
        {
          path: "admin",
          name: "admin",
          component: () => import("@/pages/Admin.vue"),
          beforeEnter: (_to, _from, next) => {
            const auth = useAuthStore()
            const user = auth.userQuery.data.value
            if (user?.is_superuser) return next()
            return next("/")
          },
        },
        {
          path: "settings",
          name: "settings",
          component: () => import("@/pages/Settings.vue"),
        },
      ],
    },
    {
      path: "/:pathMatch(.*)*",
      name: "not-found",
      component: () => import("@/pages/NotFound.vue"),
    },
  ],
})

export default router
