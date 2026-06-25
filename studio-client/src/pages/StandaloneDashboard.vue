<script setup lang="ts">
/**
 * StandaloneDashboard — 独立运行管理面板
 *
 * 功能：
 *  - 系统状态总览（版本、子系统健康、连接状态）
 *  - 功能开关控制（智能休眠 / API鉴权 / 守护进程 / GPU / 远程访问 ...）
 *  - API 密钥管理（创建 / 复制 / 撤销 / 列表）
 *  - 休眠/唤醒手动控制
 */

import { Radio } from "lucide-vue-next"
import { computed, onMounted, onUnmounted, ref } from "vue"
import {
  type ApiKeyCreated,
  type ApiKeyInfo,
  cancelOsSleep,
  createApiKey,
  type FeatureState,
  forceSleep,
  forceWake,
  getOsSleepStatus,
  getStandaloneStatus,
  getWOLInfo,
  listApiKeys,
  listFeatures,
  type OsSleepState,
  redetectWOL,
  revokeApiKey,
  type StandaloneStatus,
  sendWOL,
  toggleFeature,
  triggerOsSleep,
  type WOLInfo,
} from "@/api/standalone"

// ===== 状态 =====
const status = ref<StandaloneStatus | null>(null)
const features = ref<FeatureState[]>([])
const apiKeys = ref<ApiKeyInfo[]>([])
const loading = ref(true)
const toast = ref("")
const toastType = ref<"success" | "error" | "info">("info")
const autoRefresh = ref(true)
const refreshInterval = 8_000 // 8s
let _timer: ReturnType<typeof setInterval> | null = null

// API Key 表单
const _showKeyForm = ref(false)
const showCreatedKey = ref<ApiKeyCreated | null>(null)
const keyForm = ref({ tenant: "default", name: "", roles: "*" as string })
const keyLoading = ref(false)

// 正在切换的功能 key
const togglingKey = ref<string | null>(null)

// OS 休眠状态（独立管理，因为可能频繁变化）
const osSleepState = ref<OsSleepState | null>(null)
const osSleepLoading = ref(false)
const osSleepAction = ref<"trigger" | "cancel" | null>(null)

// 倒计时显示
const osSleepCountdown = ref("")
let _osSleepCountdownTimer: ReturnType<typeof setInterval> | null = null

// WOL 状态
const wolInfo = ref<WOLInfo | null>(null)
const wolLoading = ref(false)
const wolSendingTo = ref<string | null>(null)
const wolSendForm = ref({ mac_address: "", broadcast: "", port: 9 })

// ===== 计算属性 =====

const _uptime = computed(() => {
  if (!status.value) return "—"
  const s = Date.now() / 1000 - status.value.timestamp
  if (s < 60) return `${Math.floor(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${Math.floor(s % 60)}s`
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`
})

const sleepState = computed(
  () => status.value?.subsystems?.sleep?.state ?? "unknown",
)
const _sleepActiveLabel = computed(() => {
  const s = sleepState.value
  if (s === "sleeping") return "休眠中"
  if (s === "waking") return "唤醒中…"
  if (s === "pre_sleep") return "准备休眠…"
  return "活跃"
})

const _watchdogState = computed(
  () => status.value?.subsystems?.watchdog?.state ?? "unknown",
)
const _activeKeyCount = computed(
  () => status.value?.subsystems?.api_auth?.active_keys ?? apiKeys.value.length,
)

// 休眠统计
const _sleepStats = computed(() => status.value?.subsystems?.sleep)

// OS 休眠状态
const _osSleepEnabled = computed(
  () =>
    osSleepState.value?.enabled ??
    status.value?.subsystems?.sleep?.os_sleep?.enabled ??
    false,
)
const osSleepScheduled = computed(
  () =>
    osSleepState.value?.scheduled ??
    status.value?.subsystems?.sleep?.os_sleep?.scheduled ??
    false,
)
const osSleepRemaining = computed(() => {
  const s =
    osSleepState.value?.seconds_until_os_sleep ??
    status.value?.subsystems?.sleep?.os_sleep?.seconds_until_os_sleep ??
    0
  return s
})
const osSleepMode = computed(
  () =>
    osSleepState.value?.mode ??
    status.value?.subsystems?.sleep?.os_sleep?.mode ??
    "sleep",
)
const _osSleepModeLabel = computed(() =>
  osSleepMode.value === "hibernate" ? "休眠（断电）" : "睡眠（内存保持）",
)
const osSleepCountdownDisplay = computed(() => {
  if (!osSleepScheduled.value) return ""
  const s = osSleepRemaining.value
  if (s <= 0) return "即将触发…"
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  const sec = Math.floor(s % 60)
  if (h > 0) return `${h}h ${m}m ${sec}s`
  if (m > 0) return `${m}m ${sec}s`
  return `${sec}s`
})

const _connected = computed(() => status.value?.started)

// WOL 计算属性
const _wolEnabled = computed(() => !!wolInfo.value?.target_mac)
const _wolCommandPython = computed(() => {
  if (!wolInfo.value?.target_mac) return ""
  const mac = wolInfo.value.target_mac
  const bc = wolInfo.value.broadcast_address || "255.255.255.255"
  const port = wolInfo.value.port || 9
  return `python scripts/wake_server.py --mac ${mac} --broadcast ${bc} --port ${port}`
})
const _wolCommandCurl = computed(() => {
  if (!wolInfo.value?.target_mac) return ""
  const mac = wolInfo.value.target_mac
  return `curl -X POST http://<服务器IP>:18000/api/v1/standalone/wol/send -H "Content-Type: application/json" -d '{"mac_address":"${mac}","broadcast":"${wolInfo.value.broadcast_address || "255.255.255.255"}","port":${wolInfo.value.port || 9}}'`
})

// ===== 方法 =====

function showToast(msg: string, type: "success" | "error" | "info" = "info") {
  toast.value = msg
  toastType.value = type
  setTimeout(() => {
    toast.value = ""
  }, 3500)
}

async function fetchStatus() {
  try {
    const res = await getStandaloneStatus()
    status.value = res.data
  } catch (e: any) {
    if (e?.response?.status === 503) {
      status.value = null
    }
  }
}

async function fetchFeatures() {
  try {
    const res = await listFeatures()
    features.value = res.data.features ?? []
  } catch {
    /* ignore */
  }
}

async function fetchKeys() {
  try {
    const res = await listApiKeys()
    apiKeys.value = res.data.keys ?? []
  } catch {
    /* ignore */
  }
}

async function fetchAll() {
  loading.value = true
  await Promise.all([
    fetchStatus(),
    fetchFeatures(),
    fetchKeys(),
    fetchWOLInfo(),
  ])
  loading.value = false
}

async function _handleToggleFeature(feat: FeatureState) {
  if (!feat.dynamic) {
    showToast(`「${feat.name}」由环境变量锁定，不可动态切换`, "info")
    return
  }
  togglingKey.value = feat.key
  try {
    const res = await toggleFeature(feat.key)
    const idx = features.value.findIndex((f) => f.key === feat.key)
    if (idx >= 0) features.value[idx].enabled = res.data.enabled
    showToast(
      `「${feat.name}」已${res.data.enabled ? "启用" : "禁用"}`,
      "success",
    )
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "切换失败", "error")
  } finally {
    togglingKey.value = null
  }
}

async function _handleSleep() {
  try {
    const res = await forceSleep()
    showToast(res.data.message || "已进入休眠", "success")
    setTimeout(fetchStatus, 500)
  } catch (e: any) {
    showToast(
      e?.response?.data?.detail || "无法休眠（可能有活跃请求）",
      "error",
    )
  }
}

async function _handleWake() {
  try {
    const res = await forceWake()
    showToast(res.data.message || "已唤醒", "success")
    setTimeout(fetchStatus, 500)
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "唤醒失败", "error")
  }
}

async function fetchOsSleepStatus() {
  try {
    const res = await getOsSleepStatus()
    osSleepState.value = res.data
  } catch {
    /* ignore */
  }
}

async function _handleOsSleepNow() {
  if (
    !confirm(
      "⚠️ 这将立即使操作系统进入睡眠状态！\n\n电脑将停止响应，需要按电源键或通过 Wake-on-LAN 远程唤醒。\n\n确定要继续吗？",
    )
  )
    return
  osSleepLoading.value = true
  osSleepAction.value = "trigger"
  try {
    await triggerOsSleep()
    showToast("OS 睡眠命令已发出，电脑即将睡眠…", "info")
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "触发失败", "error")
  } finally {
    osSleepLoading.value = false
    osSleepAction.value = null
  }
}

async function _handleCancelOsSleep() {
  osSleepLoading.value = true
  osSleepAction.value = "cancel"
  try {
    await cancelOsSleep()
    osSleepState.value = null
    showToast("已取消 OS 休眠倒计时", "success")
    setTimeout(fetchOsSleepStatus, 300)
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "取消失败", "error")
  } finally {
    osSleepLoading.value = false
    osSleepAction.value = null
  }
}

function startOsSleepCountdown() {
  stopOsSleepCountdown()
  _osSleepCountdownTimer = setInterval(() => {
    if (osSleepScheduled.value) {
      osSleepCountdown.value = osSleepCountdownDisplay.value
    } else {
      osSleepCountdown.value = ""
    }
    // 同步更新 osSleepState 的 remaining 时间
    if (osSleepState.value?.scheduled) {
      osSleepState.value = {
        ...osSleepState.value,
        seconds_until_os_sleep: Math.max(
          0,
          osSleepState.value.seconds_until_os_sleep - 1,
        ),
      }
    }
  }, 1000)
}

function stopOsSleepCountdown() {
  if (_osSleepCountdownTimer) {
    clearInterval(_osSleepCountdownTimer)
    _osSleepCountdownTimer = null
  }
}

async function fetchWOLInfo() {
  try {
    const res = await getWOLInfo()
    wolInfo.value = res.data
  } catch {
    /* ignore */
  }
}

async function _handleSendWOL() {
  const mac = wolSendForm.value.mac_address || wolInfo.value?.target_mac || ""
  if (!mac) {
    showToast("请先输入目标 MAC 地址", "error")
    return
  }
  if (!/^([0-9A-Fa-f]{2}[:-]?){5}[0-9A-Fa-f]{2}$/.test(mac)) {
    showToast("MAC 地址格式无效", "error")
    return
  }
  wolLoading.value = true
  wolSendingTo.value = mac
  try {
    const res = await sendWOL(wolSendForm.value)
    if (res.data.success) {
      showToast(`魔术包已发送 → ${res.data.target_mac}`, "success")
      // 刷新 WOL 信息
      setTimeout(fetchWOLInfo, 500)
    } else {
      showToast(res.data.message || "发送失败", "error")
    }
  } catch (e: any) {
    showToast(
      e?.response?.data?.detail || "WOL 发送失败，请检查网络权限",
      "error",
    )
  } finally {
    wolLoading.value = false
    wolSendingTo.value = null
  }
}

async function _handleRedetectWOL() {
  wolLoading.value = true
  try {
    const res = await redetectWOL()
    wolInfo.value = res.data
    showToast("网络接口已重新检测", "success")
  } catch (_e: any) {
    showToast("重新检测失败", "error")
  } finally {
    wolLoading.value = false
  }
}

function _copyWOLCommand(cmd: string) {
  navigator.clipboard
    .writeText(cmd)
    .then(() => {
      showToast("命令已复制到剪贴板", "success")
    })
    .catch(() => showToast("复制失败，请手动复制", "error"))
}

async function _handleCreateKey() {
  if (!keyForm.value.name) return
  keyLoading.value = true
  try {
    const roles = keyForm.value.roles
      ? keyForm.value.roles
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
      : null
    const res = await createApiKey({
      tenant: keyForm.value.tenant || "default",
      name: keyForm.value.name,
      roles,
    })
    showCreatedKey.value = res.data
    keyForm.value = { tenant: "default", name: "", roles: "*" }
    showToast("API Key 已创建", "success")
    fetchKeys()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "创建失败", "error")
  } finally {
    keyLoading.value = false
  }
}

async function _handleRevokeKey(hashedKey: string) {
  if (!confirm("确定撤销此 API Key？操作不可撤销。")) return
  try {
    await revokeApiKey(hashedKey)
    showToast("API Key 已撤销", "success")
    fetchKeys()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "撤销失败", "error")
  }
}

function _copyKey(fullKey: string) {
  navigator.clipboard
    .writeText(fullKey)
    .then(() => {
      showToast("已复制到剪贴板（仅显示一次，请妥善保存）", "success")
    })
    .catch(() => showToast("复制失败，请手动复制", "error"))
}

function _dismissCreatedKey() {
  showCreatedKey.value = null
}

function _featureIcon(key: string) {
  const map: Record<string, string> = {
    smart_sleep: "🌙",
    api_auth: "🔑",
    watchdog: "🛡️",
    gpu_enabled: "⚡",
    remote_access: "🌐",
    auto_optimize: "🔧",
    background_tasks: "📋",
    auto_download_models: "📦",
    os_sleep: "💤",
  }
  return map[key] ?? "🔹"
}

function _sleepStateColor(state: string): string {
  const map: Record<string, string> = {
    sleeping: "text-amber-400",
    waking: "text-cyan-400",
    idle: "text-green-400",
    active: "text-blue-400",
    pre_sleep: "text-yellow-400",
  }
  return map[state] ?? "text-gray-400"
}

// ===== 生命周期 =====
onMounted(async () => {
  await fetchAll()
  await fetchOsSleepStatus()
  await fetchWOLInfo()
  startOsSleepCountdown()
  if (autoRefresh.value) {
    _timer = setInterval(fetchAll, refreshInterval)
  }
})

onUnmounted(() => {
  if (_timer) {
    clearInterval(_timer)
    _timer = null
  }
  stopOsSleepCountdown()
})

function _toggleAutoRefresh() {
  autoRefresh.value = !autoRefresh.value
  if (autoRefresh.value) {
    _timer = setInterval(fetchAll, refreshInterval)
  } else if (_timer) {
    clearInterval(_timer)
    _timer = null
  }
}
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- ===== Toast ===== -->
    <Transition name="toast">
      <div
        v-if="toast"
        :class="[
          'fixed top-6 left-1/2 -translate-x-1/2 z-50 px-5 py-2.5 rounded-xl text-sm font-medium backdrop-blur-xl shadow-xl border',
          toastType === 'success' ? 'bg-green-500/15 border-green-500/25 text-green-400' :
          toastType === 'error' ? 'bg-red-500/15 border-red-500/25 text-red-400' :
          'bg-blue-500/15 border-blue-500/25 text-blue-400',
        ]"
      >
        {{ toast }}
      </div>
    </Transition>

    <!-- ===== 页面头部 ===== -->
    <div class="flex items-center justify-between px-8 pt-8 pb-6 border-b border-white/5 shrink-0">
      <div>
        <h1 class="text-2xl font-bold text-white flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-purple-500/20 to-cyan-500/10 border border-purple-500/20 flex items-center justify-center">
            <Monitor class="w-5 h-5 text-purple-400" />
          </div>
          独立运行管理
        </h1>
        <p class="text-sm text-gray-500 mt-1.5 ml-[3.25rem]">管理本机服务的守护进程、智能休眠、API 鉴权与系统开关</p>
      </div>
      <div class="flex items-center gap-3">
        <button
          @click="toggleAutoRefresh"
          :class="[
            'flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-colors border',
            autoRefresh ? 'bg-green-500/10 border-green-500/20 text-green-400' : 'bg-white/[0.04] border-white/10 text-gray-500 hover:text-gray-300'
          ]"
          title="自动刷新"
        >
          <RefreshCw :class="['w-3.5 h-3.5', autoRefresh && 'animate-spin']" :style="{ animationDuration: '3s' }" />
          {{ autoRefresh ? '自动刷新中' : '自动刷新' }}
        </button>
        <button
          @click="fetchAll"
          :disabled="loading"
          class="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 disabled:opacity-50 text-white text-sm font-medium transition-colors shadow-lg shadow-brand-500/15"
        >
          <RefreshCw :class="['w-4 h-4', loading && 'animate-spin']" />
          刷新
        </button>
      </div>
    </div>

    <!-- ===== 滚动区域 ===== -->
    <div class="flex-1 overflow-y-auto p-6 mx-auto w-full max-w-[1200px]">
      <!-- ===== 全局连接状态横幅 ===== -->
      <div
        v-if="!connected && !loading"
        class="mb-6 p-4 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center gap-3 text-sm"
      >
        <AlertTriangle class="w-5 h-5 text-red-400 shrink-0" />
        <div>
          <span class="text-red-400 font-medium">Standalone 服务未连接</span>
          <span class="text-gray-500 ml-2">— 请确认后端已以 standalone 模式启动</span>
        </div>
      </div>

      <div v-if="loading" class="flex items-center justify-center py-32">
        <Loader2 class="w-8 h-8 animate-spin text-blue-400" />
      </div>

      <template v-else>
        <!-- ===== SECTION 1: 系统总览卡片行 ===== -->
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <!-- 版本 -->
          <div class="rounded-2xl border border-white/8 bg-white/[0.02] p-5 flex items-center gap-4 hover:border-white/12 transition-colors">
            <div class="w-11 h-11 rounded-xl bg-purple-500/10 border border-purple-500/15 flex items-center justify-center shrink-0">
              <Server class="w-5 h-5 text-purple-400" />
            </div>
            <div>
              <p class="text-xs text-gray-500 mb-0.5">版本</p>
              <p class="text-lg font-semibold text-white font-mono">{{ status?.version ?? '—' }}</p>
            </div>
          </div>

          <!-- 运行时间 -->
          <div class="rounded-2xl border border-white/8 bg-white/[0.02] p-5 flex items-center gap-4 hover:border-white/12 transition-colors">
            <div class="w-11 h-11 rounded-xl bg-blue-500/10 border border-blue-500/15 flex items-center justify-center shrink-0">
              <Clock class="w-5 h-5 text-blue-400" />
            </div>
            <div>
              <p class="text-xs text-gray-500 mb-0.5">运行时长</p>
              <p class="text-lg font-semibold text-white font-mono">{{ uptime }}</p>
            </div>
          </div>

          <!-- 连接状态 -->
          <div class="rounded-2xl border border-white/8 bg-white/[0.02] p-5 flex items-center gap-4 hover:border-white/12 transition-colors">
            <div class="w-11 h-11 rounded-xl bg-green-500/10 border border-green-500/15 flex items-center justify-center shrink-0">
              <Activity class="w-5 h-5 text-green-400" />
            </div>
            <div>
              <p class="text-xs text-gray-500 mb-0.5">系统状态</p>
              <div class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
                <span class="text-lg font-semibold text-green-400">{{ connected ? '运行中' : '离线' }}</span>
              </div>
            </div>
          </div>

          <!-- API Key 数量 -->
          <div class="rounded-2xl border border-white/8 bg-white/[0.02] p-5 flex items-center gap-4 hover:border-white/12 transition-colors">
            <div class="w-11 h-11 rounded-xl bg-amber-500/10 border border-amber-500/15 flex items-center justify-center shrink-0">
              <KeyRound class="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <p class="text-xs text-gray-500 mb-0.5">活跃密钥</p>
              <p class="text-lg font-semibold text-white font-mono">{{ activeKeyCount }}</p>
            </div>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <!-- ===== LEFT (2/3): 功能开关 + 密钥管理 ===== -->
          <div class="lg:col-span-2 space-y-8">

            <!-- ===== SECTION 2: 功能开关 ===== -->
            <section>
              <div class="flex items-center gap-3 mb-4">
                <div class="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/15 flex items-center justify-center">
                  <Gauge class="w-4 h-4 text-cyan-400" />
                </div>
                <div>
                  <h2 class="text-base font-semibold text-white">功能开关</h2>
                  <p class="text-xs text-gray-500">控制各子系统的启停状态</p>
                </div>
              </div>

              <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div
                  v-for="feat in features"
                  :key="feat.key"
                  :class="[
                    'rounded-xl border p-4 transition-all duration-200 flex items-center justify-between group',
                    feat.enabled ? 'border-white/10 bg-white/[0.03] hover:border-white/15' : 'border-white/[0.04] bg-white/[0.01] hover:border-white/8',
                    !feat.dynamic && 'opacity-60',
                  ]"
                >
                  <div class="flex items-center gap-3 min-w-0 flex-1">
                    <span class="text-xl leading-none shrink-0">{{ featureIcon(feat.key) }}</span>
                    <div class="min-w-0">
                      <p class="text-sm font-medium text-white truncate">{{ feat.name }}</p>
                      <p class="text-[11px] text-gray-500 truncate">{{ feat.description }}</p>
                      <p v-if="!feat.dynamic" class="text-[10px] text-amber-500/70 mt-0.5">🔒 环境变量锁定</p>
                    </div>
                  </div>
                  <button
                    @click="handleToggleFeature(feat)"
                    :disabled="!feat.dynamic || togglingKey === feat.key"
                    :class="[
                      'relative inline-flex h-6 w-10 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ml-3',
                      feat.enabled ? 'bg-brand-500' : 'bg-gray-600',
                      !feat.dynamic && 'cursor-not-allowed opacity-50',
                    ]"
                    :title="feat.dynamic ? '点击切换' : '由环境变量锁定'"
                  >
                    <Loader2 v-if="togglingKey === feat.key" class="absolute inset-0 m-auto w-3.5 h-3.5 animate-spin text-white" />
                    <span
                      :class="[
                        'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200',
                        feat.enabled ? 'translate-x-4' : 'translate-x-0',
                        togglingKey === feat.key && 'opacity-0',
                      ]"
                    />
                  </button>
                </div>
              </div>
            </section>

            <!-- ===== SECTION 3: API 密钥管理 ===== -->
            <section>
              <div class="flex items-center justify-between mb-4">
                <div class="flex items-center gap-3">
                  <div class="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/15 flex items-center justify-center">
                    <Fingerprint class="w-4 h-4 text-amber-400" />
                  </div>
                  <div>
                    <h2 class="text-base font-semibold text-white">远程访问密钥</h2>
                    <p class="text-xs text-gray-500">管理外部调用本机服务的 API Key</p>
                  </div>
                </div>
                <button
                  @click="showKeyForm = !showKeyForm"
                  class="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-colors bg-amber-500/10 border border-amber-500/20 text-amber-400 hover:bg-amber-500/20"
                >
                  <Plus class="w-3.5 h-3.5" />
                  创建新密钥
                </button>
              </div>

              <!-- 创建表单 -->
              <Transition name="slide-fade">
                <div v-if="showKeyForm" class="mb-4 p-4 rounded-xl border border-white/10 bg-white/[0.03]">
                  <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-3">
                    <div>
                      <label class="block text-[11px] font-medium text-gray-400 mb-1">租户标识</label>
                      <input
                        v-model="keyForm.tenant"
                        placeholder="default"
                        class="w-full rounded-lg border border-white/10 bg-white/[0.05] px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-amber-500/40 transition-all font-mono"
                      />
                    </div>
                    <div>
                      <label class="block text-[11px] font-medium text-gray-400 mb-1">名称 <span class="text-red-400">*</span></label>
                      <input
                        v-model="keyForm.name"
                        placeholder="外部团队名称"
                        class="w-full rounded-lg border border-white/10 bg-white/[0.05] px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-amber-500/40 transition-all"
                      />
                    </div>
                    <div>
                      <label class="block text-[11px] font-medium text-gray-400 mb-1">角色权限</label>
                      <input
                        v-model="keyForm.roles"
                        placeholder="* 或 studio.chat,video.generate"
                        class="w-full rounded-lg border border-white/10 bg-white/[0.05] px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-amber-500/40 transition-all font-mono"
                      />
                      <p class="text-[10px] text-gray-600 mt-0.5"><code>*</code> = 全部权限</p>
                    </div>
                  </div>
                  <div class="flex gap-2">
                    <button
                      @click="handleCreateKey"
                      :disabled="!keyForm.name || keyLoading"
                      class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-500 hover:bg-amber-600 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-medium transition-colors"
                    >
                      <Loader2 v-if="keyLoading" class="w-3.5 h-3.5 animate-spin" />
                      <Plus v-else class="w-3.5 h-3.5" />
                      生成密钥
                    </button>
                    <button @click="showKeyForm = false" class="px-4 py-2 rounded-lg bg-white/[0.04] border border-white/10 text-sm text-gray-400 hover:text-white transition-colors">
                      取消
                    </button>
                  </div>
                </div>
              </Transition>

              <!-- 新创建的 Key 提示框 -->
              <Transition name="slide-fade">
                <div v-if="showCreatedKey" class="mb-4 p-4 rounded-xl border border-amber-500/30 bg-amber-500/[0.06]">
                  <div class="flex items-center justify-between mb-2">
                    <p class="text-sm font-semibold text-amber-400 flex items-center gap-2">
                      <Check class="w-4 h-4" /> 密钥创建成功
                    </p>
                    <button @click="dismissCreatedKey" class="text-gray-500 hover:text-gray-300"><X class="w-4 h-4" /></button>
                  </div>
                  <p class="text-xs text-gray-400 mb-2">此密钥仅显示一次，请立即复制并妥善保存：</p>
                  <div class="flex items-center gap-2 mb-2">
                    <code class="flex-1 text-sm font-mono text-green-400 bg-black/30 rounded-lg px-3 py-2 break-all select-all">{{ showCreatedKey.full_key }}</code>
                    <button @click="copyKey(showCreatedKey.full_key)" class="p-2 rounded-lg bg-white/[0.08] hover:bg-white/[0.15] text-gray-400 hover:text-white transition-colors shrink-0" title="复制">
                      <Copy class="w-4 h-4" />
                    </button>
                  </div>
                  <div class="flex gap-4 text-[11px] text-gray-500">
                    <span>租户: <strong class="text-gray-300">{{ showCreatedKey.tenant }}</strong></span>
                    <span>名称: <strong class="text-gray-300">{{ showCreatedKey.name }}</strong></span>
                    <span>前缀: <code class="text-gray-400">{{ showCreatedKey.access_key_prefix }}</code></span>
                  </div>
                </div>
              </Transition>

              <!-- 密钥列表 -->
              <div v-if="!apiKeys.length" class="rounded-xl border border-white/5 bg-white/[0.01] p-8 text-center">
                <KeyRound class="w-10 h-10 text-gray-600 mx-auto mb-3 opacity-40" />
                <p class="text-sm text-gray-500">还没有远程访问密钥</p>
                <p class="text-xs text-gray-600 mt-1">创建密钥后，外部团队即可通过 <code class="text-gray-500">Authorization: Bearer &lt;key&gt;</code> 调用本机 API</p>
              </div>

              <div v-else class="space-y-2">
                <div
                  v-for="key in apiKeys"
                  :key="key.hashed_key"
                  class="flex items-center gap-3 p-3 rounded-xl border border-white/6 bg-white/[0.02] hover:border-white/10 transition-colors group"
                >
                  <div class="w-9 h-9 rounded-lg bg-amber-500/10 flex items-center justify-center shrink-0">
                    <KeyRound class="w-4 h-4 text-amber-400" />
                  </div>
                  <div class="flex-1 min-w-0">
                    <div class="flex items-center gap-2">
                      <span class="text-sm font-medium text-white font-mono">{{ key.key_prefix }}</span>
                      <span v-if="key.roles.includes('*')" class="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-500/15 text-purple-400 font-medium">全部权限</span>
                    </div>
                    <div class="flex items-center gap-3 mt-0.5 text-[11px] text-gray-500">
                      <span>租户: {{ key.tenant }}</span>
                      <span v-if="key.name">名称: {{ key.name }}</span>
                      <span v-if="key.created_at">创建于 {{ new Date(key.created_at * 1000).toLocaleDateString() }}</span>
                      <span v-else>预置密钥</span>
                    </div>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class="text-[10px] px-1.5 py-1 rounded text-green-500/60 bg-green-500/5">active</span>
                    <button
                      @click="handleRevokeKey(key.hashed_key)"
                      class="p-1.5 rounded-lg text-gray-600 hover:text-red-400 hover:bg-red-500/10 transition-colors opacity-0 group-hover:opacity-100"
                      title="撤销密钥"
                    >
                      <Trash2 class="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>

              <!-- 使用方式提示 -->
              <div class="mt-3 p-3 rounded-xl border border-white/5 bg-white/[0.01]">
                <p class="text-[11px] font-medium text-gray-500 mb-1.5">🔗 使用方式</p>
                <div class="text-xs text-gray-600 space-y-1">
                  <p>• Header: <code class="text-gray-500">Authorization: Bearer &lt;api_key&gt;</code></p>
                  <p>• Header: <code class="text-gray-500">X-API-Key: &lt;api_key&gt;</code></p>
                  <p>• Query: <code class="text-gray-500">?api_key=&lt;key&gt;</code></p>
                </div>
              </div>
            </section>

          </div>

          <!-- ===== RIGHT (1/3): 休眠控制 + 看门狗 ===== -->
          <div class="space-y-8">

            <!-- ===== SECTION 4: 智能休眠控制 ===== -->
            <section>
              <div class="flex items-center gap-3 mb-4">
                <div class="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/15 flex items-center justify-center">
                  <Moon class="w-4 h-4 text-indigo-400" />
                </div>
                <div>
                  <h2 class="text-base font-semibold text-white">智能休眠</h2>
                  <p class="text-xs text-gray-500">手动休眠 / 唤醒控制</p>
                </div>
              </div>

              <div class="rounded-2xl border border-white/8 bg-white/[0.02] p-5">
                <!-- 状态指示 -->
                <div class="flex items-center justify-between mb-5">
                  <span class="text-sm text-gray-400">当前状态</span>
                  <span :class="['flex items-center gap-2 text-sm font-semibold', sleepStateColor(sleepState)]">
                    <span class="w-2 h-2 rounded-full animate-pulse" :class="{
                      'bg-amber-400': sleepState === 'sleeping',
                      'bg-cyan-400': sleepState === 'waking',
                      'bg-green-400': sleepState === 'idle',
                      'bg-blue-400': sleepState === 'active',
                      'bg-yellow-400': sleepState === 'pre_sleep',
                    }" />
                    {{ sleepActiveLabel }}
                  </span>
                </div>

                <!-- 统计 -->
                <div v-if="sleepStats" class="space-y-2 mb-5 text-xs">
                  <div class="flex justify-between">
                    <span class="text-gray-500">距上次请求</span>
                    <span class="text-gray-300 font-mono">{{ sleepStats.last_request_seconds_ago.toFixed(0) }}s</span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-gray-500">活跃请求数</span>
                    <span class="text-gray-300 font-mono">{{ sleepStats.active_requests }}</span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-gray-500">休眠次数</span>
                    <span class="text-gray-300 font-mono">{{ sleepStats.sleep_count }}</span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-gray-500">累计休眠时长</span>
                    <span class="text-gray-300 font-mono">{{ sleepStats.total_sleep_duration.toFixed(0) }}s</span>
                  </div>
                </div>

                <!-- 按钮 -->
                <div class="flex gap-2">
                  <button
                    @click="handleSleep"
                    :disabled="sleepState === 'sleeping'"
                    class="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 bg-amber-500/10 border border-amber-500/20 text-amber-400 hover:bg-amber-500/20 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <Moon class="w-4 h-4" />
                    强制休眠
                  </button>
                  <button
                    @click="handleWake"
                    :disabled="sleepState !== 'sleeping'"
                    class="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 hover:bg-cyan-500/20 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <Power class="w-4 h-4" />
                    唤醒
                  </button>
                </div>

                <p class="mt-3 text-[10px] text-gray-600 leading-relaxed">
                  系统在 {{ sleepState === 'sleeping' ? '休眠中' : '活跃状态' }}。
                  休眠时自动卸载模型、降低 CPU 优先级以节省资源，收到请求时自动唤醒。
                </p>
              </div>
            </section>

            <!-- ===== SECTION 5: 系统省电休眠 ===== -->
            <section>
              <div class="flex items-center gap-3 mb-4">
                <div class="w-8 h-8 rounded-lg bg-violet-500/10 border border-violet-500/15 flex items-center justify-center">
                  <Battery class="w-4 h-4 text-violet-400" />
                </div>
                <div>
                  <h2 class="text-base font-semibold text-white">系统省电休眠</h2>
                  <p class="text-xs text-gray-500">操作系统级睡眠/休眠控制</p>
                </div>
              </div>

              <div class="rounded-2xl border border-white/8 bg-white/[0.02] p-5">
                <!-- 状态 -->
                <div class="flex items-center justify-between mb-5">
                  <span class="text-sm text-gray-400">模式</span>
                  <span class="text-sm font-semibold text-violet-400">{{ osSleepModeLabel }}</span>
                </div>

                <!-- 倒计时（如果已安排） -->
                <div
                  v-if="osSleepScheduled"
                  class="mb-5 p-4 rounded-xl border border-violet-500/20 bg-violet-500/[0.06]"
                >
                  <div class="flex items-center gap-2 mb-2">
                    <Timer class="w-4 h-4 text-violet-400 animate-pulse" />
                    <span class="text-xs font-medium text-violet-400">OS 休眠倒计时</span>
                  </div>
                  <div class="text-2xl font-bold text-violet-300 font-mono mb-1">
                    {{ osSleepCountdownDisplay || osSleepCountdown }}
                  </div>
                  <p class="text-[10px] text-gray-500">
                    应用休眠超 {{ (osSleepState?.timeout_seconds ?? 1800) / 60 }}分钟后，将自动触发操作系统{{ osSleepModeLabel }}
                  </p>
                </div>

                <!-- 未安排时 -->
                <div
                  v-else
                  class="mb-5 p-4 rounded-xl border border-white/5 bg-white/[0.01]"
                >
                  <div class="flex items-center gap-2">
                    <TimerOff class="w-4 h-4 text-gray-500" />
                    <span class="text-xs text-gray-500">暂无 OS 休眠计划（应用休眠未触发或已关闭）</span>
                  </div>
                </div>

                <!-- 按钮 -->
                <div class="flex gap-2 mb-3">
                  <button
                    @click="handleOsSleepNow"
                    :disabled="osSleepLoading"
                    class="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 bg-violet-500/10 border border-violet-500/20 text-violet-400 hover:bg-violet-500/20 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <Loader2 v-if="osSleepAction === 'trigger'" class="w-4 h-4 animate-spin" />
                    <BatteryWarning v-else class="w-4 h-4" />
                    立即休眠系统
                  </button>
                  <button
                    @click="handleCancelOsSleep"
                    :disabled="!osSleepScheduled || osSleepLoading"
                    class="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 bg-amber-500/10 border border-amber-500/20 text-amber-400 hover:bg-amber-500/20 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <Loader2 v-if="osSleepAction === 'cancel'" class="w-4 h-4 animate-spin" />
                    <TimerOff v-else class="w-4 h-4" />
                    取消倒计时
                  </button>
                </div>

                <div class="p-3 rounded-xl border border-amber-500/10 bg-amber-500/[0.03]">
                  <p class="text-[10px] text-amber-400/70 font-medium mb-1.5">⚠️ 唤醒方式</p>
                  <div class="text-[10px] text-gray-500 space-y-1">
                    <p>• <strong>Wake-on-LAN</strong>: 路由器 / 另一台设备发送魔术包唤醒</p>
                    <p>• <strong>定时唤醒</strong>: BIOS 设置定时开机 / RTC 唤醒</p>
                    <p>• <strong>手动唤醒</strong>: 按电源键或键盘鼠标</p>
                  </div>
                </div>
              </div>
            </section>

            <!-- ===== SECTION 6: 远程唤醒 (Wake-on-LAN) ===== -->
            <section>
              <div class="flex items-center gap-3 mb-4">
                <div class="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/15 flex items-center justify-center">
                  <Wifi class="w-4 h-4 text-emerald-400" />
                </div>
                <div>
                  <h2 class="text-base font-semibold text-white">远程唤醒</h2>
                  <p class="text-xs text-gray-500">Wake-on-LAN 魔术包发送与配置</p>
                </div>
              </div>

              <div class="rounded-2xl border border-white/8 bg-white/[0.02] p-5">
                <!-- 本机网络接口 -->
                <div class="mb-5">
                  <div class="flex items-center justify-between mb-3">
                    <span class="text-xs font-medium text-gray-400">本机网络接口</span>
                    <button
                      @click="handleRedetectWOL"
                      :disabled="wolLoading"
                      class="flex items-center gap-1 px-2 py-1 rounded text-[10px] text-gray-500 hover:text-emerald-400 hover:bg-emerald-500/10 transition-colors"
                    >
                      <RefreshCw :class="['w-3 h-3', wolLoading && 'animate-spin']" />
                      重新检测
                    </button>
                  </div>

                  <div v-if="wolInfo?.interfaces?.length" class="space-y-1.5">
                    <div
                      v-for="iface in wolInfo.interfaces"
                      :key="iface.mac"
                      :class="[
                        'rounded-lg border p-2.5 flex items-center gap-3 text-xs',
                        iface.mac === wolInfo.target_mac ? 'border-emerald-500/20 bg-emerald-500/[0.05]' : 'border-white/5 bg-white/[0.01]',
                      ]"
                    >
                      <Radio :class="['w-3.5 h-3.5 shrink-0', iface.mac === wolInfo.target_mac ? 'text-emerald-400' : 'text-gray-600']" />
                      <div class="flex-1 min-w-0">
                        <div class="flex items-center gap-2">
                          <span class="text-gray-300 font-medium truncate">{{ iface.interface_name }}</span>
                          <span v-if="iface.mac === wolInfo.target_mac" class="text-[9px] px-1 py-0.5 rounded bg-emerald-500/15 text-emerald-400 shrink-0">唤醒目标</span>
                        </div>
                        <div class="flex items-center gap-3 mt-0.5">
                          <span class="text-gray-500 font-mono text-[11px]">{{ iface.mac }}</span>
                          <span v-if="iface.ip" class="text-gray-600">{{ iface.ip }}</span>
                          <span v-if="iface.broadcast" class="text-gray-600">brd {{ iface.broadcast }}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                  <div v-else class="p-3 rounded-lg border border-white/5 bg-white/[0.01] text-xs text-gray-500 text-center">
                    未检测到网络接口 — 请确保网卡已启用
                  </div>
                </div>

                <!-- WOL 发送表单 -->
                <div class="mb-5 p-4 rounded-xl border border-white/8 bg-white/[0.02]">
                  <p class="text-xs font-medium text-gray-400 mb-3">发送魔术包唤醒设备</p>
                  <div class="grid grid-cols-3 gap-2 mb-3">
                    <div>
                      <label class="text-[10px] text-gray-500 mb-0.5 block">目标 MAC</label>
                      <input
                        v-model="wolSendForm.mac_address"
                        :placeholder="wolInfo?.target_mac || 'AA:BB:CC:DD:EE:FF'"
                        class="w-full rounded-lg border border-white/10 bg-white/[0.05] px-2.5 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-emerald-500/40 transition-all font-mono"
                      />
                    </div>
                    <div>
                      <label class="text-[10px] text-gray-500 mb-0.5 block">广播地址</label>
                      <input
                        v-model="wolSendForm.broadcast"
                        :placeholder="wolInfo?.broadcast_address || '255.255.255.255'"
                        class="w-full rounded-lg border border-white/10 bg-white/[0.05] px-2.5 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-emerald-500/40 transition-all font-mono"
                      />
                    </div>
                    <div>
                      <label class="text-[10px] text-gray-500 mb-0.5 block">端口</label>
                      <input
                        v-model.number="wolSendForm.port"
                        type="number"
                        min="1"
                        max="65535"
                        class="w-full rounded-lg border border-white/10 bg-white/[0.05] px-2.5 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-emerald-500/40 transition-all font-mono"
                      />
                    </div>
                  </div>
                  <button
                    @click="handleSendWOL"
                    :disabled="wolLoading"
                    class="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200 bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20 disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <Loader2 v-if="wolLoading" class="w-4 h-4 animate-spin" />
                    <Send v-else class="w-4 h-4" />
                    {{ wolLoading ? '发送中…' : '发送魔术包' }}
                  </button>
                  <p v-if="wolInfo?.last_sent_at" class="mt-2 text-[10px] text-gray-500">
                    上次发送：{{ new Date(wolInfo.last_sent_at * 1000).toLocaleString() }}
                    <span :class="wolInfo.last_sent_success ? 'text-green-500' : 'text-red-400'">
                      {{ wolInfo.last_sent_success ? '✓ 成功' : '✗ 失败' }}
                    </span>
                  </p>
                </div>

                <!-- 远程唤醒命令 -->
                <div class="mb-3">
                  <p class="text-xs font-medium text-gray-400 mb-2">📋 在另一台电脑上执行唤醒</p>

                  <!-- Python 脚本方式 -->
                  <div class="flex items-center gap-2 mb-2">
                    <div class="flex-1 rounded-lg border border-white/8 bg-black/20 px-3 py-2 text-xs text-gray-400 font-mono overflow-x-auto whitespace-nowrap">
                      <Terminal class="w-3 h-3 inline mr-1 text-emerald-400/60" />{{ wolCommandPython }}
                    </div>
                    <button
                      @click="copyWOLCommand(wolCommandPython)"
                      class="p-2 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] text-gray-400 hover:text-white transition-colors shrink-0"
                      title="复制"
                    >
                      <Copy class="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <!-- Curl 方式 -->
                  <div class="flex items-center gap-2">
                    <div class="flex-1 rounded-lg border border-white/8 bg-black/20 px-3 py-2 text-xs text-gray-400 font-mono overflow-x-auto whitespace-nowrap">
                      <Terminal class="w-3 h-3 inline mr-1 text-emerald-400/60" />{{ wolCommandCurl }}
                    </div>
                    <button
                      @click="copyWOLCommand(wolCommandCurl)"
                      class="p-2 rounded-lg bg-white/[0.06] hover:bg-white/[0.12] text-gray-400 hover:text-white transition-colors shrink-0"
                      title="复制"
                    >
                      <Copy class="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <!-- WOL 设置说明 -->
                <div class="p-3 rounded-xl border border-emerald-500/10 bg-emerald-500/[0.03]">
                  <p class="text-[10px] text-emerald-400/70 font-medium mb-1.5">🔧 确保能被远程唤醒</p>
                  <div class="text-[10px] text-gray-500 space-y-1">
                    <p>• <strong>BIOS</strong>: 启用 Wake-on-LAN / PCIe 唤醒（关闭 ErP/EuP 节能）</p>
                    <p>• <strong>Windows</strong>: 设备管理器 → 网卡属性 → 电源管理 → ✓「允许此设备唤醒」+ ✓「仅魔术包」</p>
                    <p>• <strong>Linux</strong>: <code class="text-gray-500">ethtool -s eth0 wol g</code>（启用 WOL）</p>
                    <p>• <strong>网络</strong>: 唤醒设备和被唤醒设备必须在同一子网</p>
                    <p>• <strong>MAC 地址</strong>: 必须选择有线网卡（无线 WOL 不稳定）</p>
                  </div>
                </div>
              </div>
            </section>

            <!-- ===== SECTION 7: 看门狗状态 ===== -->
            <section>
              <div class="flex items-center gap-3 mb-4">
                <div class="w-8 h-8 rounded-lg bg-green-500/10 border border-green-500/15 flex items-center justify-center">
                  <Shield class="w-4 h-4 text-green-400" />
                </div>
                <div>
                  <h2 class="text-base font-semibold text-white">守护进程</h2>
                  <p class="text-xs text-gray-500">崩溃恢复状态</p>
                </div>
              </div>

              <div class="rounded-2xl border border-white/8 bg-white/[0.02] p-5">
                <div class="flex items-center justify-between mb-4">
                  <span class="text-sm text-gray-400">健康状态</span>
                  <span :class="['flex items-center gap-2 text-sm font-semibold', watchdogState === 'running' ? 'text-green-400' : 'text-gray-400']">
                    <span class="w-2 h-2 rounded-full" :class="watchdogState === 'running' ? 'bg-green-400 animate-pulse' : 'bg-gray-500'" />
                    {{ watchdogState === 'running' ? '守护中' : watchdogState }}
                  </span>
                </div>

                <div v-if="status?.subsystems?.watchdog" class="space-y-2 text-xs">
                  <div class="flex justify-between">
                    <span class="text-gray-500">守护进程 PID</span>
                    <span class="text-gray-300 font-mono">{{ status.subsystems.watchdog.health_pid ?? '—' }}</span>
                  </div>
                  <div class="flex justify-between">
                    <span class="text-gray-500">累计重启</span>
                    <span class="text-gray-300 font-mono">{{ status.subsystems.watchdog.restarts ?? 0 }} 次</span>
                  </div>
                </div>
                <div v-else class="text-xs text-gray-600">
                  守护进程由外部启动脚本管理，此处显示运行状态。
                </div>
              </div>
            </section>

            <!-- ===== 快速操作 ===== -->
            <section>
              <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">快速命令</h3>
              <div class="space-y-2">
                <div class="rounded-xl border border-white/6 bg-white/[0.01] p-3">
                  <p class="text-[11px] font-medium text-gray-400 mb-1.5">查看健康状态</p>
                  <code class="text-xs text-gray-500 bg-black/20 rounded px-2 py-1 block break-all">curl http://localhost:18000/api/v1/utils/health-check/</code>
                </div>
                <div class="rounded-xl border border-white/6 bg-white/[0.01] p-3">
                  <p class="text-[11px] font-medium text-gray-400 mb-1.5">使用 API Key 调用 Agent</p>
                  <code class="text-xs text-gray-500 bg-black/20 rounded px-2 py-1 block break-all">curl -H "Authorization: Bearer &lt;key&gt;" http://localhost:18000/api/v1/agent/chat/simple -d '{"message":"hello"}'</code>
                </div>
              </div>
            </section>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.toast-enter-active, .toast-leave-active {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}
.toast-enter-from, .toast-leave-to {
  opacity: 0;
  transform: translateY(-12px) translateX(-50%);
}

.slide-fade-enter-active {
  transition: all 0.25s ease-out;
}
.slide-fade-leave-active {
  transition: all 0.2s ease-in;
}
.slide-fade-enter-from {
  opacity: 0;
  transform: translateY(-8px);
  max-height: 0;
}
.slide-fade-leave-to {
  opacity: 0;
  transform: translateY(-4px);
  max-height: 0;
}
</style>
