<script setup lang="ts">
/**
 * 护栏管理页面 — 工具调用授权护栏管理
 */
import { ref, reactive, onMounted } from "vue"
import { Shield, Play, Settings, AlertTriangle, Check, X, Info } from "lucide-vue-next"
import { checkToolCall, getGuardrailConfig } from "@/api/guardrails"
import type { GuardrailConfig } from "@/api/guardrails"

/* ── 状态 ─────────────────────────────── */
const activeTab = ref<"check" | "config">("check")
const loading = ref(false)
const config = ref<GuardrailConfig | null>(null)
const configLoading = ref(false)
const error = ref("")

/* 检查表单 */
const checkForm = reactive({
  tool_name: "execute_command",
  tool_params_str: '{"command": "ls -la"}',
})

const checkResult = ref<any>(null)
const checkError = ref("")

/* ── 方法 ─────────────────────────────── */
async function loadConfig() {
  configLoading.value = true
  try {
    const res = await getGuardrailConfig()
    config.value = res.data
  } catch (e: any) {
    console.error("Failed to load guardrail config:", e)
  } finally {
    configLoading.value = false
  }
}

async function runCheck() {
  checkError.value = ""
  checkResult.value = null
  loading.value = true

  let params: Record<string, string> = {}
  try {
    params = JSON.parse(checkForm.tool_params_str)
  } catch {
    checkError.value = "参数 JSON 格式错误"
    loading.value = false
    return
  }

  try {
    const res = await checkToolCall({ tool_name: checkForm.tool_name, tool_params: params })
    checkResult.value = res.data
  } catch (e: any) {
    checkError.value = e.response?.data?.detail || e.message || "检查请求失败"
  } finally {
    loading.value = false
  }
}

/* ── 辅助 ─────────────────────────────── */
function levelBadgeClass(level: string) {
  switch (level) {
    case "block":
      return "g-level-block"
    case "warn":
      return "g-level-warn"
    case "allow":
      return "g-level-allow"
    default:
      return ""
  }
}

function levelLabel(level: string) {
  const map: Record<string, string> = { block: "拦截", warn: "警告", allow: "允许" }
  return map[level] || level
}

/* ── 预设快捷测试 ─────────────────────── */
const presets = [
  { label: "安全命令", tool: "read_file", params: '{"path": "/etc/hosts"}' },
  { label: "危险命令", tool: "execute_command", params: '{"command": "rm -rf /"}' },
  { label: "网络请求", tool: "web_fetch", params: '{"url": "https://localhost/test"}' },
  { label: "文件写入", tool: "write_to_file", params: '{"path": "/tmp/test.txt"}' },
]

function usePreset(p: (typeof presets)[0]) {
  checkForm.tool_name = p.tool
  checkForm.tool_params_str = p.params
  checkResult.value = null
  checkError.value = ""
}

onMounted(loadConfig)
</script>

<template>
  <div class="g-container">
    <div class="g-header">
      <div class="g-header-left">
        <Shield class="g-header-icon" :size="22" />
        <h1 class="g-header-title">工具护栏</h1>
        <span class="g-header-sub">工具调用授权管理</span>
      </div>
      <div class="g-tabs">
        <button :class="['g-tab', { active: activeTab === 'check' }]" @click="activeTab = 'check'">
          <Play :size="14" /> 安全检查
        </button>
        <button
          :class="['g-tab', { active: activeTab === 'config' }]"
          @click="activeTab = 'config'"
        >
          <Settings :size="14" /> 全局配置
        </button>
      </div>
    </div>

    <!-- 安全检查 Tab -->
    <div v-if="activeTab === 'check'" class="g-content">
      <!-- 预设快捷测试 -->
      <div class="g-presets">
        <span class="g-presets-label">快捷测试：</span>
        <button
          v-for="p in presets"
          :key="p.label"
          class="g-preset-btn"
          @click="usePreset(p)"
        >
          {{ p.label }}
        </button>
      </div>

      <div class="g-check-grid">
        <div class="g-check-form">
          <label class="g-field">
            <span class="g-field-label">工具名称</span>
            <select v-model="checkForm.tool_name" class="g-input g-select">
              <option value="read_file">read_file</option>
              <option value="write_to_file">write_to_file</option>
              <option value="execute_command">execute_command</option>
              <option value="delete_file">delete_file</option>
              <option value="web_fetch">web_fetch</option>
              <option value="web_search">web_search</option>
              <option value="replace_in_file">replace_in_file</option>
            </select>
          </label>

          <label class="g-field">
            <span class="g-field-label">工具参数 (JSON)</span>
            <textarea
              v-model="checkForm.tool_params_str"
              class="g-input g-textarea"
              rows="4"
              placeholder='{"key": "value"}'
            />
          </label>

          <div class="g-field-actions">
            <button class="g-btn g-btn-primary" :disabled="loading" @click="runCheck">
              <Shield :size="15" />
              <span>{{ loading ? "检查中..." : "执行安全检查" }}</span>
            </button>
          </div>

          <div v-if="checkError" class="g-error-msg">
            <AlertTriangle :size="14" /> {{ checkError }}
          </div>
        </div>

        <!-- 检查结果 -->
        <div v-if="checkResult" class="g-check-result">
          <h3 class="g-result-title">检查结果</h3>

          <div class="g-result-level">
            <span>裁定等级：</span>
            <span :class="['g-level-badge', levelBadgeClass(checkResult.level)]">
              {{ levelLabel(checkResult.level) }}
            </span>
          </div>

          <div class="g-result-item">
            <span class="g-result-label">原因：</span>
            <span>{{ checkResult.reason }}</span>
          </div>

          <div v-if="checkResult.blocked_params.length" class="g-result-item">
            <span class="g-result-label">拦截参数：</span>
            <div class="g-param-list">
              <span v-for="p in checkResult.blocked_params" :key="p" class="g-param-tag g-tag-danger">
                {{ p }}
              </span>
            </div>
          </div>

          <div v-if="checkResult.suggestions.length" class="g-result-item">
            <span class="g-result-label">建议：</span>
            <ul class="g-suggestions">
              <li v-for="s in checkResult.suggestions" :key="s">{{ s }}</li>
            </ul>
          </div>
        </div>
      </div>
    </div>

    <!-- 全局配置 Tab -->
    <div v-if="activeTab === 'config'" class="g-content">
      <div v-if="configLoading" class="g-loading">
        <Info :size="14" /> 加载配置中...
      </div>
      <div v-else-if="config" class="g-config-grid">
        <!-- 开关 -->
        <div class="g-config-card">
          <div class="g-config-header">
            <span class="g-config-label">护栏状态</span>
            <span :class="['g-status-dot', config.enabled ? 'on' : 'off']" />
            {{ config.enabled ? "已启用" : "已禁用" }}
          </div>
          <div class="g-config-item">
            <span class="g-config-key">默认等级</span>
            <span :class="['g-level-badge', levelBadgeClass(config.default_level)]">
              {{ levelLabel(config.default_level) }}
            </span>
          </div>
        </div>

        <!-- 限制参数 -->
        <div class="g-config-card">
          <h4 class="g-config-title">系统限制</h4>
          <div class="g-config-item">
            <span class="g-config-key">最大文件大小</span>
            <span class="g-config-val">{{ config.max_file_size_mb }} MB</span>
          </div>
          <div class="g-config-item">
            <span class="g-config-key">最大命令长度</span>
            <span class="g-config-val">{{ config.max_command_length }} 字符</span>
          </div>
        </div>

        <!-- 文件路径白名单 -->
        <div class="g-config-card">
          <h4 class="g-config-title">文件路径白名单</h4>
          <div v-if="config.file_path_whitelist.length" class="g-config-tags">
            <span v-for="p in config.file_path_whitelist" :key="p" class="g-tag g-tag-safe">
              <Check :size="12" /> {{ p }}
            </span>
          </div>
          <span v-else class="g-empty">无</span>
        </div>

        <!-- 文件路径黑名单 -->
        <div class="g-config-card">
          <h4 class="g-config-title">文件路径黑名单</h4>
          <div v-if="config.file_path_blacklist.length" class="g-config-tags">
            <span v-for="p in config.file_path_blacklist" :key="p" class="g-tag g-tag-danger">
              <X :size="12" /> {{ p }}
            </span>
          </div>
          <span v-else class="g-empty">无</span>
        </div>

        <!-- 敏感命令 -->
        <div class="g-config-card">
          <h4 class="g-config-title">敏感命令</h4>
          <div v-if="config.sensitive_commands.length" class="g-config-tags">
            <span
              v-for="c in config.sensitive_commands"
              :key="c"
              class="g-tag g-tag-warn"
            >
              <AlertTriangle :size="12" /> {{ c }}
            </span>
          </div>
          <span v-else class="g-empty">无</span>
        </div>

        <!-- 拦截域名 -->
        <div class="g-config-card">
          <h4 class="g-config-title">拦截域名</h4>
          <div v-if="config.blocked_domains.length" class="g-config-tags">
            <span
              v-for="d in config.blocked_domains"
              :key="d"
              class="g-tag g-tag-danger"
            >
              {{ d }}
            </span>
          </div>
          <span v-else class="g-empty">无</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── 布局 ─────────────────────────────── */
.g-container {
  padding: 24px;
  max-width: 1100px;
  margin: 0 auto;
}

.g-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 12px;
}

.g-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.g-header-icon {
  color: var(--color-ide-accent, #a855f7);
}

.g-header-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-ide-fg, #e2e8f0);
  margin: 0;
}

.g-header-sub {
  font-size: 13px;
  color: var(--color-ide-fg-secondary, #94a3b8);
}

.g-tabs {
  display: flex;
  gap: 4px;
  background: var(--color-ide-bg-secondary, #1e293b);
  border-radius: 8px;
  padding: 3px;
}

.g-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--color-ide-fg-secondary, #94a3b8);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.g-tab:hover {
  color: var(--color-ide-fg, #e2e8f0);
}

.g-tab.active {
  background: var(--color-ide-bg-primary, #0f172a);
  color: var(--color-ide-fg, #e2e8f0);
}

/* ── 内容 ─────────────────────────────── */
.g-content {
  animation: g-fade 0.2s ease;
}

@keyframes g-fade {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ── 预设 ─────────────────────────────── */
.g-presets {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}

.g-presets-label {
  font-size: 12px;
  color: var(--color-ide-fg-secondary, #94a3b8);
}

.g-preset-btn {
  padding: 4px 12px;
  border: 1px solid var(--color-ide-border, #334155);
  border-radius: 14px;
  background: var(--color-ide-bg-secondary, #1e293b);
  color: var(--color-ide-fg-secondary, #94a3b8);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.g-preset-btn:hover {
  border-color: var(--color-ide-accent, #a855f7);
  color: var(--color-ide-accent, #a855f7);
}

/* ── 表单 ─────────────────────────────── */
.g-check-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}

@media (max-width: 800px) {
  .g-check-grid {
    grid-template-columns: 1fr;
  }
}

.g-check-form {
  background: var(--color-ide-bg-secondary, #1e293b);
  border: 1px solid var(--color-ide-border, #334155);
  border-radius: 10px;
  padding: 20px;
}

.g-field {
  display: block;
  margin-bottom: 16px;
}

.g-field-label {
  display: block;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-ide-fg-secondary, #94a3b8);
  margin-bottom: 6px;
}

.g-input {
  width: 100%;
  padding: 9px 12px;
  border: 1px solid var(--color-ide-border, #334155);
  border-radius: 7px;
  background: var(--color-ide-bg-primary, #0f172a);
  color: var(--color-ide-fg, #e2e8f0);
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
  font-family: inherit;
}

.g-input:focus {
  border-color: var(--color-ide-accent, #a855f7);
}

.g-select {
  cursor: pointer;
}

.g-textarea {
  resize: vertical;
  min-height: 80px;
  font-family: "JetBrains Mono", "Fira Code", monospace;
}

.g-field-actions {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}

.g-btn {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 9px 18px;
  border: none;
  border-radius: 7px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}

.g-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.g-btn-primary {
  background: var(--color-ide-accent, #a855f7);
  color: #fff;
}

.g-btn-primary:hover:not(:disabled) {
  filter: brightness(1.1);
}

.g-error-msg {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 12px;
  padding: 8px 12px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 6px;
  color: #ef4444;
  font-size: 12px;
}

/* ── 检查结果 ────────────────────────── */
.g-check-result {
  background: var(--color-ide-bg-secondary, #1e293b);
  border: 1px solid var(--color-ide-border, #334155);
  border-radius: 10px;
  padding: 20px;
}

.g-result-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-ide-fg, #e2e8f0);
  margin: 0 0 16px 0;
}

.g-result-level {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--color-ide-fg-secondary, #94a3b8);
}

.g-level-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 600;
}

.g-level-block {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.g-level-warn {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.g-level-allow {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.g-result-item {
  margin-bottom: 10px;
  font-size: 13px;
  color: var(--color-ide-fg, #e2e8f0);
}

.g-result-label {
  font-size: 12px;
  color: var(--color-ide-fg-secondary, #94a3b8);
  margin-right: 4px;
}

.g-param-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.g-param-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
  font-family: monospace;
}

.g-suggestions {
  list-style: disc;
  padding-left: 18px;
  margin: 4px 0 0 0;
  font-size: 12px;
  color: var(--color-ide-fg-secondary, #94a3b8);
}

.g-suggestions li {
  margin-bottom: 2px;
}

/* ── 配置 ─────────────────────────────── */
.g-loading {
  display: flex;
  align-items: center;
  gap: 6px;
  color: var(--color-ide-fg-secondary, #94a3b8);
  font-size: 13px;
  padding: 40px 0;
}

.g-config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.g-config-card {
  background: var(--color-ide-bg-secondary, #1e293b);
  border: 1px solid var(--color-ide-border, #334155);
  border-radius: 10px;
  padding: 16px;
}

.g-config-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-ide-fg, #e2e8f0);
  margin-bottom: 12px;
}

.g-config-label {
  flex: 1;
}

.g-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  display: inline-block;
}

.g-status-dot.on {
  background: #22c55e;
  box-shadow: 0 0 6px rgba(34, 197, 94, 0.4);
}

.g-status-dot.off {
  background: #ef4444;
  box-shadow: 0 0 6px rgba(239, 68, 68, 0.4);
}

.g-config-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-ide-fg, #e2e8f0);
  margin: 0 0 10px 0;
}

.g-config-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  font-size: 13px;
}

.g-config-key {
  color: var(--color-ide-fg-secondary, #94a3b8);
}

.g-config-val {
  color: var(--color-ide-fg, #e2e8f0);
  font-weight: 500;
  font-family: monospace;
}

.g-config-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.g-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 10px;
  border-radius: 14px;
  font-size: 12px;
}

.g-tag-safe {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
}

.g-tag-danger {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.g-tag-warn {
  background: rgba(245, 158, 11, 0.1);
  color: #f59e0b;
}

.g-empty {
  font-size: 12px;
  color: var(--color-ide-fg-secondary, #94a3b8);
  font-style: italic;
}
</style>
