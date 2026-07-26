<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { Eye, EyeOff, LogIn } from 'lucide-vue-next'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const email = ref('admin')
const password = ref('')
const showPassword = ref(false)

const redirect = (route.query.redirect as string) || '/'

async function handleLogin() {
  if (!email.value || !password.value) return
  const ok = await auth.login(email.value, password.value)
  if (ok) {
    router.replace(redirect)
  }
}
</script>

<template>
  <div class="min-h-screen flex items-center justify-center bg-surface-950 px-4">
    <div class="w-full max-w-md">
      <!-- Logo -->
      <div class="text-center mb-8">
        <div class="mx-auto w-12 h-12 rounded-xl bg-brand-500/20 flex items-center justify-center mb-4">
          <div class="w-6 h-6 rounded bg-brand-400" />
        </div>
        <h1 class="text-2xl font-bold text-white">AI Studio 管理后台</h1>
        <p class="text-gray-500 mt-2 text-sm">请输入管理员账号登录</p>
      </div>

      <!-- Form -->
      <form @submit.prevent="handleLogin" class="bg-surface-900 rounded-xl border border-white/10 p-6 space-y-5">
        <!-- Email -->
        <div>
          <label class="block text-sm text-gray-400 mb-1.5">用户名</label>
          <input
            v-model="email"
            type="text"
            required
            placeholder="admin@example.com"
            class="w-full rounded-lg bg-surface-800 border border-white/10 px-3 py-2.5 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-400 transition-colors"
          />
        </div>

        <!-- Password -->
        <div>
          <label class="block text-sm text-gray-400 mb-1.5">密码</label>
          <div class="relative">
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              required
              placeholder="输入密码"
              class="w-full rounded-lg bg-surface-800 border border-white/10 px-3 py-2.5 pr-10 text-sm text-white placeholder-gray-500 outline-none focus:border-brand-400 transition-colors"
            />
            <button
              type="button"
              class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
              @click="showPassword = !showPassword"
            >
              <Eye v-if="!showPassword" class="w-4 h-4" />
              <EyeOff v-else class="w-4 h-4" />
            </button>
          </div>
        </div>

        <!-- Error -->
        <div v-if="auth.error" class="rounded-lg bg-red-500/10 border border-red-500/20 px-3 py-2 text-sm text-red-400">
          {{ auth.error }}
        </div>

        <!-- Submit -->
        <button
          type="submit"
          :disabled="auth.loading"
          class="w-full rounded-lg bg-brand-500 hover:bg-brand-600 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2.5 text-sm flex items-center justify-center gap-2 transition-colors"
        >
          <LogIn class="w-4 h-4" />
          {{ auth.loading ? '登录中...' : '登录' }}
        </button>
      </form>
    </div>
  </div>
</template>
