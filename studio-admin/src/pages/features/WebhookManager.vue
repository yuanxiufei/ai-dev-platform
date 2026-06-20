<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { webhookApi, type WebhookConfig, type WebhookDeliveryLog, type WebhookTestResult } from '@/api/model-features'

const webhooks = ref<WebhookConfig[]>([])
const loading = ref(true)

// Create/Edit modal
const showModal = ref(false)
const editingId = ref('')
const form = ref({
  url: '', name: '', events: [] as string[], secret: '',
  max_retries: 3, timeout_seconds: 10, description: '', is_active: true,
  headers: {} as Record<string, string>,
})

// Events
const eventTypes = ref<{ value: string; name: string; description: string }[]>([])
const allEvents = computed(() => eventTypes.value.map(e => e.value))

// Test result
const testResult = ref<WebhookTestResult | null>(null)

// Logs
const showLogs = ref(false)
const logsWebhookId = ref('')
const logs = ref<WebhookDeliveryLog[]>([])

async function load() {
  loading.value = true
  try {
    const { data } = await webhookApi.list()
    webhooks.value = data.webhooks
  } finally {
    loading.value = false
  }
}

async function loadEventTypes() {
  try {
    const { data } = await webhookApi.eventTypes()
    eventTypes.value = data.event_types
  } catch {}
}

onMounted(async () => {
  await Promise.all([load(), loadEventTypes()])
})

function openCreate() {
  editingId.value = ''
  form.value = { url: '', name: '', events: [], secret: '', max_retries: 3, timeout_seconds: 10, description: '', is_active: true, headers: {} }
  showModal.value = true
}

function openEdit(w: WebhookConfig) {
  editingId.value = w.id
  form.value = { url: w.url, name: w.name, events: [...w.events], secret: '', max_retries: w.max_retries, timeout_seconds: w.timeout_seconds, description: w.description, is_active: w.is_active, headers: { ...w.headers } }
  showModal.value = true
}

async function save() {
  try {
    if (editingId.value) {
      await webhookApi.update(editingId.value, form.value)
    } else {
      await webhookApi.create(form.value)
    }
    showModal.value = false
    await load()
  } catch {}
}

async function remove(id: string) {
  if (!confirm('确认删除此 Webhook？')) return
  await webhookApi.delete(id)
  await load()
}

async function testWebhook(id: string) {
  try {
    testResult.value = (await webhookApi.test(id)).data
  } catch {}
}

async function toggleActive(w: WebhookConfig) {
  await webhookApi.update(w.id, { is_active: !w.is_active })
  await load()
}

async function viewLogs(webhookId: string) {
  showLogs.value = true
  logsWebhookId.value = webhookId
  try {
    const { data } = await webhookApi.logs(webhookId, 50)
    logs.value = data.logs
  } catch {}
}

function toggleEvent(event: string) {
  const idx = form.value.events.indexOf(event)
  if (idx >= 0) form.value.events.splice(idx, 1)
  else form.value.events.push(event)
}
</script>

<template>
  <div class="p-6 max-w-6xl mx-auto space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">Webhook 管理</h1>
        <p class="text-sm text-gray-400 mt-1">事件注册/触发/重试 · 对接外部系统</p>
      </div>
      <button @click="openCreate"
        class="px-4 py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-sm transition-colors">
        + 新建 Webhook
      </button>
    </div>

    <!-- List -->
    <div v-if="loading" class="text-gray-400 text-sm py-12 text-center">加载中...</div>

    <div v-else-if="!webhooks.length" class="text-gray-500 text-sm py-12 text-center bg-white/5 rounded-xl border border-white/10">
      暂无 Webhook，点击按钮创建
    </div>

    <div v-else class="space-y-3">
      <div v-for="w in webhooks" :key="w.id"
        class="bg-white/5 rounded-xl p-4 border transition-colors"
        :class="w.is_active ? 'border-white/10 hover:border-white/20' : 'border-red-500/20 opacity-60'">
        <div class="flex items-start justify-between">
          <div class="space-y-2 flex-1">
            <div class="flex items-center gap-3">
              <h3 class="text-sm font-semibold text-white">{{ w.name }}</h3>
              <span :class="['px-2 py-0.5 rounded text-xs', w.is_active ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400']">
                {{ w.is_active ? '活跃' : '停用' }}
              </span>
            </div>
            <p class="text-xs text-gray-400 font-mono">{{ w.url }}</p>
            <p v-if="w.description" class="text-xs text-gray-500">{{ w.description }}</p>
            <div class="flex flex-wrap gap-1.5">
              <span v-for="e in w.events" :key="e" class="px-2 py-0.5 rounded text-xs bg-brand-500/15 text-brand-300">{{ e }}</span>
            </div>
            <div class="flex items-center gap-4 text-xs text-gray-500">
              <span>成功: {{ w.success_count }}</span>
              <span>失败: {{ w.failure_count }}</span>
              <span v-if="w.last_triggered_at">上次触发: {{ new Date(w.last_triggered_at).toLocaleString() }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2 ml-4">
            <button @click="testWebhook(w.id)" class="px-3 py-1.5 rounded text-xs bg-white/10 hover:bg-white/20 text-gray-300 transition-colors">测试</button>
            <button @click="viewLogs(w.id)" class="px-3 py-1.5 rounded text-xs bg-white/10 hover:bg-white/20 text-gray-300 transition-colors">日志</button>
            <button @click="toggleActive(w)" class="px-3 py-1.5 rounded text-xs bg-white/10 hover:bg-white/20 text-gray-300 transition-colors">
              {{ w.is_active ? '停用' : '启用' }}
            </button>
            <button @click="openEdit(w)" class="px-3 py-1.5 rounded text-xs bg-white/10 hover:bg-white/20 text-gray-300 transition-colors">编辑</button>
            <button @click="remove(w.id)" class="px-3 py-1.5 rounded text-xs bg-red-500/10 hover:bg-red-500/20 text-red-400 transition-colors">删除</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Test Result -->
    <div v-if="testResult" class="bg-white/5 rounded-xl p-5 border border-white/10 space-y-3">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold text-white">测试结果</h3>
        <button @click="testResult = null" class="text-xs text-gray-400 hover:text-white">关闭</button>
      </div>
      <div class="grid grid-cols-3 gap-4 text-sm">
        <div class="bg-black/30 rounded-lg p-3">
          <p class="text-xs text-gray-500">状态</p>
          <p :class="testResult.success ? 'text-green-400' : 'text-red-400'">{{ testResult.success ? '✓ 成功' : '✗ 失败' }}</p>
        </div>
        <div class="bg-black/30 rounded-lg p-3">
          <p class="text-xs text-gray-500">HTTP 状态码</p>
          <p class="text-gray-200">{{ testResult.status }}</p>
        </div>
        <div class="bg-black/30 rounded-lg p-3">
          <p class="text-xs text-gray-500">延迟</p>
          <p class="text-gray-200">{{ testResult.latency_ms.toFixed(0) }}ms</p>
        </div>
      </div>
      <p v-if="testResult.error_message" class="text-sm text-red-400">{{ testResult.error_message }}</p>
    </div>

    <!-- Logs -->
    <div v-if="showLogs" class="bg-white/5 rounded-xl p-5 border border-white/10 space-y-3">
      <div class="flex items-center justify-between">
        <h3 class="text-sm font-semibold text-white">投递日志</h3>
        <button @click="showLogs = false" class="text-xs text-gray-400 hover:text-white">关闭</button>
      </div>
      <div class="max-h-64 overflow-auto space-y-1">
        <div v-for="l in logs" :key="l.id" class="flex items-center gap-3 text-xs py-2 border-b border-white/5">
          <span :class="l.success ? 'text-green-400' : 'text-red-400'">{{ l.success ? '✓' : '✗' }}</span>
          <span class="text-gray-400 w-28">{{ l.event_type }}</span>
          <span class="text-gray-500">HTTP {{ l.status }}</span>
          <span class="text-gray-500">attempt {{ l.attempt }}</span>
          <span class="text-gray-500">{{ l.latency_ms.toFixed(0) }}ms</span>
          <span class="text-gray-600 text-xs">{{ new Date(l.sent_at).toLocaleTimeString() }}</span>
          <span v-if="l.error_message" class="text-red-400 truncate max-w-xs">{{ l.error_message }}</span>
        </div>
      </div>
    </div>

    <!-- Modal -->
    <teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="showModal = false">
        <div class="bg-gray-900 rounded-xl border border-white/10 w-full max-w-lg mx-4 max-h-[85vh] overflow-auto p-6 space-y-4">
          <h2 class="text-lg font-bold text-white">{{ editingId ? '编辑' : '新建' }} Webhook</h2>

          <label class="block space-y-1">
            <span class="text-xs text-gray-400">名称</span>
            <input v-model="form.name"
              class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-brand-500"
              placeholder="我的 Webhook" />
          </label>

          <label class="block space-y-1">
            <span class="text-xs text-gray-400">回调 URL</span>
            <input v-model="form.url"
              class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 font-mono focus:outline-none focus:border-brand-500"
              placeholder="https://my-service.com/webhook" />
          </label>

          <div class="space-y-1">
            <span class="text-xs text-gray-400">订阅事件</span>
            <div class="flex flex-wrap gap-1.5 max-h-32 overflow-auto">
              <button v-for="e in eventTypes" :key="e.value" @click="toggleEvent(e.value)" :title="e.description"
                :class="['px-2.5 py-1 rounded text-xs transition-colors', form.events.includes(e.value) ? 'bg-brand-600 text-white' : 'bg-white/10 text-gray-400 hover:bg-white/20']">
                {{ e.name }}
              </button>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <label class="space-y-1">
              <span class="text-xs text-gray-400">最大重试</span>
              <input v-model.number="form.max_retries" type="number" min="0" max="10"
                class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none" />
            </label>
            <label class="space-y-1">
              <span class="text-xs text-gray-400">超时 (秒)</span>
              <input v-model.number="form.timeout_seconds" type="number" min="1" max="60"
                class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none" />
            </label>
          </div>

          <label class="block space-y-1">
            <span class="text-xs text-gray-400">描述</span>
            <input v-model="form.description"
              class="w-full bg-black/30 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-brand-500" />
          </label>

          <label class="flex items-center gap-2">
            <input v-model="form.is_active" type="checkbox" class="accent-brand-500" />
            <span class="text-sm text-gray-300">创建后立即启用</span>
          </label>

          <div class="flex gap-3 pt-2">
            <button @click="save"
              class="flex-1 py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-sm transition-colors">保存</button>
            <button @click="showModal = false"
              class="flex-1 py-2.5 rounded-lg bg-white/10 hover:bg-white/20 text-gray-300 text-sm transition-colors">取消</button>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>
