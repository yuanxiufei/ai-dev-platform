<script setup lang="ts">
import { ref, onMounted } from "vue"
import { Settings, RefreshCw, Eye, EyeOff, X } from "lucide-vue-next"
import { getConfig, reloadConfig } from "@/api/systemConfig"

const configData = ref<Record<string, unknown> | null>(null)
const loading = ref(false)
const reloading = ref(false)
const errorMsg = ref("")
const showSensitive = ref(false)

async function loadConfig() {
  loading.value = true; errorMsg.value = ""
  try { const res = await getConfig(); configData.value = res.data } catch (e: any) { errorMsg.value = e.response?.data?.detail || e.message || "加载失败" } finally { loading.value = false }
}

async function handleReload() {
  if (!confirm("确定热加载系统配置？")) return
  reloading.value = true; errorMsg.value = ""
  try { const res = await reloadConfig(); alert(res.data.message || "配置已重新加载"); await loadConfig() } catch (e: any) { errorMsg.value = e.response?.data?.detail || e.message || "重载失败" } finally { reloading.value = false }
}

/** 判断是否敏感值（脱敏占位符: *** 或 ****） */
function isSensitive(val: unknown): boolean {
  return typeof val === "string" && /^\*+$/.test(val)
}

/** 格式化显示值 */
function displayValue(val: unknown): string {
  if (val === null) return "null"
  if (val === undefined) return "undefined"
  if (typeof val === "boolean") return val ? "true" : "false"
  if (typeof val === "object") return JSON.stringify(val, null, 2)
  return String(val)
}

/** 过滤/排序配置键 */
function sortedKeys(obj: Record<string, unknown>): string[] {
  return Object.keys(obj).sort()
}

onMounted(loadConfig)
</script>

<template>
  <div class="g-container">
    <div class="g-header">
      <div class="g-header-left"><Settings :size="22" class="g-header-icon" /><h1 class="g-header-title">系统配置</h1><span class="g-header-sub">查看与热加载配置</span></div>
      <div class="g-header-actions">
        <button class="g-btn g-btn-ghost" @click="showSensitive = !showSensitive">
          <Eye v-if="!showSensitive" :size="15" /> <EyeOff v-else :size="15" />
          {{ showSensitive ? "隐藏" : "显示" }}敏感值
        </button>
        <button class="g-btn g-btn-primary" :disabled="reloading" @click="handleReload">
          <RefreshCw :size="15" :class="{ 'g-spin': reloading }" />
          {{ reloading ? "重载中..." : "热加载配置" }}
        </button>
      </div>
    </div>

    <div v-if="errorMsg" class="g-error-msg">{{ errorMsg }}<button class="g-error-close" @click="errorMsg = ''"><X :size="14" /></button></div>
    <div v-if="loading" class="g-loading">加载中...</div>

    <div v-else-if="configData" class="g-config-table">
      <div class="g-table-header">
        <span class="g-th-key">配置键</span>
        <span class="g-th-val">值</span>
      </div>
      <div v-for="key in sortedKeys(configData)" :key="key" class="g-table-row">
        <span class="g-td-key">{{ key }}</span>
        <span class="g-td-val">
          <template v-if="isSensitive(configData[key]) && !showSensitive">
            <span class="g-sensitive">********</span>
          </template>
          <template v-else>
            <code class="g-val-code">{{ displayValue(configData[key]) }}</code>
          </template>
        </span>
      </div>
    </div>
    <div v-else class="g-empty-page">暂无配置数据</div>
  </div>
</template>

<style scoped>
.g-container { padding: 24px; max-width: 900px; margin: 0 auto; }
.g-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }
.g-header-left { display: flex; align-items: center; gap: 10px; }
.g-header-icon { color: var(--color-ide-accent, #a855f7); }
.g-header-title { font-size: 20px; font-weight: 600; color: var(--color-ide-fg, #e2e8f0); margin: 0; }
.g-header-sub { font-size: 13px; color: var(--color-ide-fg-secondary, #94a3b8); }
.g-header-actions { display: flex; gap: 8px; }
.g-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border: none; border-radius: 7px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.15s; }
.g-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.g-btn-primary { background: var(--color-ide-accent, #a855f7); color: #fff; }
.g-btn-ghost { background: transparent; color: var(--color-ide-fg-secondary, #94a3b8); border: 1px solid var(--color-ide-border, #334155); }
.g-btn-ghost:hover { color: var(--color-ide-fg, #e2e8f0); }
.g-spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
.g-error-msg { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; margin-bottom: 16px; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 7px; color: #ef4444; font-size: 13px; }
.g-error-close { background: none; border: none; color: #ef4444; cursor: pointer; }
.g-loading { color: var(--color-ide-fg-secondary, #94a3b8); font-size: 13px; padding: 40px 0; }
.g-empty-page { text-align: center; padding: 60px 0; color: var(--color-ide-fg-secondary, #94a3b8); font-size: 14px; }

.g-config-table { background: var(--color-ide-bg-secondary, #1e293b); border: 1px solid var(--color-ide-border, #334155); border-radius: 10px; overflow: hidden; }
.g-table-header { display: flex; padding: 10px 16px; background: var(--color-ide-bg-primary, #0f172a); border-bottom: 1px solid var(--color-ide-border, #334155); font-size: 12px; font-weight: 600; color: var(--color-ide-fg-secondary, #94a3b8); }
.g-th-key { width: 280px; flex-shrink: 0; }
.g-th-val { flex: 1; }
.g-table-row { display: flex; padding: 9px 16px; border-bottom: 1px solid var(--color-ide-border, #334155); font-size: 13px; transition: background 0.1s; }
.g-table-row:last-child { border-bottom: none; }
.g-table-row:hover { background: var(--color-ide-bg-primary, #0f172a); }
.g-td-key { width: 280px; flex-shrink: 0; color: var(--color-ide-fg, #e2e8f0); font-family: "JetBrains Mono", "Fira Code", monospace; font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.g-td-val { flex: 1; min-width: 0; }
.g-val-code { font-size: 12px; color: var(--color-ide-fg-secondary, #94a3b8); white-space: pre-wrap; word-break: break-all; font-family: "JetBrains Mono", "Fira Code", monospace; }
.g-sensitive { color: var(--color-ide-accent, #a855f7); font-size: 12px; font-family: monospace; user-select: none; }
</style>
