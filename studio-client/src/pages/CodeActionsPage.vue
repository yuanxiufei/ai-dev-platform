<template>
  <div class="pg">
    <h1 class="pg-h">代码操作</h1>
    <div class="row-flex">
      <div class="hflex"><label>语言</label><select v-model="language"><option value="">自动检测</option><option v-for="l in langs" :key="l" :value="l">{{ l }}</option></select></div>
      <div class="hflex"><label>文件路径 (可选)</label><input v-model="filePath" class="inp" placeholder="/src/file.ts"/></div>
    </div>
    <label>源代码</label><textarea v-model="sourceCode" class="ta" rows="10" placeholder="粘贴代码..."/>
    <button class="btn btn-pri" @click="fetchActions" :disabled="loading">{{ loading?'获取中...':'获取代码操作' }}</button>

    <!-- 操作列表 -->
    <div v-if="actions.length" class="act-ct">
      <h3>可用操作 ({{ actions.length }})</h3>
      <div v-for="(a,i) in actions" :key="i" class="card">
        <div class="card-h"><span class="card-t">{{ a.label || a.name || `操作 ${i+1}` }}</span><span v-if="a.kind" class="tag">{{ a.kind }}</span></div>
        <p v-if="a.description" class="desc">{{ a.description }}</p>
        <div class="card-bar">
          <span v-if="a.severity" class="sev" :class="a.severity">{{ a.severity }}</span>
          <button class="btn btn-sm" @click="applyAction(a)" :disabled="applying===i">{{ applying===i?'应用中...':'应用' }}</button>
        </div>
      </div>
    </div>

    <div v-if="applyResult" class="res-ct">
      <h3>应用结果</h3>
      <pre class="res">{{ applyResult }}</pre>
    </div>
    <div v-if="error" class="err">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { codeActionsApi } from '@/api/codeActions'

const language = ref('')
const filePath = ref('')
const sourceCode = ref('')
const actions = ref<any[]>([])
const applying = ref<number|null>(null)
const applyResult = ref('')
const error = ref('')
const loading = ref(false)
const langs = ['javascript','typescript','python','rust','go','java','c','cpp','ruby','php','html','css','json','yaml','markdown','sql','shell']

async function fetchActions() {
  try { loading.value=true;error.value='';actions.value=[];applyResult.value=''
    const r=await codeActionsApi.getCodeActions({code:sourceCode.value,language:language.value||undefined,filePath:filePath.value||undefined})
    actions.value=r.data?.actions??r.data??[]
  } catch(e:any) { error.value=e.response?.data?.detail??e.message }
  finally { loading.value=false }
}
async function applyAction(action:any) {
  const idx=actions.value.indexOf(action);applying.value=idx
  try { error.value='';applyResult.value=''
    const r=await codeActionsApi.applyCodeAction({actionId:action.id??action.name??action.label,code:sourceCode.value,language:language.value||undefined,filePath:filePath.value||undefined})
    applyResult.value=JSON.stringify(r.data,null,2)
  } catch(e:any) { error.value=e.response?.data?.detail??e.message }
  finally { applying.value=null }
}
</script>

<style scoped>
.pg{max-width:1200px;margin:0 auto;padding:24px}
.pg-h{font-size:1.5rem;font-weight:600;margin-bottom:20px;color:var(--color-ide-fg)}
.row-flex{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.hflex{display:flex;flex-direction:column;gap:6px}
label{font-size:0.8rem;font-weight:500;color:var(--color-ide-fg2)}
.ta,.inp{width:100%;padding:10px;border:1px solid var(--color-ide-border);border-radius:6px;background:var(--color-ide-bg2);color:var(--color-ide-fg);font-family:monospace;font-size:0.85rem;resize:vertical}
select{padding:6px 10px;border:1px solid var(--color-ide-border);border-radius:4px;background:var(--color-ide-bg2);color:var(--color-ide-fg)}
.btn{padding:8px 20px;border:none;border-radius:6px;font-size:0.875rem;cursor:pointer;font-weight:500;transition:all .15s}
.btn-pri{background:var(--color-ide-accent);color:#fff;margin:16px 0}
.btn-pri:disabled{opacity:0.5;cursor:not-allowed}
.btn-pri:hover:not(:disabled){opacity:0.85}
.btn-sm{padding:4px 14px;font-size:0.8rem;background:var(--color-ide-accent);color:#fff;border:none;border-radius:4px;cursor:pointer}
.btn-sm:disabled{opacity:0.5;cursor:not-allowed}
.act-ct{margin-top:24px}
.act-ct h3{margin:0 0 12px;font-size:0.95rem;color:var(--color-ide-fg)}
.card{background:var(--color-ide-bg2);border:1px solid var(--color-ide-border);border-radius:8px;padding:12px 16px;margin-bottom:8px}
.card-h{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.card-t{font-weight:600;font-size:0.9rem;color:var(--color-ide-fg)}
.tag{padding:2px 8px;border-radius:4px;font-size:0.7rem;background:var(--color-ide-accent);color:#fff;opacity:0.8}
.desc{font-size:0.8rem;color:var(--color-ide-fg2);margin:0 0 8px}
.card-bar{display:flex;align-items:center;justify-content:space-between}
.sev{padding:1px 6px;border-radius:3px;font-size:0.7rem;text-transform:uppercase}
.sev.error{background:rgba(224,85,85,.15);color:#e05555}
.sev.warning{background:rgba(224,176,85,.15);color:#e0a040}
.sev.info{background:rgba(85,150,224,.15);color:#4a90e0}
.sev.hint{background:rgba(85,224,150,.15);color:#40a070}
.res-ct{margin-top:24px;background:var(--color-ide-bg2);border:1px solid var(--color-ide-border);border-radius:8px;padding:16px}
.res-ct h3{margin:0 0 12px;font-size:0.95rem;color:var(--color-ide-fg)}
.res{background:var(--color-ide-bg);color:var(--color-ide-fg);padding:12px;border-radius:4px;font-size:0.8rem;line-height:1.4;white-space:pre-wrap;overflow-x:auto;max-height:400px;overflow-y:auto}
.err{color:var(--color-ide-err,#e05555);background:var(--color-ide-err-bg,rgba(224,85,85,.1));padding:10px;border-radius:6px;margin-top:12px;font-size:0.85rem}
</style>