<template>
  <div class="diag-page">
    <header class="page-header"><div><Stethoscope class="h-5 w-5"/><h2>代码诊断</h2></div>
      <div class="header-actions">
        <select v-model="language" class="input-sm">
          <option v-for="l in languages" :key="l" :value="l">{{l}}</option>
        </select>
        <label class="cb-label"><input type="checkbox" v-model="checkLint"/> Lint</label>
        <label class="cb-label"><input type="checkbox" v-model="checkType"/> Type</label>
        <label class="cb-label"><input type="checkbox" v-model="checkSecurity"/> Security</label>
        <label class="cb-label"><input type="checkbox" v-model="checkStyle"/> Style</label>
        <label class="cb-label"><input type="checkbox" v-model="checkPerf"/> Perf</label>
      </div>
    </header>
    <div class="split-panel">
      <div class="panel"><h3>代码</h3>
        <textarea v-model="code" :placeholder="`输入 ${language} 代码...`" rows="16" class="code-area mono"/><br/>
        <button class="btn btn-primary" @click="analyze" :disabled="!code||analyzing">
          <Play class="h-4 w-4"/>{{analyzing?'分析中...':'分析代码'}}</button>
      </div>
      <div class="panel">
        <h3>诊断结果 {{result&&`(${result.summary.total} 问题)`}}</h3>
        <div v-if="result" class="summary-bar">
          <span class="sev e">{{result.summary.errors}} 错误</span>
          <span class="sev w">{{result.summary.warnings}} 警告</span>
          <span class="sev i">{{result.summary.info}} 信息</span>
          <span class="sev h">{{result.summary.hints}} 提示</span>
          <span class="dur">{{result.duration_ms}}ms</span>
        </div>
        <div v-if="result" class="issues">
          <div v-for="(issue,idx) in result.issues" :key="idx" :class="['issue',issue.severity]">
            <div class="is-top"><span class="is-loc">L{{issue.line}}:{{issue.column||1}}</span><span :class="['is-sev',issue.severity]">{{issue.severity}}</span><span class="is-src">{{issue.source}}</span></div>
            <div class="is-msg">{{issue.message}} <code v-if="issue.code">{{issue.code}}</code></div>
            <div v-if="issue.fix" class="is-fix">💡 {{issue.fix}}</div>
          </div>
        </div>
        <div v-else class="empty">分析结果将在此显示</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from "vue"
import { Stethoscope, Play } from "lucide-vue-next"
import { analyzeCode, listSupportedLanguages, DiagnosticResponse } from "@/api/diagnostics"

const language=ref("python"),code=ref(""),analyzing=ref(false),result=ref<DiagnosticResponse|null>(null)
const checkLint=ref(true),checkType=ref(true),checkSecurity=ref(true),checkStyle=ref(false),checkPerf=ref(false)
const languages=ref<string[]>(["python","typescript","javascript","go","rust","java","cpp"])
const checkTypes=computed(()=>{const c:string[]=[];if(checkLint.value)c.push("lint");if(checkType.value)c.push("type");if(checkSecurity.value)c.push("security");if(checkStyle.value)c.push("style");if(checkPerf.value)c.push("performance");return c})

onMounted(async()=>{try{const r=await listSupportedLanguages();languages.value=r.data}catch{}})
async function analyze(){analyzing.value=true;result.value=null;try{const r=await analyzeCode({code:code.value,language:language.value,check_types:checkTypes.value.length?checkTypes.value:undefined});result.value=r.data}catch(e){console.error(e)}finally{analyzing.value=false}}
</script>

<style scoped>
.diag-page{padding:20px}.page-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:8px}.page-header>div{display:flex;align-items:center;gap:8px}.page-header h2{font-size:18px;margin:0}.header-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.cb-label{font-size:12px;display:flex;align-items:center;gap:3px;cursor:pointer}.split-panel{display:grid;grid-template-columns:1fr 1fr;gap:16px;height:calc(100vh - 200px)}.panel{background:var(--color-ide-bg);border:1px solid var(--color-ide-border);border-radius:10px;padding:14px;display:flex;flex-direction:column}.panel h3{font-size:14px;margin:0 0 8px;flex-shrink:0}.code-area{width:100%;box-sizing:border-box;border:1px solid var(--color-ide-border);border-radius:6px;padding:10px;background:var(--color-ide-surface);color:var(--color-ide-text);font-size:13px;resize:vertical;outline:none;flex:1;min-height:0}.mono{font-family:monospace}.summary-bar{display:flex;gap:10px;padding:8px 12px;background:var(--color-ide-surface);border-radius:6px;margin-bottom:8px;font-size:12px;flex-wrap:wrap}.sev.e{color:#dc2626}.sev.w{color:#f59e0b}.sev.i{color:#3b82f6}.sev.h{color:var(--color-ide-text-secondary)}.dur{color:var(--color-ide-text-secondary);margin-left:auto}.issues{flex:1;overflow-y:auto;display:flex;flex-direction:column;gap:8px}.issue{padding:8px 12px;border-radius:6px;border-left:3px solid var(--color-ide-border)}.issue.error{border-left-color:#dc2626;background:#dc262608}.issue.warning{border-left-color:#f59e0b;background:#f59e0b08}.issue.info{border-left-color:#3b82f6;background:#3b82f608}.is-top{display:flex;gap:8px;align-items:center;margin-bottom:2px;font-size:11px}.is-loc{font-family:monospace}.is-sev{padding:0 4px;border-radius:3px;font-weight:600}.is-sev.error{background:#dc262620;color:#dc2626}.is-sev.warning{background:#f59e0b20;color:#f59e0b}.is-sev.info{background:#3b82f620;color:#3b82f6}.is-src{color:var(--color-ide-text-secondary)}.is-msg{font-size:13px;margin:2px 0}.is-fix{font-size:12px;color:#059669}.empty{text-align:center;padding:40px;color:var(--color-ide-text-secondary)}
.input-sm{font-size:12px;padding:4px 8px;border:1px solid var(--color-ide-border);border-radius:6px;background:var(--color-ide-surface);color:var(--color-ide-text)}
.btn{display:inline-flex;align-items:center;gap:4px;border:none;cursor:pointer;border-radius:8px;font-size:13px;padding:8px 14px}.btn-primary{background:var(--color-ide-accent);color:#fff}.btn-primary:disabled{opacity:.5;cursor:not-allowed}
</style>
