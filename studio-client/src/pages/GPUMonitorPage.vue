<template>
  <div class="gpu-page">
    <header class="page-header"><div><Cpu class="h-5 w-5"/><h2>GPU 监控</h2></div>
      <button class="btn btn-ghost btn-sm" @click="refresh" :disabled="refreshing"><RefreshCw :class="['h-4 w-4',{spin:refreshing}]"/>{{status?.timestamp?'刷新':'加载'}}</button>
    </header>

    <div v-if="status" class="summary-bar">
      <div class="sm-item"><span class="sm-label">设备数</span><span class="sm-val">{{status.device_count}}</span></div>
      <div class="sm-item"><span class="sm-label">总显存</span><span class="sm-val">{{(status.summary.total_memory_mb/1024).toFixed(1)}} GB</span></div>
      <div class="sm-item"><span class="sm-label">已用</span><span class="sm-val">{{(status.summary.used_memory_mb/1024).toFixed(1)}} GB</span></div>
      <div class="sm-item"><span class="sm-label">平均利用率</span><span class="sm-val">{{status.summary.avg_utilization}}%</span></div>
      <div class="sm-item"><span class="sm-label">最高温度</span><span class="sm-val">{{status.summary.max_temperature}}°C</span></div>
    </div>

    <div class="devices-grid">
      <div v-for="d in devices" :key="d.index" class="device-card">
        <div class="dc-header">
          <span class="dc-name">GPU {{d.index}}: {{d.name}}</span>
          <span :class="['dc-status',d.utilization_gpu>80?'hot':d.utilization_gpu>50?'warm':'idle']">
            {{d.utilization_gpu}}%</span>
        </div>
        <div class="mem-bar"><div class="mem-fill" :style="{width:(d.memory_used_mb/d.memory_total_mb*100)+'%'}"/></div>
        <div class="mem-text">{{(d.memory_used_mb/1024).toFixed(1)}} / {{(d.memory_total_mb/1024).toFixed(1)}} GB</div>
        <div class="dc-stats">
          <span>🌡 {{d.temperature_c}}°C</span><span>⚡ {{d.power_w}}/{{d.power_limit_w}}W</span>
          <span>🕐 {{d.clock_mhz}}MHz</span><span>🌀 {{d.fan_speed}}%</span>
        </div>
      </div>
      <div v-if="!devices.length" class="empty">未检测到 GPU 设备</div>
    </div>

    <h3 v-if="allocations.length" style="margin-top:24px">GPU 分配</h3>
    <table v-if="allocations.length" class="alloc-table">
      <thead><tr><th>ID</th><th>GPU</th><th>进程</th><th>PID</th><th>显存</th><th>启动时间</th><th>状态</th><th>操作</th></tr></thead>
      <tbody><tr v-for="a in allocations" :key="a.id">
        <td class="mono">{{a.id.slice(0,8)}}</td><td>GPU {{a.device_index}}</td><td>{{a.process_name}}</td><td>{{a.pid}}</td>
        <td>{{a.memory_mb}} MB</td><td>{{a.started_at}}</td>
        <td><span :class="['a-status',a.status]">{{a.status}}</span></td>
        <td><button class="btn btn-sm btn-ghost" @click="release(a.id)" :disabled="a.status==='finished'">释放</button></td>
      </tr></tbody>
    </table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import { Cpu, RefreshCw } from "lucide-vue-next"
import { listGPUDevices, listAllocations, gpuStatus, releaseAllocation, GPUDevice, GPUAllocation, GPUStatus } from "@/api/gpuMonitor"

const devices=ref<GPUDevice[]>([]),allocations=ref<GPUAllocation[]>([]),status=ref<GPUStatus|null>(null),refreshing=ref(false)
async function refresh(){refreshing.value=true;try{const[d,a,s]=await Promise.all([listGPUDevices(),listAllocations(),gpuStatus()]);devices.value=d.data||[];allocations.value=a.data||[];status.value=s.data}catch{}finally{refreshing.value=false}}
async function release(id:string){try{await releaseAllocation(id);allocations.value=allocations.value.filter(a=>a.id!==id)}catch{}}
onMounted(refresh)
</script>

<style scoped>
.gpu-page{padding:20px}.page-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}.page-header>div{display:flex;align-items:center;gap:8px}.page-header h2{font-size:18px;margin:0}
.summary-bar{display:flex;gap:16px;padding:14px 18px;background:var(--color-ide-bg);border:1px solid var(--color-ide-border);border-radius:10px;margin-bottom:16px;flex-wrap:wrap}.sm-item{display:flex;flex-direction:column;gap:2px}.sm-label{font-size:11px;color:var(--color-ide-text-secondary)}.sm-val{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums}
.devices-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}.device-card{padding:14px;border:1px solid var(--color-ide-border);border-radius:10px;background:var(--color-ide-bg)}.dc-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}.dc-name{font-weight:600;font-size:13px}.dc-status{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums;padding:2px 8px;border-radius:6px}.dc-status.hot{background:#dc26261a;color:#dc2626}.dc-status.warm{background:#f59e0b1a;color:#f59e0b}.dc-status.idle{background:#0596691a;color:#059669}.mem-bar{height:8px;background:var(--color-ide-surface);border-radius:4px;overflow:hidden;margin-bottom:4px}.mem-fill{height:100%;background:var(--color-ide-accent);border-radius:4px;transition:width .3s}.mem-text{font-size:12px;color:var(--color-ide-text-secondary);margin-bottom:8px}.dc-stats{display:flex;gap:10px;font-size:11px;flex-wrap:wrap}
.alloc-table{width:100%;border-collapse:collapse;font-size:13px;margin-top:8px}.alloc-table th{text-align:left;padding:8px 10px;border-bottom:2px solid var(--color-ide-border);color:var(--color-ide-text-secondary)}.alloc-table td{padding:8px 10px;border-bottom:1px solid var(--color-ide-border)}.mono{font-family:monospace;font-size:12px}.a-status{font-size:11px;padding:1px 6px;border-radius:99px}.a-status.running{background:#0596691a;color:#059669}.a-status.error{background:#dc26261a;color:#dc2626}.a-status.finished{background:var(--color-ide-surface);color:var(--color-ide-text-secondary)}.empty{text-align:center;padding:40px;color:var(--color-ide-text-secondary)}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
.btn{display:inline-flex;align-items:center;gap:4px;border:none;cursor:pointer;border-radius:8px;font-size:13px;padding:8px 14px}.btn-ghost{background:transparent}.btn-sm{padding:4px 8px;font-size:12px}
</style>
