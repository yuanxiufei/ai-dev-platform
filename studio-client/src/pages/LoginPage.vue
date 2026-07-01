<template>
  <div class="login-page flex h-screen overflow-hidden">
    <!-- ═════ 左侧：品牌展示区 ═══════ -->
    <div class="brand-panel hidden lg:flex lg:w-[55%] relative items-center justify-center">
      <!-- 动态背景 -->
      <div class="absolute inset-0 pointer-events-none overflow-hidden">
        <div class="orb orb-1" />
        <div class="orb orb-2" />
      </div>

      <!-- 居中内容容器 -->
      <div class="relative z-10 w-full max-w-[480px] px-12 xl:px-16 text-center">
        <!-- Logo -->
        <div class="flex items-center justify-center gap-3 mb-10">
          <div class="logo-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
            </svg>
          </div>
          <div class="text-left">
            <h1 class="text-xl font-bold text-white tracking-tight">CodeBuddy</h1>
            <p class="text-[10px] text-[var(--color-ide-text-dim)] font-medium tracking-wider uppercase">AI Fullstack Platform</p>
          </div>
        </div>

        <!-- 主标语 -->
        <div class="mb-10">
          <h2 class="text-3xl xl:text-[38px] font-bold text-white leading-tight tracking-tight mb-4">
            用自然语言构建
            <br />
            <span class="bg-gradient-to-r from-indigo-300 via-purple-300 to-cyan-300 bg-clip-text text-transparent">全栈应用</span>
          </h2>
          <p class="text-sm text-[var(--color-ide-text-dim)] leading-relaxed max-w-sm mx-auto">
            截图转代码 · AI 对话编程 · 一键部署 — 从想法到上线
          </p>
        </div>

        <!-- 特性卡片：横排 2x2 紧凑网格 -->
        <div class="grid grid-cols-2 gap-3 mb-9 max-w-md mx-auto">
          <div v-for="(feature, i) in features" :key="i"
               class="feature-card group p-3.5 rounded-xl border border-[var(--color-ide-border)] bg-[var(--color-ide-surface-hover)]
                      backdrop-blur-sm transition-all duration-300 hover:bg-[var(--color-ide-surface)] hover:border-[var(--color-ide-accent)]"
               :style="{ animationDelay: `${i * 100}ms` }">
            <div class="feature-icon mb-1.5">{{ feature.icon }}</div>
            <h3 class="text-xs font-semibold text-[var(--color-ide-text)] mb-0.5">{{ feature.title }}</h3>
            <p class="text-[11px] text-[var(--color-ide-text-dim)] leading-snug">{{ feature.desc }}</p>
          </div>
        </div>

        <!-- 统计数据条：一行居中 -->
        <div class="flex items-center justify-center gap-6 mb-7">
          <div v-for="(stat, i) in stats" :key="i" class="flex items-center gap-1.5">
            <span class="text-lg font-bold bg-gradient-to-r from-indigo-300 to-cyan-300 bg-clip-text text-transparent">{{ stat.value }}</span>
            <span class="text-[11px] text-[var(--color-ide-text-dim)]">{{ stat.label }}</span>
          </div>
          <template v-if="i < stats.length - 1"><div class="w-px h-5 bg-white/10" /></template>
        </div>

        <!-- 技术栈标签 -->
        <div class="flex items-center justify-center flex-wrap gap-1.5">
          <span v-for="tech in techStack" :key="tech"
                class="px-2.5 py-1 rounded-full text-[10px] font-medium text-[var(--color-ide-text-dim)] bg-[var(--color-ide-surface-hover)] border border-[var(--color-ide-border)]">
            {{ tech }}
          </span>
        </div>
      </div>
    </div>

    <!-- ═══════ 右侧：登录表单区 ═══════ -->
    <div class="form-panel flex-1 flex flex-col items-center justify-center p-6 sm:p-10 relative">
      <!-- 装饰光晕 (仅右侧可见) -->
      <div class="absolute top-[-20%] right-[-20%] w-[400px] h-[400px] rounded-full blur-[120px] pointer-events-none"
           style="background: rgba(99,102,241,0.06);" />
      <div class="absolute bottom-[-15%] left-[-10%] w-[300px] h-[300px] rounded-full blur-[100px] pointer-events-none"
           style="background: rgba(56,189,248,0.04);" />

      <!-- 移动端 Logo -->
      <div class="lg:hidden flex items-center gap-3 mb-10">
        <div class="logo-icon-sm">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="w-5 h-5">
            <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
          </svg>
        </div>
        <span class="text-lg font-bold text-[var(--color-ide-text-bright)]">CodeBuddy</span>
      </div>

      <!-- 表单容器 -->
      <div class="w-full max-w-[380px] relative z-10">
        <!-- 标题区 -->
        <div class="mb-8">
          <h2 class="text-2xl font-bold text-[var(--color-ide-text-bright)] mb-2">欢迎回来</h2>
          <p class="text-sm text-[var(--color-ide-text-dim)]">登录以继续使用 CodeBuddy IDE Studio</p>
        </div>

        <!-- 登录表单 -->
        <form @submit.prevent="login" class="space-y-5">
          <!-- 邮箱 -->
          <div class="field-group">
            <label class="field-label">邮箱地址</label>
            <div class="input-wrapper">
              <input
                v-model="username"
                type="email"
                autocomplete="email"
                placeholder="name@company.com"
                class="login-input"
              />
              <div class="input-icon">
                <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" stroke-linejoin="round" d="M16 12a4 4 0 10-8 0 4 4 0 008 0zm0 0v1.5a2.5 2.5 0 005 0V12a9 9 0 10-9 9m4.5-1.206a8.959 8.959 0 01-4.5 1.207"/></svg>
              </div>
            </div>
          </div>

          <!-- 密码 -->
          <div class="field-group">
            <label class="field-label">密码</label>
            <div class="input-wrapper">
              <input
                v-model="password"
                :type="showPassword ? 'text' : 'password'"
                autocomplete="current-password"
                placeholder="••••••••"
                class="login-input pr-11"
              />
              <button type="button" @click="showPassword = !showPassword" tabindex="-1"
                      class="toggle-btn" :class="{ active: showPassword }">
                <svg v-if="!showPassword" width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                <svg v-else width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.7"><path stroke-linecap="round" stroke-linejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"/></svg>
              </button>
            </div>
          </div>

          <!-- 记住我 & 忘记密码 -->
          <div class="flex items-center justify-between -mt-1">
            <label class="flex items-center gap-2 cursor-pointer group/select">
              <div class="checkbox-wrap">
                <input type="checkbox" v-model="rememberMe" class="sr-only peer" />
                <div class="checkbox-box peer-checked:border-indigo-500 peer-checked:bg-indigo-500/20">
                  <svg class="check-icon" width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="3"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>
                </div>
              </div>
              <span class="text-xs text-[var(--color-ide-text-dim)] group-hover/select:text-[var(--color-ide-text)] transition-colors">记住登录状态</span>
            </label>
            <a href="#" class="text-xs text-indigo-400 hover:text-indigo-300 transition-colors font-medium">忘记密码？</a>
          </div>

          <!-- 提交按钮 -->
          <button
            type="submit"
            :disabled="loading"
            class="submit-btn"
          >
            <span v-if="loading" class="flex items-center justify-center gap-2.5">
              <svg class="animate-spin h-[18px] w-[18px]" fill="none" viewBox="0 0 24 24">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              正在验证...
            </span>
            <span v-else>登 录</span>
          </button>

          <!-- 错误提示 -->
          <transition name="slide-fade">
            <div v-if="error" class="error-banner">
              <svg width="16" height="16" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8" class="shrink-0 mt-0.5">
                <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
              </svg>
              <span>{{ error }}</span>
            </div>
          </transition>
        </form>

        <!-- 分割线 -->
        <div class="divider my-7">
          <span class="divider-text">或继续使用</span>
        </div>

        <!-- 第三方登录 -->
        <div class="space-y-3">
          <button v-for="provider in oauthProviders" :key="provider.name"
                  class="oauth-btn group" @click.prevent>
            <component :is="'span'" v-html="provider.icon" class="shrink-0" />
            <span>使用 {{ provider.name }} 登录</span>
          </button>
        </div>

        <!-- 注册引导 -->
        <p class="text-center text-xs text-[var(--code-ide-text-dim)] mt-8 pt-6 border-t border-[var(--color-ide-border)]">
          还没有账号？
          <router-link to="#" class="text-indigo-400 hover:text-indigo-300 font-semibold transition-colors ml-1">申请试用</router-link>
        </p>

        <!-- 底部部署信息 -->
        <p class="text-center text-[10px] text-[var(--color-ide-text-dim)] opacity-30 mt-4 leading-relaxed">
          本地部署 · Docker + GPU · Port {{ port }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const username = ref('admin@example.com')
const password = ref('changethis')
const loading = ref(false)
const error = ref('')
const showPassword = ref(false)
const rememberMe = ref(true)
const port = ref(18000)

onMounted(() => {
  // 自动检测端口
  const host = window.location.port
  if (host) port.value = parseInt(host)
})

async function login() {
  loading.value = true
  error.value = ''
  // 前端直通：模拟登录，不走后端（样式开发阶段）
  await new Promise(r => setTimeout(r, 600))
  localStorage.setItem('token', 'dev-mode-token')
  router.push('/chat')
}

/* ═════ 数据定义 ════ */

const features = [
  { icon: '🎨', title: '截图转代码', desc: 'UI 设计图直接生成可运行代码' },
  { icon: '⚡', title: 'AI 对话编程', desc: '自然语言描述即可生成全栈项目' },
  { icon: '🎬', title: 'AI 视频生成', desc: '文字描述一键生成高质量视频' },
  { icon: '🚀', title: '一键部署', desc: 'Docker 容器化自动部署上线' },
]

const stats = [
  { value: '59+', label: '闭环测试通过' },
  { value: '4层', label: '回退链保障' },
  { value: '0依赖', label: '完全自主实现' },
]

const techStack = ['Vue 3', 'FastAPI', 'Monaco', 'Tauri', 'SQLite', 'Ollama']

const oauthProviders = [
  {
    name: 'GitHub',
    icon: '<svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor"><path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/></svg>',
  },
  {
    name: 'Google',
    icon: '<svg class="w-5 h-5" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>',
  },
]
</script>

<style scoped>
/* ═════ 页面布局 ═════ */
.login-page {
  background: #0b0d14;
}
.brand-panel {
  background: linear-gradient(165deg, #0f1020 0%, #13122b 40%, #0e1030 70%, #0c0e1f 100%);
}

/* ═════ 动态光球 ═════ */
.orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
  animation: float 14s ease-in-out infinite;
}
.orb-1 {
  width: 420px; height: 420px;
  top: -8%; left: -6%;
  background: radial-gradient(circle, rgba(99,102,241,.16) 0%, transparent 70%);
}
.orb-2 {
  width: 320px; height: 320px;
  bottom: 8%; right: -4%;
  background: radial-gradient(circle, rgba(56,189,248,.10) 0%, transparent 70%);
  animation-delay: -7s;
}
@keyframes float {
  0%, 100% { transform: translate(0, 0); }
  50%      { transform: translate(18px, -20px); }
}

/* ═════ Logo ═════ */
.logo-icon {
  width: 44px; height: 44px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 13px;
  background: linear-gradient(135deg, rgba(99,102,241,.25), rgba(168,85,247,.15));
  border: 1px solid rgba(99,102,241,.2);
  color: #a5b4fc;
}
.logo-icon svg {
  width: 22px; height: 22px;
}
.logo-icon-sm {
  width: 34px; height: 34px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 10px;
  background: linear-gradient(135deg, rgba(99,102,241,.2), rgba(168,85,247,.12));
  border: 1px solid rgba(99,102,241,.2);
  color: #a5b4fc;
}

/* ═════ 特性卡片 ═════ */
.feature-card {
  animation: fadeSlideUp 0.6s ease both;
}
.feature-icon {
  font-size: 22px;
  line-height: 1;
}
@keyframes fadeSlideUp {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* ═════ 表单样式 ═════ */
.form-panel {
  background: linear-gradient(175deg, #0e1018 0%, #12131f 60%, #0e1018 100%);
}

.field-label {
  display: block;
  font-size: 12.5px;
  font-weight: 600;
  margin-bottom: 7px;
  color: var(--color-ide-text-dim);
  letter-spacing: 0.01em;
}

.input-wrapper {
  position: relative;
}

.login-input {
  width: 100%;
  padding: 11px 39px 11px 13px;
  padding-left: 13px;
  font-size: 13.5px;
  border-radius: 11px;
  outline: none;
  transition: all 0.2s ease;
  background: rgba(15, 17, 27, 0.75);
  border: 1.2px solid rgba(65, 68, 88, 0.4);
  color: var(--color-ide-text);
}
.login-input::placeholder { color: rgba(144, 143, 160, 0.4); }
.login-input:hover { border-color: rgba(99, 102, 241, 0.3); }
.login-input:focus {
  border-color: rgba(99, 102, 241, 0.55);
  box-shadow: 0 0 0 3.5px rgba(99, 102, 241, 0.08), 0 1px 3px rgba(0,0,0,0.1) inset;
  background: rgba(15, 17, 27, 0.9);
}

.input-icon {
  position: absolute;
  right: 12px;
  top: 50%; transform: translateY(-50%);
  color: var(--color-ide-text-dim);
  pointer-events: none;
  opacity: 0.5;
}

.toggle-btn {
  position: absolute;
  right: 10px;
  top: 50%; transform: translateY(-50%);
  padding: 4px;
  color: var(--color-ide-text-dim);
  opacity: 0.45;
  border-radius: 6px;
  transition: all 0.15s ease;
}
.toggle-btn:hover,
.toggle-btn.active { opacity: 0.85; color: var(--color-ide-text); }

/* Checkbox */
.checkbox-wrap {
  position: relative;
}
.checkbox-box {
  width: 16px; height: 16px;
  border-radius: 4.5px;
  border: 1.5px solid rgba(65, 68, 88, 0.55);
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s ease;
  cursor: pointer;
}
.checkbox-box:hover { border-color: rgba(99, 102, 241, 0.5); }
.check-icon { color: transparent; transition: color 0.15s ease; }
.peer:checked ~ .checkbox-box .check-icon { color: white; }

/* Submit button */
.submit-btn {
  width: 100%;
  padding: 11px 0;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.02em;
  border-radius: 11px;
  border: none;
  cursor: pointer;
  color: #fff;
  background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #7c3aed 100%);
  background-size: 200% 200%;
  box-shadow: 0 4px 20px rgba(99, 102, 241, 0.3), 0 1px 3px rgba(0,0,0,0.2);
  transition: all 0.25s ease;
  position: relative;
  overflow: hidden;
}
.submit-btn::before {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255,255,255,0.15) 0%, transparent 50%);
  opacity: 0;
  transition: opacity 0.25s;
}
.submit-btn:hover:not(:disabled) {
  background-position: 100% 0;
  box-shadow: 0 6px 28px rgba(99, 102, 241, 0.4), 0 2px 4px rgba(0,0,0,0.2);
  transform: translateY(-1px);
}
.submit-btn:hover:not(:disabled)::before { opacity: 1; }
.submit-btn:active:not(:disabled) { transform: translateY(0); }
.submit-btn:disabled { opacity: 0.5; cursor: not-allowed; }

/* Error banner */
.error-banner {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 12.5px;
  color: #fca5a5;
  background: rgba(220, 38, 38, 0.07);
  border: 1px solid rgba(220, 38, 38, 0.12);
  line-height: 1.5;
}
.slide-fade-enter-active { transition: all 0.25s ease; }
.slide-fade-leave-active { transition: all 0.15s ease; }
.slide-fade-enter-from { opacity: 0; transform: translateY(-8px); }
.slide-fade-leave-to { opacity: 0; transform: translateY(-4px); }

/* Divider */
.divider {
  position: relative;
  display: flex;
  align-items: center;
}
.divider::before, .divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(65,68,88,0.3), transparent);
}
.divider-text {
  padding: 0 16px;
  font-size: 11.5px;
  color: var(--color-ide-text-dim);
  opacity: 0.5;
  white-space: nowrap;
}

/* OAuth buttons */
.oauth-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  width: 100%;
  padding: 10px 0;
  font-size: 13px;
  font-weight: 500;
  border-radius: 11px;
  border: 1.2px solid rgba(65, 68, 88, 0.3);
  background: rgba(15, 17, 27, 0.5);
  color: var(--color-ide-text);
  cursor: pointer;
  transition: all 0.2s ease;
}
.oauth-btn:hover {
  background: rgba(15, 17, 27, 0.85);
  border-color: rgba(99, 102, 241, 0.25);
  color: var(--color-ide-text-bright);
}
</style>
