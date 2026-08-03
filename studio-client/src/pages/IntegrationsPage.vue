<template>
  <div class="int-page">
    <header class="page-header"><div><PlugZap class="h-5 w-5"/><h2>第三方集成</h2></div>
      <button class="btn btn-primary" @click="openCreate"><Plus class="h-4 w-4"/>新增集成</button>
    </header>
    <div class="filters">
      <span :class="['f-chip',{active:!filterCat}]" @click="filterCat=''">全部({{stats.total}})</span>
      <span :class="['f-chip',{active:filterCat==='connected'}]" @click="filterCat='connected'">已连接({{stats.connected}})</span>
      <span :class="['f-chip',{active:filterCat==='disconnected'}]" @click="filterCat='disconnected'">未连接({{stats.disconnected}})</span>
      <span :class="['f-chip',{active:filterCat==='error'}]" @click="filterCat='error'">错误({{stats.error}})</span>
    </div>
    <div class="int-grid">
      <div v-for="it in filteredIntegrations" :key="it.id" class="int-card" :class="it.status">
        <div class="ic-top">
          <span class="ic-name">{{it.name}}</span>
          <span :class="['ic-status',it.status]">{{it.status}}</span>
        </div>
        <div class="ic-meta">{{it.provider}} · {{it.category}}</div>
        <div class="ic-actions">
          <button v-if="it.status!=='connected'" class="btn btn-sm btn-primary" @click="doConnect(it)"><Link class="h-3.5 w-3.5"/>连接</button>
          <button v-else class="btn btn-sm btn-ghost" @click="doDisconnect(it)"><Unlink class="h-3.5 w-3.5"/>断开</button>
          <button class="btn btn-sm btn-ghost" @click="openEdit(it)"><Pencil class="h-3.5 w-3.5"/></button>
          <button class="btn btn-sm btn-ghost" @click="doDelete(it.id)"><Trash2 class="h-3.5 w-3.5"/></button>
        </div>
      </div>
      <div v-if="!filteredIntegrations.length" class="empty">暂无集成</div>
    </div>

    <Teleport to="body"><div v-if="showModal" class="modal-overlay" @click.self="showModal=false">
      <div class="modal"><h3>{{editing?'编辑':'新增'}}集成</h3>
        <label>名称</label><input v-model="form.name" class="input-field"/>
        <label>类别</label><select v-model="form.category" class="input-field"><option value="storage">存储</option><option value="database">数据库</option><option value="ai">AI</option><option value="devops">DevOps</option><option value="auth">认证</option></select>
        <label>提供商</label><input v-model="form.provider" placeholder="aws/github/openai..." class="input-field"/>
        <label>配置 (JSON)</label><textarea v-model="form.configJson" rows="4" class="code-area mono"/>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showModal=false">取消</button>
          <button class="btn btn-primary" @click="doSave">{{editing?'更新':'创建'}}</button>
        </div></div></div></Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { PlugZap, Plus, Link, Unlink, Pencil, Trash2 } from "lucide-vue-next"
import { listIntegrations, createIntegration, updateIntegration, deleteIntegration, connectIntegration, disconnectIntegration, integrationsStats, Integration } from "@/api/integrations"

const integrations=ref<Integration[]>([]),filterCat=ref("")
const stats=ref({total:0,connected:0,disconnected:0,error:0,by_category:{}})
const filteredIntegrations=computed(()=>filterCat.value?integrations.value.filter(i=>i.status===filterCat.value):integrations.value)
async function load(){try{const[r,s]=await Promise.all([listIntegrations(),integrationsStats()]);integrations.value=r.data||[];stats.value=s.data}catch{}}
onMounted(load)

async function doConnect(it:Integration){try{await connectIntegration(it.id,{credentials:{}});it.status="connected";load()}catch{}}
async function doDisconnect(it:Integration){try{await disconnectIntegration(it.id);it.status="disconnected";load()}catch{}}
async function doDelete(id:string){if(!confirm('确认删除？'))return;try{await deleteIntegration(id);integrations.value=integrations.value.filter(i=>i.id!==id)}catch{}}

const showModal=ref(false),editing=ref(false),editId=ref("")
const form=ref({name:"",category:"storage",provider:"",configJson:"{}"})
function openCreate(){editing.value=false;form.value={name:"",category:"storage",provider:"",configJson:"{}"};showModal.value=true}
function openEdit(it:Integration){editing.value=true;editId.value=it.id;form.value={name:it.name,category:it.category,provider:it.provider,configJson:JSON.stringify(it.config||{},null,2)};showModal.value=true}
async function doSave(){try{let cfg:Record<string,unknown>={};try{cfg=JSON.parse(form.value.configJson)}catch{alert('配置JSON无效');return}
  if(editing.value){const r=await updateIntegration(editId.value,{name:form.value.name,config:cfg});const idx=integrations.value.findIndex(i=>i.id===editId.value);if(idx>=0)integrations.value[idx]=r.data}
  else{const r=await createIntegration({name:form.value.name,category:form.value.category,provider:form.value.provider,config:cfg});integrations.value.push(r.data)}
  showModal.value=false;load()}catch{}}
</script>

<style scoped>
.int-page{padding:20px}.page-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}.page-header>div{display:flex;align-items:center;gap:8px}.page-header h2{font-size:18px;margin:0}
.filters{display:flex;gap:6px;margin-bottom:16px}.f-chip{padding:4px 12px;border-radius:99px;font-size:12px;cursor:pointer;border:1px solid var(--color-ide-border)}.f-chip.active{background:var(--color-ide-accent);color:#fff;border-color:var(--color-ide-accent)}
.int-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}.int-card{padding:14px;border:1px solid var(--color-ide-border);border-radius:10px;background:var(--color-ide-bg)}.int-card.connected{border-left:3px solid #059669}.int-card.error{border-left:3px solid #dc2626}.ic-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}.ic-name{font-weight:600}.ic-status{font-size:11px;padding:2px 8px;border-radius:99px}.ic-status.connected{background:#0596691a;color:#059669}.ic-status.disconnected{background:var(--color-ide-surface);color:var(--color-ide-text-secondary)}.ic-status.error{background:#dc26261a;color:#dc2626}.ic-meta{font-size:12px;color:var(--color-ide-text-secondary);margin-bottom:10px}.ic-actions{display:flex;gap:4px}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:100}.modal{background:var(--color-ide-bg);border-radius:12px;padding:24px;width:480px;max-height:80vh;overflow-y:auto}.modal h3{margin:0 0 12px;font-size:16px}.modal-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}
.input-field{width:100%;box-sizing:border-box;border:1px solid var(--color-ide-border);border-radius:6px;padding:6px 10px;font-size:13px;background:var(--color-ide-surface);color:var(--color-ide-text);outline:none;margin-bottom:10px}.code-area{width:100%;box-sizing:border-box;border:1px solid var(--color-ide-border);border-radius:6px;padding:10px;background:var(--color-ide-surface);color:var(--color-ide-text);font-size:13px;resize:vertical;outline:none}.mono{font-family:monospace}.empty{text-align:center;padding:40px;color:var(--color-ide-text-secondary);grid-column:1/-1}
.btn{display:inline-flex;align-items:center;gap:4px;border:none;cursor:pointer;border-radius:8px;font-size:13px;padding:8px 14px}.btn-primary{background:var(--color-ide-accent);color:#fff}.btn-ghost{background:transparent}.btn-sm{padding:4px 8px;font-size:12px}
</style>
