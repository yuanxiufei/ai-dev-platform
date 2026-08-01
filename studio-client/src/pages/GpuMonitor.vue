<template>
  <div class="gpu-monitor-page">
    <div class="page-header">
      <h2>GPU 监控</h2>
      <p class="subtitle">设备列表、显存分配与状态摘要</p>
    </div>

    <div class="toolbar">
      <button class="btn btn-primary" @click="refreshAll">刷新</button>
      <span class="auto-refresh">
        <label>
          <input type="checkbox" v-model="autoRefresh" @change="toggleAutoRefresh" />
          自动刷新 (5s)
        </label>
      </span>
    </div>

    <!-- 状态摘要 -->
    <div class="section" v-if="status">
      <h3>状态摘要</h3>
      <div class="status-grid">
        <div class="status-card">
          <span class="status-val">{{ status.total_devices ?? '—' }}</span>
          <span class="status-label">设备数</span>
        </div>
        <div class="status-card">
          <span class="status-val">{{ formatMem(status.total_memory_mb) }}</span>
          <span class="status-label">总显存</span>
        </div>
        <div class="status-card">
          <span class="status-val">{{ formatMem(status.free_memory_mb) }}</span>
          <span class="status-label">空闲显存</span>
        </div>
        <div class="status-card">
          <span class="status-val">{{ status.used_memory_mb != null ? ((status.used_memory_mb / status.total_memory_mb) * 100).toFixed(1) + '%' : '—' }}</span>
          <span class="status-label">利用率</span>
        </div>
      </div>
    </div>

    <!-- GPU 设备 -->
    <div class="section">
      <h3>GPU 设备</h3>
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="devices.length === 0" class="empty">未检测到 GPU 设备</div>
      <div v-else class="device-grid">
        <div v-for="d in devices" :key="d.index ?? d.id" class="device-card"
             :class="{ 'device-warn': d.temperature > 80, 'device-offline': !d.online }">
          <div class="device-header">
            <span class="device-name">GPU {{ d.index ?? d.id }} — {{ d.name || 'Unknown' }}</span>
            <span :class="['badge', d.online !== false ? 'badge-ok' : 'badge-error']">
              {{ d.online !== false ? '在线' : '离线' }}
            </span>
          </div>
          <div class="device-bars">
            <div class="mem-bar">
              <div class="bar-label">
                <span>显存 {{ formatMem(d.memory_used_mb) }} / {{ formatMem(d.memory_total_mb) }}</span>
                <span>{{ d.memory_total_mb ? ((d.memory_used_mb / d.memory_total_mb) * 100).toFixed(1) : 0 }}%</span>
              </div>
              <div class="progress-bar">
                <div class="progress-fill mem-fill"
                     :style="{ width: d.memory_total_mb ? ((d.memory_used_mb / d.memory_total_mb) * 100) + '%' : '0%' }"></div>
              </div>
            </div>
            <div class="util-bar">
              <div class="bar-label">
                <span>GPU 利用率</span>
                <span>{{ d.utilization_gpu ?? 0 }}%</span>
              </div>
              <div class="progress-bar">
                <div class="progress-fill util-fill"
                     :style="{ width: (d.utilization_gpu ?? 0) + '%' }"></div>
              </div>
            </div>
          </div>
          <div class="device-meta">
            <span v-if="d.temperature != null">温度 {{ d.temperature }}°C</span>
            <span v-if="d.power_watts != null">功耗 {{ d.power_watts }}W</span>
            <span v-if="d.fan_speed != null">风扇 {{ d.fan_speed }}%</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 显存分配 -->
    <div class="section">
      <h3>显存分配</h3>
      <div v-if="allocations.length === 0" class="empty">当前无活跃分配</div>
      <div v-else class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>分配 ID</th>
              <th>GPU</th>
              <th>进程</th>
              <th>占用</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="a in allocations" :key="a.id || a.allocation_id">
              <td class="mono">{{ a.id || a.allocation_id }}</td>
              <td>GPU {{ a.gpu_index ?? '—' }}</td>
              <td>{{ a.process_name || '—' }} ({{ a.pid ?? '—' }})</td>
              <td>{{ formatMem(a.memory_mb) }}</td>
              <td>
                <button class="btn btn-sm btn-danger" @click="releaseAllocation(a.id || a.allocation_id)">释放</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { gpuApi } from '@/api/gpu'

const devices = ref<any[]>([])
const allocations = ref<any[]>([])
const status = ref<any>(null)
const loading = ref(false)
const autoRefresh = ref(false)
let refreshTimer: number | null = null

function formatMem(mb?: number) {
  if (mb == null || isNaN(mb)) return '—'
  return mb >= 1024 ? (mb / 1024).toFixed(1) + ' GB' : mb.toFixed(0) + ' MB'
}

async function fetchDevices() {
  loading.value = true
  try {
    const res = await gpuApi.listDevices()
    devices.value = res.data?.devices ?? res.data ?? []
  } finally {
    loading.value = false
  }
}

async function fetchAllocations() {
  try {
    const res = await gpuApi.listAllocations()
    allocations.value = res.data?.allocations ?? res.data ?? []
  } catch { /* empty */ }
}

async function fetchStatus() {
  try {
    const res = await gpuApi.getStatus()
    status.value = res.data ?? null
  } catch { /* empty */ }
}

async function refreshAll() {
  await Promise.all([fetchDevices(), fetchAllocations(), fetchStatus()])
}

async function releaseAllocation(id: string) {
  if (!confirm(`确认释放分配 "${id}"？`)) return
  try {
    await gpuApi.releaseAllocation(id)
    fetchAllocations()
  } catch { /* empty */ }
}

function toggleAutoRefresh() {
  if (autoRefresh.value) {
    refreshTimer = window.setInterval(refreshAll, 5000)
  } else {
    if (refreshTimer) { clearInterval(refreshTimer); refreshTimer = null }
  }
}

onMounted(() => refreshAll())
onUnmounted(() => { if (refreshTimer) clearInterval(refreshTimer) })
</script>

<style scoped>
.gpu-monitor-page { padding: 24px; }
.page-header { margin-bottom: 20px; }
.page-header h2 { margin: 0; font-size: 20px; }
.subtitle { color: var(--color-ide-fg-secondary); margin: 4px 0 0; font-size: 13px; }

.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }
.auto-refresh { font-size: 13px; color: var(--color-ide-fg-secondary); }
.auto-refresh input { vertical-align: middle; margin-right: 4px; }

.section { margin-bottom: 28px; }
.section h3 { margin: 0 0 12px; font-size: 16px; }

.status-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
.status-card { border: 1px solid var(--color-ide-border); border-radius: 8px; padding: 14px; text-align: center; }
.status-val { display: block; font-size: 22px; font-weight: 700; }
.status-label { font-size: 12px; color: var(--color-ide-fg-secondary); margin-top: 4px; display: block; }

.device-grid { display: grid; gap: 12px; }
.device-card { border: 1px solid var(--color-ide-border); border-radius: 8px; padding: 16px; }
.device-warn { border-color: #d4a72c; }
.device-offline { opacity: 0.5; }
.device-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.device-name { font-weight: 600; font-size: 15px; }
.device-bars { display: flex; flex-direction: column; gap: 8px; margin-bottom: 8px; }
.bar-label { display: flex; justify-content: space-between; font-size: 12px; color: var(--color-ide-fg-secondary); margin-bottom: 3px; }
.device-meta { display: flex; gap: 16px; font-size: 12px; color: var(--color-ide-fg-secondary); }

.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--color-ide-border); }
th { font-size: 12px; color: var(--color-ide-fg-secondary); font-weight: 600; }
.mono { font-family: monospace; font-size: 12px; }

.loading, .empty { padding: 32px 0; text-align: center; color: var(--color-ide-fg-secondary); }

.progress-bar { height: 8px; background: var(--color-ide-bg-secondary); border-radius: 4px; overflow: hidden; }
.progress-fill { height: 100%; border-radius: 4px; transition: width 0.4s; }
.mem-fill { background: linear-gradient(90deg, #4fc1ff, #4090e0); }
.util-fill { background: linear-gradient(90deg, #1a7f37, #4fc1ff); }

.badge { padding: 2px 8px; border-radius: 10px; font-size: 11px; }
.badge-ok { background: #1a7f3711; color: #1a7f37; }
.badge-error { background: #cf222e11; color: #cf222e; }

.input { background: var(--color-ide-bg-secondary); border: 1px solid var(--color-ide-border); border-radius: 6px; padding: 6px 10px; font-size: 13px; color: var(--color-ide-fg); }
.input-sm { width: 100px; }
.btn { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid var(--color-ide-border); background: var(--color-ide-bg); color: var(--color-ide-fg); }
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--color-ide-accent, #4fc1ff); color: #fff; border-color: var(--color-ide-accent, #4fc1ff); }
.btn-outline { background: transparent; border-color: var(--color-ide-border); }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-danger { color: #cf222e; border-color: #cf222e; background: transparent; }
</style>
