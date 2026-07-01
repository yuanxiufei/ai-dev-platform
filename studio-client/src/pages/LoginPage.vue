<template>
  <div class="login-page min-h-screen flex items-center justify-center p-4 relative overflow-hidden">
    <!-- 装饰背景 — IDE 主题色 -->
    <div class="absolute inset-0 pointer-events-none">
      <div class="absolute -top-40 -right-40 w-[420px] h-[420px] rounded-full blur-[120px]" style="background: rgba(192,193,255,0.07);" />
      <div class="absolute -bottom-40 -left-40 w-[360px] h-[360px] rounded-full blur-[120px]" style="background: rgba(56,189,248,0.05);" />
      <!-- 网格背景 -->
      <div class="absolute inset-0 bg-grid" />
    </div>

    <!-- 主卡片 -->
    <div class="relative w-full max-w-md z-10">
      <!-- Logo/标题 -->
      <div class="text-center mb-10">
        <div class="inline-flex items-center justify-center w-16 h-16 rounded-2xl mb-5 shadow-lg" style="background: linear-gradient(135deg, rgba(192,193,255,0.25), rgba(192,193,255,0.08)); border: 1px solid rgba(192,193,255,0.18);">
          <svg class="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="var(--color-ide-accent)" stroke-width="1.8">
            <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <h1 class="text-2xl font-bold mb-1.5 text-[var(--color-ide-text-bright)]">AI Dev Platform</h1>
        <p class="text-xs text-[var(--color-ide-text-dim)]">CodeBuddy IDE Studio</p>
      </div>

      <!-- 表单卡片 -->
      <form @submit.prevent="login" class="space-y-6 p-8 rounded-2xl border border-solid backdrop-blur-xl"
        style="background: rgba(28,31,42,0.65); border-color: rgba(70,69,84,0.45); box-shadow: 0 20px 60px rgba(0,0,0,0.35);">
        <div>
          <label class="block text-[13px] font-medium mb-2.5 text-[var(--color-ide-text-dim)]">邮箱</label>
          <div class="relative">
            <div class="absolute left-3.5 top-1/2 -translate-y-1/2 flex items-center pointer-events-none text-[var(--color-ide-text-dim)]">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
                <path stroke-linecap="round" stroke-linejoin="round" d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9m4.5-1.206a8.959 8.959 0 01-4.5 1.207" />
              </svg>
            </div>
            <input
              v-model="username"
              type="text"
              placeholder="admin@example.com"
              class="login-input w-full pl-11 pr-4 py-3.5 text-sm rounded-xl outline-none transition-all duration-150"
            />
          </div>
        </div>

        <div>
          <label class="block text-[13px] font-medium mb-2.5 text-[var(--color-ide-text-dim)]">密码</label>
          <div class="relative">
            <div class="absolute left-3.5 top-1/2 -translate-y-1/2 flex items-center pointer-events-none text-[var(--color-ide-text-dim)]">
              <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
                <path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              placeholder="••••••••"
              class="login-input w-full pl-11 pr-12 py-3.5 text-sm rounded-xl outline-none transition-all duration-150"
            />
            <button type="button" @click="showPassword = !showPassword" class="absolute right-3.5 top-1/2 -translate-y-1/2 btn-ghost p-1 text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]">
              <svg v-if="!showPassword" class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
                <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
              </svg>
              <svg v-else class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8">
                <path stroke-linecap="round" stroke-linejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
              </svg>
            </button>
          </div>
        </div>

        <button
          type="submit"
          :disabled="loading"
          class="w-full py-3 rounded-xl text-[14px] font-semibold transition-all duration-200 disabled:opacity-40 disabled:pointer-events-none active:scale-[0.98]"
          style="background: linear-gradient(135deg, #8b7bd6, #6366f1); color: #fff; box-shadow: 0 4px 20px rgba(99,102,241,0.25);"
        >
          <span v-if="loading" class="flex items-center justify-center gap-2">
            <svg class="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            登录中...
          </span>
          <span v-else>登 录</span>
        </button>

        <p v-if="error" class="text-[13px] text-center px-3 py-2 rounded-lg" style="color: var(--color-ide-error); background: rgba(224,108,117,0.08);">{{ error }}</p>
      </form>

      <!-- 底部信息 -->
      <p class="text-center text-[11px] mt-6 text-[var(--color-ide-text-dim)] opacity-60">
        本地部署 · Docker + GPU · 端口 18000
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const username = ref('admin@example.com')
const password = ref('changethis')
const loading = ref(false)
const error = ref('')
const showPassword = ref(false)

async function login() {
  loading.value = true
  error.value = ''
  try {
    const form = new URLSearchParams()
    form.append('username', username.value)
    form.append('password', password.value)

    const res = await fetch('/api/v1/login/access-token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: form,
    })

    if (!res.ok) throw new Error('邮箱或密码错误')

    const data = await res.json()
    localStorage.setItem('token', data.access_token)
    router.push('/chat')
  } catch (e: any) {
    error.value = e.message || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  background: linear-gradient(165deg, #0f131d 0%, #131726 50%, #0f131d 100%);
}
.login-input {
  background: rgba(15, 19, 29, 0.7);
  border: 1px solid var(--color-ide-border);
  color: var(--color-ide-text);
}
.login-input::placeholder {
  color: rgba(144, 143, 160, 0.45);
}
.login-input:focus {
  border-color: var(--color-ide-border-focus);
  box-shadow: 0 0 0 3px rgba(192, 193, 255, 0.08);
}
</style>
