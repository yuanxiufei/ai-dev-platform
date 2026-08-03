<template>
  <div class="so-page">
    <header class="page-header">
      <div><Braces class="h-5 w-5" /><h2>结构化输出</h2></div>
      <div class="header-tabs">
        <button :class="['tab', { active: tab==='convert' }]" @click="tab='convert'">转换</button>
        <button :class="['tab', { active: tab==='validate' }]" @click="tab='validate'">验证</button>
        <button :class="['tab', { active: tab==='templates' }]" @click="tab='templates'">模板</button>
        <button :class="['tab', { active: tab==='preview' }]" @click="tab='preview'">预览</button>
      </div>
    </header>

    <div v-if="tab==='convert'" class="split-panel">
      <div class="panel"><h3>JSON Schema</h3>
        <textarea v-model="jsonSchema" placeholder='{"type":"object"}' rows="14" class="code-area mono"/><br/>
        <button class="btn btn-primary" @click="doConvert" :disabled="!jsonSchema||converting"><Play class="h-4 w-4"/>转为 GBNF</button></div>
      <div class="panel"><h3>GBNF</h3>
        <button class="btn btn-sm btn-ghost" v-if="gbnf" @click="copyGbnf"><Copy class="h-3.5 w-3.5"/>复制</button>
        <pre class="code-area mono">{{gbnf||'转换后显示'}}</pre>
        <div v-if="warnings.length" class="warn"><AlertTriangle class="h-4 w-4"/><ul><li v-for="w in warnings" :key="w">{{w}}</li></ul></div></div>
    </div>

    <div v-if="tab==='validate'">
      <h3>验证 GBNF 语法</h3>
      <textarea v-model="gbnfValidate" placeholder="GBNF 语法..." rows="6" class="code-area mono"/><br/>
      <input v-model="sampleOutput" placeholder="样例输出（可选）" class="input-field"/>&nbsp;
      <button class="btn btn-primary" @click="doValidate" :disabled="!gbnfValidate||validating"><CheckCircle class="h-4 w-4"/>验证</button>
      <div v-if="validateResult!==null" :class="['v-result',validateResult?'success':'fail']">
        {{validateResult?'✅ 有效':`❌ ${validateErrors.join('; ')}`}}</div>
    </div>

    <div v-if="tab==='templates'" class="t-grid">
      <div v-for="t in templates" :key="t.name" class="t-card" @click="loadTemplate(t)">
        <h4>{{t.name}}</h4><p>{{t.description}}</p><span>{{JSON.stringify(t.schema).length}} 字符</span></div>
      <div v-if="!templates.length" class="empty">暂无模板</div>
    </div>

    <div v-if="tab==='preview'" class="split-panel">
      <div class="panel"><h3>JSON Schema</h3>
        <textarea v-model="previewSchema" placeholder='{"type":"object"}' rows="12" class="code-area mono"/><br/>
        <input v-model="previewModel" placeholder="模型(可选)" class="input-field"/>&nbsp;
        <button class="btn btn-primary" @click="doPreview" :disabled="!previewSchema||previewing"><Eye class="h-4 w-4"/>预览</button></div>
      <div class="panel"><h3>预览结果</h3><pre class="code-area mono">{{previewOutput||'预览后显示'}}</pre></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from "vue"
import { Braces, Play, Copy, AlertTriangle, CheckCircle, Eye } from "lucide-vue-next"
import { schemaToGbnf, validateGbnf, listTemplates, previewResponseFormat, TemplateItem } from "@/api/structuredOutput"

const tab=ref<"convert"|"validate"|"templates"|"preview">("convert")
const jsonSchema=ref(""),gbnf=ref(""),warnings=ref<string[]>([]),converting=ref(false)
async function doConvert(){converting.value=true;try{const s=JSON.parse(jsonSchema.value);const r=await schemaToGbnf({json_schema:s});gbnf.value=r.data.gbnf;warnings.value=r.data.warnings||[]}catch(e){console.error(e)}finally{converting.value=false}}
function copyGbnf(){navigator.clipboard.writeText(gbnf.value)}
const gbnfValidate=ref(""),sampleOutput=ref(""),validating=ref(false),validateResult=ref<boolean|null>(null),validateErrors=ref<string[]>([])
async function doValidate(){validating.value=true;try{const r=await validateGbnf({gbnf:gbnfValidate.value,sample_output:sampleOutput.value||undefined});validateResult.value=r.data.valid;validateErrors.value=r.data.errors||[]}catch(e){console.error(e)}finally{validating.value=false}}
const templates=ref<TemplateItem[]>([])
onMounted(async()=>{try{const r=await listTemplates();templates.value=r.data||[]}catch{}})
function loadTemplate(t:TemplateItem){jsonSchema.value=JSON.stringify(t.schema,null,2);tab.value="convert"}
const previewSchema=ref(""),previewModel=ref(""),previewOutput=ref(""),previewing=ref(false)
async function doPreview(){previewing.value=true;try{const s=JSON.parse(previewSchema.value);const r=await previewResponseFormat({json_schema:s,model:previewModel.value||undefined});previewOutput.value=r.data.preview}catch(e){console.error(e)}finally{previewing.value=false}}
</script>

<style scoped>
.so-page{padding:20px}.page-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}.page-header>div{display:flex;align-items:center;gap:8px}.page-header h2{font-size:18px;margin:0}.header-tabs{display:flex;gap:4px;background:var(--color-ide-surface);border-radius:8px;padding:3px}.tab{padding:6px 14px;border:none;border-radius:6px;font-size:13px;cursor:pointer;background:transparent;color:var(--color-ide-text-secondary)}.tab.active{background:var(--color-ide-accent);color:#fff}.split-panel{display:grid;grid-template-columns:1fr 1fr;gap:16px}.panel{background:var(--color-ide-bg);border:1px solid var(--color-ide-border);border-radius:10px;padding:14px}.panel h3{font-size:14px;margin:0 0 8px}.code-area{width:100%;box-sizing:border-box;border:1px solid var(--color-ide-border);border-radius:6px;padding:10px;background:var(--color-ide-surface);color:var(--color-ide-text);font-size:13px;resize:vertical;outline:none;white-space:pre-wrap}.mono{font-family:monospace}.warn{color:#f59e0b;margin-top:8px;font-size:12px}.v-result{padding:10px;border-radius:6px;margin-top:10px;font-size:13px}.v-result.success{background:#065f461a;color:#059669}.v-result.fail{background:#b91c1c1a;color:#dc2626}.t-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}.t-card{padding:14px;border:1px solid var(--color-ide-border);border-radius:8px;cursor:pointer}.t-card:hover{border-color:var(--color-ide-accent)}.t-card h4{font-size:14px;margin:0 0 6px}.t-card p{font-size:12px;color:var(--color-ide-text-secondary);margin:0 0 4px}.t-card span{font-size:11px;color:var(--color-ide-text-secondary)}.empty{text-align:center;padding:40px;color:var(--color-ide-text-secondary)}.input-field{width:100%;box-sizing:border-box;border:1px solid var(--color-ide-border);border-radius:6px;padding:6px 10px;font-size:13px;background:var(--color-ide-surface);color:var(--color-ide-text);outline:none}.btn{display:inline-flex;align-items:center;gap:4px;border:none;cursor:pointer;border-radius:8px;font-size:13px;padding:8px 14px}.btn-primary{background:var(--color-ide-accent);color:#fff}.btn-primary:disabled{opacity:.5;cursor:not-allowed}.btn-ghost{background:transparent}.btn-sm{padding:4px 8px;font-size:12px}
</style>
