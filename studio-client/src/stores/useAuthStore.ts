import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import apiClient from '@/api/client'

export interface UserProfile {
  id: string
  email: string
  full_name?: string
  is_active: boolean
  is_superuser: boolean
  avatar_url?: string
}

export const useAuthStore = defineStore('auth', () => {
  // ── State ──
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<UserProfile | null>(null)
  const loading = ref(false)
  const error = ref('')

  // ── Getters ──
  const isAuthenticated = computed(() => !!token.value)
  const userName = computed(() => user.value?.full_name || user.value?.email || '')
  const isSuperuser = computed(() => user.value?.is_superuser ?? false)

  // ── Actions ──

  async function login(username: string, password: string): Promise<boolean> {
    loading.value = true
    error.value = ''

    try {
      // Step 1: Get access token via OAuth2 form login
      const formData = new URLSearchParams()
      formData.append('username', username)
      formData.append('password', password)

      const tokenRes = await apiClient.post('/login/access-token', formData, {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })

      const accessToken: string = tokenRes.data.access_token
      token.value = accessToken
      localStorage.setItem('token', accessToken)

      // Step 2: Fetch user profile
      await fetchProfile()

      return true
    } catch (e: any) {
      const msg = e?.response?.data?.detail
        || e?.message
        || '登录失败，请检查用户名和密码'
      error.value = msg
      token.value = null
      localStorage.removeItem('token')
      user.value = null
      return false
    } finally {
      loading.value = false
    }
  }

  async function fetchProfile(): Promise<UserProfile | null> {
    try {
      const res = await apiClient.get('/users/me')
      user.value = res.data as UserProfile
      return user.value
    } catch {
      // Token might be invalid/expired — clear
      logout()
      return null
    }
  }

  function logout(): void {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
  }

  // Auto-fetch profile on store creation if token exists
  if (token.value && token.value !== 'dev-mode-token') {
    fetchProfile()
  }

  return {
    token,
    user,
    loading,
    error,
    isAuthenticated,
    userName,
    isSuperuser,
    login,
    logout,
    fetchProfile,
  }
})
