<template>
  <div class="settings-section">
    <div class="section-title">账户信息</div>

    <SettingRow label="用户名" hint="当前登录的邮箱地址">
      <span class="value-text">{{ authStore.user?.email || '—' }}</span>
    </SettingRow>

    <SettingRow label="超级管理员" hint="拥有系统所有权限">
      <span :class="authStore.isSuperuser ? 'badge badge-super' : 'badge badge-normal'">
        {{ authStore.isSuperuser ? '是' : '否' }}
      </span>
    </SettingRow>

    <SettingRow label="账户状态">
      <span :class="authStore.user?.is_active ? 'badge badge-active' : 'badge badge-inactive'">
        {{ authStore.user?.is_active ? '正常' : '已禁用' }}
      </span>
    </SettingRow>

    <div class="section-title">安全设置</div>

    <SettingRow label="修改密码" hint="至少 8 个字符，包含字母和数字">
      <button class="btn btn-primary" @click="showPasswordModal = true">修改</button>
    </SettingRow>

    <!-- Password Modal -->
    <Teleport to="body">
      <div v-if="showPasswordModal" class="modal-overlay" @click.self="showPasswordModal = false">
        <div class="modal-card">
          <h3 class="modal-title">修改密码</h3>
          <form @submit.prevent="changePassword" class="modal-body">
            <div class="field">
              <label>当前密码</label>
              <input v-model="currentPassword" type="password" class="input" placeholder="输入当前密码" />
            </div>
            <div class="field">
              <label>新密码</label>
              <input v-model="newPassword" type="password" class="input" placeholder="至少 8 个字符" />
            </div>
            <div class="field">
              <label>确认新密码</label>
              <input v-model="confirmPassword" type="password" class="input" placeholder="再次输入新密码" />
            </div>
            <p v-if="pwdError" class="error-text">{{ pwdError }}</p>
            <div class="modal-actions">
              <button type="button" class="btn btn-ghost" @click="showPasswordModal = false">取消</button>
              <button type="submit" class="btn btn-primary" :disabled="pwdLoading">
                {{ pwdLoading ? '保存中...' : '确认修改' }}
              </button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useAuthStore } from '@/stores/useAuthStore'
import SettingRow from './SettingRow.vue'
import apiClient from '@/api/client'

const authStore = useAuthStore()

const showPasswordModal = ref(false)
const currentPassword = ref('')
const newPassword = ref('')
const confirmPassword = ref('')
const pwdLoading = ref(false)
const pwdError = ref('')

async function changePassword() {
  pwdError.value = ''
  if (newPassword.value.length < 8) {
    pwdError.value = '密码至少 8 个字符'
    return
  }
  if (newPassword.value !== confirmPassword.value) {
    pwdError.value = '两次密码不一致'
    return
  }
  pwdLoading.value = true
  try {
    await apiClient.patch('/users/me/password', {
      current_password: currentPassword.value,
      new_password: newPassword.value,
    })
    showPasswordModal.value = false
    currentPassword.value = ''
    newPassword.value = ''
    confirmPassword.value = ''
  } catch (e: any) {
    pwdError.value = e?.response?.data?.detail || '修改失败'
  } finally {
    pwdLoading.value = false
  }
}
</script>

<style scoped>
.section-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-ide-text-dim);
  padding: 16px 0 8px;
}
.section-title:first-child { padding-top: 0; }
.value-text { font-size: 13px; color: var(--color-ide-text); }
.badge {
  font-size: 11.5px;
  padding: 2px 10px;
  border-radius: 3px;
  font-weight: 600;
}
.badge-super { background: rgba(0,122,204,0.15); color: var(--color-ide-accent); }
.badge-normal { background: rgba(204,204,204,0.1); color: var(--color-ide-text-dim); }
.badge-active { background: rgba(78,201,176,0.15); color: var(--color-ide-success); }
.badge-inactive { background: rgba(244,135,113,0.15); color: var(--color-ide-error); }
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center;
  z-index: 300;
}
.modal-card {
  background: var(--color-ide-surface);
  border: 1px solid var(--color-ide-border);
  border-radius: 6px;
  width: 400px; max-width: 90vw;
  padding: 24px;
  box-shadow: var(--shadow-lg);
}
.modal-title { font-size: 16px; color: var(--color-ide-text); margin-bottom: 20px; }
.modal-body { display: flex; flex-direction: column; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field label { font-size: 12px; color: var(--color-ide-text-dim); }
.input {
  padding: 8px 12px; font-size: 13px;
  background: var(--color-chat-input-bg); border: 1px solid var(--color-ide-border);
  border-radius: 3px; color: var(--color-ide-text); outline: none;
}
.input:focus { border-color: var(--color-ide-border-focus); }
.error-text { font-size: 12px; color: var(--color-ide-error); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
.btn {
  padding: 6px 16px; font-size: 12px; border-radius: 3px; border: none; cursor: pointer;
  font-weight: 600; transition: background 0.1s;
}
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-primary:hover { background: var(--color-ide-accent-hover); }
.btn-primary:disabled { opacity: 0.5; }
.btn-ghost { background: transparent; color: var(--color-ide-text); }
.btn-ghost:hover { background: rgba(255,255,255,0.06); }
</style>
