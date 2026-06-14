import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query"
import { defineStore } from "pinia"
import { computed, ref } from "vue"
import { useRouter } from "vue-router"
import {
  type Body_login_login_access_token,
  LoginService,
  type Token,
  type UserPublic,
  type UserRegister,
  UsersService,
} from "@/client"
import { OpenAPI } from "@/client/core/OpenAPI"

export const useAuthStore = defineStore("auth", () => {
  const token = ref<string | null>(localStorage.getItem("access_token"))
  const router = useRouter()
  const queryClient = useQueryClient()

  const isLoggedIn = computed(() => !!token.value)

  // Configure OpenAPI token
  if (token.value) {
    OpenAPI.TOKEN = token.value
  }
  OpenAPI.BASE = import.meta.env.VITE_API_URL || ""

  const userQuery = useQuery({
    queryKey: ["user", "me"],
    queryFn: async () => {
      const { data } = await UsersService.readUserMe()
      return data as UserPublic
    },
    enabled: computed(() => !!token.value),
    retry: false,
    staleTime: 5 * 60 * 1000,
  })

  const loginMutation = useMutation({
    mutationFn: async (credentials: Body_login_login_access_token) => {
      const { data } = await LoginService.loginAccessToken({
        formData: credentials,
      })
      return data as Token
    },
    onSuccess: (data) => {
      token.value = data.access_token
      localStorage.setItem("access_token", data.access_token)
      OpenAPI.TOKEN = data.access_token
      queryClient.invalidateQueries({ queryKey: ["user", "me"] })
      router.push("/")
    },
  })

  const signUpMutation = useMutation({
    mutationFn: async (data: UserRegister) => {
      return UsersService.registerUser({ requestBody: data })
    },
    onSuccess: () => {
      router.push("/login")
    },
  })

  function logout() {
    token.value = null
    localStorage.removeItem("access_token")
    OpenAPI.TOKEN = undefined
    queryClient.clear()
    router.push("/login")
  }

  return { token, isLoggedIn, userQuery, loginMutation, signUpMutation, logout }
})
