<template>
  <div class="mem-page">
    <header class="page-header"><div><Brain class="h-5 w-5"/><h2>记忆管理</h2></div>
      <div class="h-actions"><button class="btn btn-primary btn-sm" @click="showCreate=true"><Plus class="h-4 w-4"/>新建</button><button class="btn btn-ghost btn-sm" @click="load"><RefreshCw :class="['h-4 w-4',{spin:loading}]"/>刷新</button></div>
    </header>

    <!-- 统计栏 -->
    <div class="stats-bar" v-if="stats"><div class="st-item"><span class="st-label">总记忆</span><span class="st-val">{{stats.total_memories}}</span></div><div class="st-item"><span class="st-label">总访问</span><span class="st-val">{{stats.total_accesses}}</span></div><div class="st-item" v-for="(v,k) in stats.by_domain" :key="k"><span class="st-label">{{k}}</span><span class="st-val">{{v}}</span></div></div>

    <!-- 搜索栏 -->
    <div class="search-bar"><input v-model="q" placeholder="语义检索记忆..." class="input" @keyup.enter="doSearch"/><button class="btn btn-primary btn-sm" @click="doSearch" :disabled="!q"><Search class="h-4 w-4"/>搜索</button></div>

    <!-- 搜索结果 -->
    <div v-if="results.length" class="results-panel"><h3>搜索结果 ({{results.length}})</h3>
      <div v-for="r in results" :key="r.id" class="result-card">
        <div class="rc-head"><span class="rc-key">{{r.key}}</span><span class="rc-score">{{(r.similarity*100).toFixed(0)}}% 相似</span></div>
        <p class="rc-val">{{r.value}}</p><div class="rc-meta">{{r.domain}} · 重要度 {{r.importance}}</div>
      </div>
    </div>

    <!-- 记忆表格 -->
    <div class="table-wrap"><table><thead><tr><th>Key</th><th>值</th><th>域</th><th>重要度</th><th>访问</th><th>操作</th></tr></thead>
    <tbody><tr v-for="m in memories" :key="m.id">
      <td class="fw6 mono">{{m.key}}</td><td class="ellip" :title="m.value">{{m.value.slice(0,80)}}{{m.value.length>80?'…':''}}</td>
      <td><span class="tag">{{m.domain||'default'}}</span></td><td>{{m.importance}}</td><td>{{m.access_count}}</td>
      <td class="td-actions"><button class="btn btn-ghost btn-sm" @click="editMem(m)">编辑</button><button class="btn btn-ghost btn-sm" @click="doDel(m.id)">删除</button></td>
    </tr></tbody></table></div>

    <!-- 创建/编辑弹窗 -->
    <Teleport to="body" v-if="showCreate||editData">
      <div class="modal-mask" @click.self="showCreate=false;editData=null"><div class="modal-box">
        <div class="modal-h"><span>{{editData?'编辑记忆':'新建记忆'}}</span><button class="btn btn-ghost btn-sm" @click="showCreate=false;editData=null">✕</button></div>
        <div class="form"><label>Key<input v-model="form.key" class="input"/></label><label>值<textarea v-model="form.value" class="input" rows="4"/></label><label>域<input v-model="form.domain" class="input" placeholder="default"/></label><label>重要度 (1-10)<input v-model.number="form.importance" type="number" min="1" max="10" class="input"/></label></div>
        <div style="text-align:right;margin-top:12px"><button class="btn btn-primary btn-sm" @click="submitForm">{{editData?'更新':'创建'}}</button></div>
      </div></div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import { Brain, Plus, RefreshCw, Search } from "lucide-vue-next"
import { listMemories, createMemory, updateMemory, deleteMemory, searchMemories, memoryStats, MemoryEntry, MemorySearchResult, MemoryStats } from "@/api/memory"

const memories=ref<MemoryEntry[]>([]), stats=ref<MemoryStats|null>(null), loading=ref(false)
const results=ref<MemorySearchResult[]>([]), q=ref("")
const showCreate=ref(false), editData=ref<MemoryEntry|null>(null)
const form=ref({key:"",value:"",domain:"",importance:5})

async function load(){loading.value=true;try{const[r,s]=await Promise.all([listMemories({size:100}),memoryStats()]);memories.value=r.data?.data||[];stats.value=s.data}catch{}finally{loading.value=false}}
async function doSearch(){if(!q.value)return;try{const r=await searchMemories({query:q.value,top_k:20});results.value=r.data?.results||[]}catch{}}
async function doDel(id:string){if(!confirm('删除记忆？'))return;try{await deleteMemory(id);load()}catch{}}
function editMem(m:MemoryEntry){editData.value=m;form.value={key:m.key,value:m.value,domain:m.domain||"",importance:m.importance}}
async function submitForm(){try{if(editData.value){await updateMemory(editData.value.id,form.value)}else{await createMemory(form.value)}showCreate.value=false;editData.value=null;load()}catch{}}
onMounted(load)
</script>

<style scoped>
.mem-page{padding:20px}.page-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px}.page-header>div{display:flex;align-items:center;gap:8px}.page-header h2{font-size:18px;margin:0}.h-actions{display:flex;gap:8px}.stats-bar{display:flex;gap:16px;padding:12px 16px;margin-bottom:16px;background:var(--color-ide-bg);border:1px solid var(--color-ide-border);border-radius:10px;flex-wrap:wrap}.st-item{display:flex;flex-direction:column;gap:2px}.st-label{font-size:11px;color:var(--color-ide-text-secondary)}.st-val{font-size:18px;font-weight:700}.search-bar{display:flex;gap:8px;margin-bottom:16px}.search-bar .input{flex:1}.results-panel{margin-bottom:16px}.result-card{padding:10px 14px;border:1px solid var(--color-ide-border);border-radius:8px;margin-bottom:8px;background:var(--color-ide-bg)}.rc-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}.rc-key{font-weight:600;color:var(--color-ide-accent);font-size:13px}.rc-score{font-size:11px;color:var(--color-ide-text-secondary)}.rc-val{font-size:13px;margin:0 0 4px}.rc-meta{font-size:11px;color:var(--color-ide-text-secondary)}.table-wrap{overflow-x:auto;border:1px solid var(--color-ide-border);border-radius:10px;background:var(--color-ide-bg)}.table-wrap table{width:100%;border-collapse:collapse;font-size:13px}.table-wrap th{text-align:left;padding:10px 12px;border-bottom:2px solid var(--color-ide-border);color:var(--color-ide-text-secondary);font-size:11px}.table-wrap td{padding:8px 12px;border-bottom:1px solid var(--color-ide-border);vertical-align:middle}.fw6{font-weight:600}.mono{font-family:monospace;font-size:12px}.tag{font-size:10px;padding:2px 6px;border-radius:99px;background:var(--color-ide-surface);color:var(--color-ide-text-secondary)}.td-actions{display:flex;gap:4px}.ellip{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:300px}.modal-mask{position:fixed;inset:0;z-index:999;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center}.modal-box{background:var(--color-ide-bg);border:1px solid var(--color-ide-border);border-radius:12px;padding:20px;min-width:420px;max-width:560px;max-height:80vh;overflow-y:auto}.modal-h{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;font-weight:600}.form{display:flex;flex-direction:column;gap:12px}.form label{display:flex;flex-direction:column;gap:4px;font-size:12px;color:var(--color-ide-text-secondary)}.input{width:100%;padding:8px 10px;border:1px solid var(--color-ide-border);border-radius:6px;font-size:13px;background:var(--color-ide-surface);color:var(--color-ide-text);box-sizing:border-box}.btn{display:inline-flex;align-items:center;gap:4px;border:none;cursor:pointer;border-radius:8px;font-size:13px;padding:8px 14px}.btn-primary{background:var(--color-ide-accent);color:#fff}.btn-ghost{background:transparent}.btn-sm{padding:4px 8px;font-size:12px}.spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
</style>
