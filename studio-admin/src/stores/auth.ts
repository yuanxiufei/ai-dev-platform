import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { loginWithPassword } from '@/api/auth'

const TOKEN_KEY = 'token'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) || '')
  const error = ref<string>('')
  const loading = ref(false)

  const isLoggedIn = computed(() => !!token.value)

  async function login(email: string, password: string): Promise<boolean> {
    loading.value = true
    error.value = ''
    try {
      const res = await loginWithPassword(email, password)
      token.value = res.access_token
      localStorage.setItem(TOKEN_KEY, res.access_token)
      return true
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      error.value = typeof detail === 'string' ? detail : '登录失败，请检查邮箱和密码'
      return false
    } finally {
      loading.value = false
    }
  }

  function logout() {
    token.value = ''
    localStorage.removeItem(TOKEN_KEY)
  }

  return { token, error, loading, isLoggedIn, login, logout }
})
