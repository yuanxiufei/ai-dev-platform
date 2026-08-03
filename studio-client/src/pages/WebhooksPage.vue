<template>
  <div class="wh-page">
    <header class="page-header"><div><Webhook class="h-5 w-5"/><h2>Webhook 管理</h2></div>
      <div class="h-actions"><button class="btn btn-primary btn-sm" @click="showCreate=true"><Plus class="h-4 w-4"/>新建</button><button class="btn btn-ghost btn-sm" @click="load"><RefreshCw :class="['h-4 w-4',{spin:loading}]"/></button></div>
    </header>

    <!-- 卡片网格 -->
    <div class="cards"><div v-for="w in webhooks" :key="w.id" class="card">
      <div class="c-head"><div class="c-name"><span class="c-dot" :class="{active:w.is_active}"/>{{w.name}}</div><div class="c-actions"><button class="btn btn-ghost btn-sm" @click="doTest(w.id)">测试</button><button class="btn btn-ghost btn-sm" @click="editWh(w)">编辑</button><button class="btn btn-ghost btn-sm" @click="doDel(w.id)">删除</button></div></div>
      <div class="c-url mono">{{w.url}}</div>
      <div class="c-events"><span v-for="e in w.events" :key="e" class="tag">{{e}}</span></div>
      <div class="c-stats"><span>成功 {{w.success_count}}</span><span>失败 {{w.failure_count}}</span><span>最后触发 {{w.last_triggered_at||'—'}}</span></div>
    </div></div>

    <!-- 事件类型 -->
    <h3 style="margin-top:24px">事件类型</h3>
    <div class="events-grid"><span v-for="e in eventTypes" :key="e.value" class="ev-tag" :title="e.description">{{e.name}}</span></div>

    <!-- 投递日志 -->
    <h3 style="margin-top:24px">投递日志</h3>
    <div class="table-wrap" v-if="logs.length">
      <table><thead><tr><th>时间</th><th>事件</th><th>URL</th><th>状态</th><th>延迟</th><th>重试</th><th>错误</th></tr></thead>
      <tbody><tr v-for="l in logs" :key="l.id">
        <td class="mono">{{l.sent_at?.slice(0,19)||''}}</td><td>{{l.event_type}}</td><td class="mono ellip">{{l.url}}</td>
        <td :class="l.success?'ok':'err'">{{l.status}}</td><td>{{l.latency_ms}}ms</td><td>{{l.attempt}}</td>
        <td class="ellip" style="max-width:200px">{{l.error_message||''}}</td>
      </tr></tbody></table></div>

    <!-- 创建/编辑弹窗 -->
    <Teleport to="body" v-if="showCreate||edit">
      <div class="modal-mask" @click.self="showCreate=false;edit=null"><div class="modal-box">
        <div class="modal-h"><span>{{edit?'编辑 Webhook':'新建 Webhook'}}</span><button class="btn btn-ghost btn-sm" @click="showCreate=false;edit=null">✕</button></div>
        <div class="form"><label>名称<input v-model="f.name" class="input"/></label><label>URL<input v-model="f.url" class="input"/></label><label>事件 (逗号分隔)<input v-model="f.eventsStr" class="input" placeholder="agent.started,agent.completed"/></label><label>密钥 (可选)<input v-model="f.secret" type="password" class="input"/></label><label>最大重试次数<input v-model.number="f.max_retries" type="number" class="input"/></label><label>超时 (秒)<input v-model.number="f.timeout_seconds" type="number" class="input"/></label></div>
        <div style="text-align:right;margin-top:12px"><button class="btn btn-primary btn-sm" @click="submit">{{edit?'更新':'创建'}}</button></div>
      </div></div>
    </Teleport>

    <!-- 测试结果弹窗 -->
    <Teleport to="body" v-if="testR"><div class="modal-mask" @click.self="testR=null"><div class="modal-box">
      <div class="modal-h"><span>测试结果</span><button class="btn btn-ghost btn-sm" @click="testR=null">✕</button></div>
      <div><strong>状态:</strong> <span :class="testR.success?'ok':'err'">{{testR.success?'成功':'失败'}}</span></div>
      <div><strong>HTTP 状态:</strong> {{testR.status}}</div><div><strong>延迟:</strong> {{testR.latency_ms}}ms</div>
      <div v-if="testR.error_message"><strong>错误:</strong> {{testR.error_message}}</div>
    </div></div></Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import { Webhook, Plus, RefreshCw } from "lucide-vue-next"
import { listWebhooks, listEventTypes, createWebhook, updateWebhook, deleteWebhook, testWebhook, getDeliveryLogs, WebhookRegistration, EventType, DeliveryLog, TestResult } from "@/api/webhooks"

const webhooks=ref<WebhookRegistration[]>([]), eventTypes=ref<EventType[]>([]), logs=ref<DeliveryLog[]>([])
const loading=ref(false), showCreate=ref(false), edit=ref<WebhookRegistration|null>(null), testR=ref<TestResult|null>(null)
const f=ref({name:"",url:"",eventsStr:"",secret:"",max_retries:3,timeout_seconds:30})

async function load(){loading.value=true;try{const[w,e,l]=await Promise.all([listWebhooks(),listEventTypes(),getDeliveryLogs({limit:50})]);webhooks.value=w.data?.webhooks||[];eventTypes.value=e.data?.event_types||[];logs.value=l.data?.logs||[]}catch{}finally{loading.value=false}}
async function doTest(id:string){try{const r=await testWebhook(id);testR.value=r.data}catch{}}
async function doDel(id:string){if(!confirm('删除 webhook？'))return;try{await deleteWebhook(id);load()}catch{}}
function editWh(w:WebhookRegistration){edit.value=w;f.value={name:w.name,url:w.url,eventsStr:w.events.join(","),secret:w.secret||"",max_retries:w.max_retries,timeout_seconds:w.timeout_seconds}}
async function submit(){const d={name:f.value.name,url:f.value.url,events:f.value.eventsStr.split(",").map(s=>s.trim()).filter(Boolean),secret:f.value.secret||undefined,max_retries:f.value.max_retries,timeout_seconds:f.value.timeout_seconds};try{if(edit.value){await updateWebhook(edit.value.id,d)}else{await createWebhook(d)}showCreate.value=false;edit.value=null;load()}catch{}}
onMounted(load)
</script>

<style scoped>
.wh-page{padding:20px}.page-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}.page-header>div{display:flex;align-items:center;gap:8px}.page-header h2{font-size:18px;margin:0}.h-actions{display:flex;gap:8px}.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(380px,1fr));gap:10px}.card{padding:14px;border:1px solid var(--color-ide-border);border-radius:10px;background:var(--color-ide-bg)}.c-head{display:flex;justify-content:space-between;margin-bottom:8px}.c-name{display:flex;align-items:center;gap:6px;font-weight:600}.c-dot{width:8px;height:8px;border-radius:50%;background:var(--color-ide-text-secondary)}.c-dot.active{background:#059669}.c-url{font-size:12px;color:var(--color-ide-text-secondary);margin-bottom:6px}.c-events{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:6px}.c-stats{display:flex;gap:12px;font-size:11px;color:var(--color-ide-text-secondary)}.events-grid{display:flex;gap:6px;flex-wrap:wrap}.ev-tag{font-size:12px;padding:4px 10px;border:1px solid var(--color-ide-border);border-radius:99px;background:var(--color-ide-surface)}.table-wrap{overflow-x:auto;border:1px solid var(--color-ide-border);border-radius:10px;background:var(--color-ide-bg);margin-top:8px}.table-wrap table{width:100%;border-collapse:collapse;font-size:13px}.table-wrap th{text-align:left;padding:10px 12px;border-bottom:2px solid var(--color-ide-border);color:var(--color-ide-text-secondary);font-size:11px}.table-wrap td{padding:8px 12px;border-bottom:1px solid var(--color-ide-border)}.mono{font-family:monospace;font-size:12px}.ellip{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.tag{font-size:10px;padding:2px 6px;border-radius:99px;background:var(--color-ide-surface);color:var(--color-ide-text-secondary)}.ok{color:#059669}.err{color:#dc2626}.modal-mask{position:fixed;inset:0;z-index:999;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center}.modal-box{background:var(--color-ide-bg);border:1px solid var(--color-ide-border);border-radius:12px;padding:20px;min-width:420px;max-width:560px;max-height:80vh;overflow-y:auto}.modal-h{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;font-weight:600}.form{display:flex;flex-direction:column;gap:12px}.form label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--color-ide-text-secondary)}.input{width:100%;padding:8px 10px;border:1px solid var(--color-ide-border);border-radius:6px;font-size:13px;background:var(--color-ide-surface);color:var(--color-ide-text);box-sizing:border-box}.btn{display:inline-flex;align-items:center;gap:4px;border:none;cursor:pointer;border-radius:8px;font-size:13px;padding:8px 14px}.btn-primary{background:var(--color-ide-accent);color:#fff}.btn-ghost{background:transparent}.btn-sm{padding:4px 8px;font-size:12px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
</style>
