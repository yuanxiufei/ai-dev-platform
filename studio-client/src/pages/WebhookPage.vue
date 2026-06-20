<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { webhookApi, type WebhookConfig, type WebhookTestResult, type WebhookDeliveryLog } from '@/api/model-features'
import { Webhook, Plus, RefreshCw, Trash2, Play, List } from 'lucide-vue-next'

const webhooks = ref<WebhookConfig[]>([])
const loading = ref(true)

const showModal = ref(false)
const editingId = ref('')
const form = ref({ url: '', name: '', events: [] as string[], description: '', is_active: true, max_retries: 3, timeout_seconds: 10 })

const testResult = ref<WebhookTestResult | null>(null)
const showLogs = ref(false)
const logs = ref<WebhookDeliveryLog[]>([])
const logsWebhookId = ref('')

const eventTypes = ref<{ value: string; name: string; description: string }[]>([])

async function load() {
  loading.value = true
  try { const { data } = await webhookApi.list(); webhooks.value = data.webhooks }
  finally { loading.value = false }
}

async function loadTypes() {
  try { eventTypes.value = (await apiClient.get('/webhooks/event-types')).data.event_types } catch {}
}
async function save() {
  try {
    if (editingId.value) await webhookApi.update(editingId.value, form.value)
    else await webhookApi.create(form.value)
    showModal.value = false; await load()
  } catch {}
}

function openCreate() {
  editingId.value = ''
  form.value = { url: '', name: '', events: [], description: '', is_active: true, max_retries: 3, timeout_seconds: 10 }
  showModal.value = true
}
function openEdit(w: WebhookConfig) {
  editingId.value = w.id
  form.value = { url: w.url, name: w.name, events: [...w.events], description: w.description, is_active: w.is_active, max_retries: w.max_retries, timeout_seconds: w.timeout_seconds }
  showModal.value = true
}
function toggleEvent(evt: string) {
  const i = form.value.events.indexOf(evt); i >= 0 ? form.value.events.splice(i, 1) : form.value.events.push(evt)
}

async function remove(id: string) {
  if (!confirm('确认删除？')) return
  await webhookApi.delete(id); await load()
}
async function testWebhook(id: string) {
  try { testResult.value = (await webhookApi.test(id)).data }
  catch {}
}
async function viewLogs(id: string) {
  showLogs.value = true; logsWebhookId.value = id
  try { const { data } = await webhookApi.logs(id); logs.value = data.logs }
  catch {}
}

import apiClient from '@/api/client'
onMounted(async () => { await Promise.all([load(), loadTypes()]) })
</script>

<template>
  <div class="p-6 max-w-5xl mx-auto space-y-6">
    <header class="flex items-center justify-between">
      <div>
        <h1 class="text-3xl font-bold text-white">Webhook 管理</h1>
        <p class="text-gray-400 mt-2">事件注册 · 外部系统回调</p>
      </div>
      <button @click="openCreate" class="px-4 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 text-white font-medium flex items-center gap-2 text-sm">
        <Plus class="w-4 h-4" /> 新建
      </button>
    </header>

    <div v-if="loading" class="text-center py-12 text-gray-500">加载中...</div>
    <div v-else-if="!webhooks.length" class="text-center py-16 text-gray-500 bg-gray-900/50 rounded-2xl border border-gray-800/50">
      <Webhook class="w-10 h-10 mx-auto mb-3 text-gray-600" />
      <p>暂无 Webhook，点击按钮创建</p>
    </div>
    <div v-else class="space-y-3">
      <div v-for="w in webhooks" :key="w.id" class="bg-gray-900/50 rounded-2xl p-5 border" :class="w.is_active ? 'border-gray-800/50' : 'border-red-500/20 opacity-60'">
        <div class="flex items-start justify-between">
          <div class="space-y-2 flex-1">
            <div class="flex items-center gap-3">
              <h3 class="font-semibold text-white">{{ w.name }}</h3>
              <span :class="['px-2 py-0.5 rounded-full text-xs', w.is_active ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400']">{{ w.is_active ? '活跃' : '停用' }}</span>
            </div>
            <p class="text-xs text-gray-400 font-mono">{{ w.url }}</p>
            <div class="flex flex-wrap gap-1.5">
              <span v-for="e in w.events" :key="e" class="px-2 py-0.5 rounded-full text-xs bg-brand-500/15 text-brand-300">{{ e }}</span>
            </div>
            <div class="flex items-center gap-4 text-xs text-gray-500">
              <span>成功 {{ w.success_count }} · 失败 {{ w.failure_count }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2 ml-4">
            <button @click="testWebhook(w.id)" class="px-3 py-1.5 rounded-lg text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 transition">测试</button>
            <button @click="viewLogs(w.id)" class="px-3 py-1.5 rounded-lg text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 transition">日志</button>
            <button @click="openEdit(w)" class="px-3 py-1.5 rounded-lg text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 transition">编辑</button>
            <button @click="remove(w.id)" class="px-3 py-1.5 rounded-lg text-xs bg-red-500/10 hover:bg-red-500/20 text-red-400 transition">删除</button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="testResult" class="bg-gray-900/50 rounded-2xl p-5 border border-gray-800/50">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-semibold text-white">测试结果</h3>
        <button @click="testResult = null" class="text-xs text-gray-400">关闭</button>
      </div>
      <div class="grid grid-cols-3 gap-4 text-sm">
        <div class="bg-gray-800/50 rounded-xl p-3"><p class="text-xs text-gray-500">状态</p><p :class="testResult.success ? 'text-green-400' : 'text-red-400'">{{ testResult.success ? '✓ 成功' : '✗ 失败' }}</p></div>
        <div class="bg-gray-800/50 rounded-xl p-3"><p class="text-xs text-gray-500">HTTP</p><p class="text-gray-200">{{ testResult.status }}</p></div>
        <div class="bg-gray-800/50 rounded-xl p-3"><p class="text-xs text-gray-500">延迟</p><p class="text-gray-200">{{ testResult.latency_ms.toFixed(0) }}ms</p></div>
      </div>
    </div>

    <div v-if="showLogs" class="bg-gray-900/50 rounded-2xl p-5 border border-gray-800/50">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-semibold text-white">投递日志</h3>
        <button @click="showLogs = false" class="text-xs text-gray-400">关闭</button>
      </div>
      <div class="max-h-64 overflow-auto space-y-1">
        <div v-for="l in logs" :key="l.id" class="flex items-center gap-3 text-xs py-2 border-b border-gray-800/30">
          <span :class="l.success ? 'text-green-400' : 'text-red-400'">{{ l.success ? '✓' : '✗' }}</span>
          <span class="text-gray-400 w-28">{{ l.event_type }}</span>
          <span class="text-gray-500">HTTP {{ l.status }} · {{ l.latency_ms.toFixed(0) }}ms</span>
          <span class="text-gray-600">{{ new Date(l.sent_at).toLocaleTimeString() }}</span>
        </div>
      </div>
    </div>

    <!-- Modal -->
    <Teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="showModal = false">
        <div class="bg-gray-900 rounded-2xl border border-gray-800 w-full max-w-lg mx-4 max-h-[85vh] overflow-auto p-6 space-y-4">
          <h2 class="text-lg font-bold text-white">{{ editingId ? '编辑' : '新建' }} Webhook</h2>
          <label class="block space-y-1"><span class="text-xs text-gray-400">名称</span><input v-model="form.name" class="w-full bg-gray-800 border border-gray-700/50 rounded-xl px-3 py-2 text-sm text-gray-200 outline-none" /></label>
          <label class="block space-y-1"><span class="text-xs text-gray-400">URL</span><input v-model="form.url" class="w-full bg-gray-800 border border-gray-700/50 rounded-xl px-3 py-2 text-sm text-gray-200 font-mono outline-none" /></label>
          <div class="space-y-1"><span class="text-xs text-gray-400">事件</span>
            <div class="flex flex-wrap gap-1.5"><button v-for="e in eventTypes" :key="e.value" @click="toggleEvent(e.value)" :class="['px-2.5 py-1 rounded-lg text-xs', form.events.includes(e.value) ? 'bg-brand-500 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700']">{{ e.name }}</button></div>
          </div>
          <div class="flex gap-3 pt-2"><button @click="save" class="flex-1 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 text-white font-medium">保存</button><button @click="showModal = false" class="flex-1 py-2.5 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300">取消</button></div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
