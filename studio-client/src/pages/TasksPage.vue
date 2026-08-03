<template>
  <div class="tasks-page">
    <header class="page-header"><div><ListTodo class="h-5 w-5"/><h2>任务管理</h2></div>
      <div class="h-actions"><button class="btn btn-ghost btn-sm" @click="autoDetect"><Search class="h-4 w-4"/>自动检测</button><button class="btn btn-primary btn-sm" @click="showCreate=true"><Plus class="h-4 w-4"/>新建</button><button class="btn btn-ghost btn-sm" @click="refreshAll"><RefreshCw :class="['h-4 w-4',{spin:loading}]"/>刷新</button></div>
    </header>

    <!-- 任务配置表格 -->
    <div class="table-wrap">
      <table><thead><tr><th>名称</th><th>类型</th><th>命令</th><th>构建</th><th>测试</th><th>操作</th></tr></thead>
      <tbody><tr v-for="t in tasks" :key="t.name">
        <td class="fw6">{{t.label||t.name}}</td><td><span class="tag">{{t.type}}</span></td>
        <td class="mono">{{t.command}}</td><td>{{t.is_build?'✔':''}}</td><td>{{t.is_test?'✔':''}}</td>
        <td class="td-actions">
          <button class="btn btn-ghost btn-sm" @click="run(t.name)">▶ 运行</button>
          <button class="btn btn-ghost btn-sm" @click="editTask(t)">编辑</button>
          <button class="btn btn-ghost btn-sm" @click="doDelete(t.name)">删除</button>
        </td>
      </tr></tbody></table></div>

    <!-- 队列面板 -->
    <h3 style="margin-top:24px">任务队列</h3>
    <div class="queue-stats" v-if="qStats">
      <div class="qs-item"><span class="qs-label">活跃任务</span><span class="qs-val">{{qStats.active||0}}</span></div>
      <div class="qs-item"><span class="qs-label">Worker 数</span><span class="qs-val">{{qStats.workers||0}}</span></div>
    </div>
    <div class="table-wrap" v-if="qTasks.length">
      <table><thead><tr><th>ID</th><th>名称</th><th>状态</th><th>Worker</th><th>创建时间</th><th>操作</th></tr></thead>
      <tbody><tr v-for="q in qTasks" :key="q.task_id">
        <td class="mono">{{q.task_id.slice(0,8)}}</td><td>{{q.name}}</td>
        <td><span :class="['q-status',q.status]">{{q.status}}</span></td><td>{{q.worker||'—'}}</td><td>{{q.started_at||q.created_at}}</td>
        <td><button class="btn btn-sm btn-ghost" @click="revokeTask(q.task_id)" v-if="q.status==='STARTED'||q.status==='PENDING'">撤销</button></td>
      </tr></tbody></table></div>

    <!-- 输出弹窗 -->
    <Teleport to="body" v-if="output">
      <div class="modal-mask" @click.self="output=null"><div class="modal-box wide">
        <div class="modal-h"><span>输出 — {{outputName}}</span><button class="btn btn-ghost btn-sm" @click="output=null">✕</button></div>
        <pre class="output">{{output}}</pre>
      </div></div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import { ListTodo, Search, Plus, RefreshCw, Play } from "lucide-vue-next"
import { listTasks, createTask, updateTask, deleteTask, runTask, getExecutionOutput, cancelExecution, autoDetectTasks, taskQueueStats, taskQueueActive, taskQueueRevoke, TaskDefinition, QueueStats, QueueTask } from "@/api/tasks"

const tasks=ref<TaskDefinition[]>([]), qTasks=ref<QueueTask[]>([]), qStats=ref<Record<string,unknown>|null>(null)
const loading=ref(false), showCreate=ref(false), output=ref<string|null>(null), outputName=ref("")

async function load(){loading.value=true;try{tasks.value=(await listTasks()).data||[]}catch{}finally{loading.value=false}}
async function loadQ(){try{const[s,a]=await Promise.all([taskQueueStats(),taskQueueActive()]);qStats.value=s.data?.queue_stats||{} as any;qTasks.value=a.data||[]}catch{}}
async function refreshAll(){await Promise.all([load(),loadQ()])}
async function run(name:string){try{const r=await runTask(name);let id=r.data?.execution_id;if(!id)return;await new Promise(r=>setTimeout(r,1000));const o=await getExecutionOutput(id);output.value=o.data?.stdout||o.data?.stderr||'';outputName.value=name}catch{}}
async function doDelete(name:string){if(!confirm('删除任务 "'+name+'"？'))return;try{await deleteTask(name);load()}catch{}}
async function autoDetect(){try{await autoDetectTasks();load()}catch{}}
async function revokeTask(id:string){try{await taskQueueRevoke(id);loadQ()}catch{}}
function editTask(t:TaskDefinition){/* TODO */}

onMounted(refreshAll)
</script>

<style scoped>
.tasks-page{padding:20px}.page-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}.page-header>div{display:flex;align-items:center;gap:8px}.page-header h2{font-size:18px;margin:0}.h-actions{display:flex;gap:8px}.table-wrap{overflow-x:auto;border:1px solid var(--color-ide-border);border-radius:10px;background:var(--color-ide-bg)}.table-wrap table{width:100%;border-collapse:collapse;font-size:13px}.table-wrap th{text-align:left;padding:10px 12px;border-bottom:2px solid var(--color-ide-border);color:var(--color-ide-text-secondary);font-size:11px}.table-wrap td{padding:9px 12px;border-bottom:1px solid var(--color-ide-border);vertical-align:middle}.fw6{font-weight:600}.mono{font-family:monospace;font-size:12px}.tag{font-size:10px;padding:2px 6px;border-radius:99px;background:var(--color-ide-surface);color:var(--color-ide-text-secondary)}.td-actions{display:flex;gap:4px}.queue-stats{display:flex;gap:16px;padding:12px 16px;margin:8px 0 12px;background:var(--color-ide-bg);border:1px solid var(--color-ide-border);border-radius:10px}.qs-item{display:flex;flex-direction:column;gap:2px}.qs-label{font-size:11px;color:var(--color-ide-text-secondary)}.qs-val{font-size:18px;font-weight:700}.q-status{font-size:10px;padding:1px 6px;border-radius:99px}.q-status.STARTED,.q-status.running{background:#0596691a;color:#059669}.q-status.PENDING,.q-status.pending{background:#f59e0b1a;color:#f59e0b}.q-status.FAILURE,.q-status.failed{background:#dc26261a;color:#dc2626}.q-status.SUCCESS,.q-status.completed{background:#6366f11a;color:#6366f1}.modal-mask{position:fixed;inset:0;z-index:999;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center}.modal-box{background:var(--color-ide-bg);border:1px solid var(--color-ide-border);border-radius:12px;padding:20px;min-width:420px;max-width:720px;max-height:80vh;overflow-y:auto}.modal-box.wide{width:720px}.modal-h{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;font-weight:600}.output{white-space:pre-wrap;font-family:monospace;font-size:12px;max-height:60vh;overflow-y:auto;padding:12px;background:var(--color-ide-surface);border-radius:8px}.btn{display:inline-flex;align-items:center;gap:4px;border:none;cursor:pointer;border-radius:8px;font-size:13px;padding:8px 14px}.btn-primary{background:var(--color-ide-accent);color:#fff}.btn-ghost{background:transparent}.btn-sm{padding:4px 8px;font-size:12px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
</style>
