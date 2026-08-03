<template>
  <div class="oa-page">
    <header class="page-header">
      <div><Globe class="h-5 w-5" /><h2>OpenAPI 发现</h2></div>
      <button class="btn btn-primary" @click="showDiscover=true"><Plus class="h-4 w-4"/>发现服务</button>
    </header>

    <!-- 服务列表 -->
    <div class="servers-grid">
      <div v-for="s in servers" :key="s.id" class="server-card" :class="{selected:selectedServer===s.id}" @click="selectServer(s.id)">
        <div class="s-top">
          <span class="s-name">{{s.name}}</span>
          <span class="s-status" :class="s.status">{{s.status}}</span>
        </div>
        <div class="s-url">{{s.url}}</div>
        <div class="s-meta">{{s.tool_count||0}} 工具 · {{s.spec_version||'?'}}
          <button class="btn btn-sm btn-ghost" @click.stop="deleteSrv(s.id)"><Trash2 class="h-3.5 w-3.5"/></button></div>
      </div>
      <div v-if="!servers.length" class="empty">暂无发现的服务，点击上方按钮添加</div>
    </div>

    <!-- 工具列表 -->
    <div v-if="selectedServer" class="tools-section">
      <h3>{{tools.length}} 个 API 工具</h3>
      <div class="tools-grid">
        <div v-for="t in tools" :key="t.id" class="tool-card">
          <div class="t-header">
            <span :class="['method',t.method]">{{t.method}}</span>
            <span class="t-path">{{t.path}}</span>
          </div>
          <div class="t-desc">{{t.description||t.name}}</div>
          <details class="t-params"><summary>参数 ({{t.parameters?.length||0}})</summary>
            <table><tr v-for="p in t.parameters" :key="p.name"><td>{{p.in}}</td><td>{{p.name}}</td><td>{{p.type}}</td><td>{{p.required?'*':''}}</td></tr></table>
          </details>
          <button class="btn btn-sm btn-primary" @click="testTool(t)"><Play class="h-3.5 w-3.5"/>调用</button>
        </div>
      </div>
    </div>

    <!-- 发现弹窗 -->
    <Teleport to="body"><div v-if="showDiscover" class="modal-overlay" @click.self="showDiscover=false">
      <div class="modal"><h3>发现 OpenAPI 服务</h3>
        <label>服务 URL</label><input v-model="discUrl" placeholder="https://api.example.com/openapi.json" class="input-field"/>
        <label>名称</label><input v-model="discName" placeholder="可选名称" class="input-field"/>
        <label>API Key</label><input v-model="discKey" type="password" placeholder="可选" class="input-field"/>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showDiscover=false">取消</button>
          <button class="btn btn-primary" @click="doDiscover" :disabled="!discUrl||discovering">{{discovering?'发现中...':'开始发现'}}</button>
        </div></div></div></Teleport>

    <!-- 工具调用弹窗 -->
    <Teleport to="body"><div v-if="testTarget" class="modal-overlay" @click.self="testTarget=null">
      <div class="modal"><h3>调用: {{testTarget.name}}</h3>
        <textarea v-model="testParams" placeholder='{"key":"value"}' rows="6" class="code-area mono"/>
        <div v-if="testResult" class="test-result"><pre>{{JSON.stringify(testResult,null,2)}}</pre></div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="testTarget=null;testResult=null">关闭</button>
          <button class="btn btn-primary" @click="doCall" :disabled="calling">{{calling?'调用中...':'执行'}}</button>
        </div></div></div></Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import { Globe, Plus, Trash2, Play } from "lucide-vue-next"
import { listServers, discoverServer, deleteServer, listTools, callTool, OpenAPIServer, OpenAPITool } from "@/api/openapiDiscovery"

const servers=ref<OpenAPIServer[]>([]),selectedServer=ref(""),tools=ref<OpenAPITool[]>([])
onMounted(loadServers)
async function loadServers(){try{const r=await listServers();servers.value=r.data||[]}catch{}}
async function selectServer(id:string){selectedServer.value=id;try{const r=await listTools(id);tools.value=r.data||[]}catch{}}
async function deleteSrv(id:string){if(!confirm('确认删除？'))return;try{await deleteServer(id);servers.value=servers.value.filter(s=>s.id!==id);if(selectedServer.value===id){selectedServer.value="";tools.value=[]}}catch{}}

const showDiscover=ref(false),discUrl=ref(""),discName=ref(""),discKey=ref(""),discovering=ref(false)
async function doDiscover(){discovering.value=true;try{const r=await discoverServer({url:discUrl.value,name:discName.value||undefined,api_key:discKey.value||undefined});servers.value.push(r.data);showDiscover.value=false}catch(e){console.error(e)}finally{discovering.value=false}}

const testTarget=ref<OpenAPITool|null>(null),testParams=ref(""),testResult=ref<any>(null),calling=ref(false)
function testTool(t:OpenAPITool){testTarget.value=t;testParams.value="";testResult.value=null}
async function doCall(){if(!testTarget.value)return;calling.value=true;try{let p:Record<string,unknown>={};try{p=JSON.parse(testParams.value)}catch{}const r=await callTool(testTarget.value.id,{parameters:p});testResult.value=r.data}catch(e){console.error(e)}finally{calling.value=false}}
</script>

<style scoped>
.oa-page{padding:20px}.page-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}.page-header>div{display:flex;align-items:center;gap:8px}.page-header h2{font-size:18px;margin:0}
.servers-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px;margin-bottom:20px}.server-card{padding:14px;border:1px solid var(--color-ide-border);border-radius:10px;cursor:pointer;background:var(--color-ide-bg)}.server-card.selected{border-color:var(--color-ide-accent)}.s-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}.s-name{font-weight:600}.s-status{font-size:11px;padding:2px 8px;border-radius:99px}.s-status.active{background:#0596691a;color:#059669}.s-status.error{background:#dc26261a;color:#dc2626}.s-status.discovering{background:#f59e0b1a;color:#f59e0b}.s-url{font-size:12px;color:var(--color-ide-text-secondary);margin-bottom:4px;word-break:break-all}.s-meta{font-size:12px;color:var(--color-ide-text-secondary);display:flex;align-items:center;gap:8px}
.tools-section h3{font-size:14px;margin-bottom:12px}.tools-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}.tool-card{padding:12px;border:1px solid var(--color-ide-border);border-radius:8px;background:var(--color-ide-bg)}.t-header{display:flex;gap:8px;align-items:center;margin-bottom:6px}.method{font-size:11px;font-weight:700;padding:1px 6px;border-radius:4px;text-transform:uppercase}.method.get{background:#3b82f61a;color:#3b82f6}.method.post{background:#0596691a;color:#059669}.method.put{background:#f59e0b1a;color:#f59e0b}.method.delete{background:#dc26261a;color:#dc2626}.t-path{font-size:13px;font-family:monospace;word-break:break-all}.t-desc{font-size:12px;color:var(--color-ide-text-secondary);margin-bottom:6px}.t-params{margin-bottom:8px}.t-params summary{font-size:12px;cursor:pointer}.t-params table{width:100%;font-size:11px;margin-top:4px}.t-params td{padding:2px 4px}
.modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:100}.modal{background:var(--color-ide-bg);border-radius:12px;padding:24px;width:520px;max-height:80vh;overflow-y:auto}.modal h3{margin:0 0 12px;font-size:16px}.modal-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}.test-result{margin-top:10px;background:var(--color-ide-surface);border-radius:6px;padding:10px;max-height:200px;overflow:auto;font-size:12px}.test-result pre{margin:0;white-space:pre-wrap}.empty{text-align:center;padding:40px;color:var(--color-ide-text-secondary);grid-column:1/-1}
.input-field{width:100%;box-sizing:border-box;border:1px solid var(--color-ide-border);border-radius:6px;padding:6px 10px;font-size:13px;background:var(--color-ide-surface);color:var(--color-ide-text);outline:none;margin-bottom:10px}.code-area{width:100%;box-sizing:border-box;border:1px solid var(--color-ide-border);border-radius:6px;padding:10px;background:var(--color-ide-surface);color:var(--color-ide-text);font-size:13px;resize:vertical;outline:none}.mono{font-family:monospace}
.btn{display:inline-flex;align-items:center;gap:4px;border:none;cursor:pointer;border-radius:8px;font-size:13px;padding:8px 14px}.btn-primary{background:var(--color-ide-accent);color:#fff}.btn-primary:disabled{opacity:.5;cursor:not-allowed}.btn-ghost{background:transparent}.btn-sm{padding:4px 8px;font-size:12px}
</style>
