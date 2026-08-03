<template>
  <div class="pg">
    <h1 class="pg-h">Diff 对比</h1>
    <!-- 模式切换 -->
    <div class="tabs-bar">
      <button :class="{tab:1,act:mode==='text'}" @click="mode='text'">文本对比</button>
      <button :class="{tab:1,act:mode==='files'}" @click="mode='files'">文件对比</button>
      <button :class="{tab:1,act:mode==='apply'}" @click="mode='apply'">应用补丁</button>
    </div>

    <!-- 文本对比模式 -->
    <div v-if="mode==='text'" class="ct">
      <div class="row-flex">
        <div class="hflex"><label>原始文本</label><textarea v-model="textLeft" class="ta" rows="8"/></div>
        <div class="hflex"><label>新文本</label><textarea v-model="textRight" class="ta" rows="8"/></div>
      </div>
      <div class="bar">
        <label class="lbl">格式: </label>
        <select v-model="diffFormat"><option v-for="f in formats" :key="f" :value="f">{{ f }}</option></select>
        <button class="btn btn-pri" @click="runTextDiff" :disabled="loading">{{ loading?'对比中...':'执行对比' }}</button>
      </div>
    </div>

    <!-- 文件对比模式 -->
    <div v-if="mode==='files'" class="ct">
      <div class="row-flex">
        <div class="hflex"><label>文件路径 (左)</label><input v-model="fileLeft" class="inp" placeholder="/path/to/left"/></div>
        <div class="hflex"><label>文件路径 (右)</label><input v-model="fileRight" class="inp" placeholder="/path/to/right"/></div>
      </div>
      <button class="btn btn-pri" @click="runFileDiff" :disabled="loading">{{ loading?'对比中...':'执行对比' }}</button>
    </div>

    <!-- 应用补丁模式 -->
    <div v-if="mode==='apply'" class="ct">
      <div class="hflex"><label>文件路径</label><input v-model="patchFile" class="inp" placeholder="/path/to/target"/></div>
      <label>补丁内容</label><textarea v-model="patchContent" class="ta" rows="6"/>
      <button class="btn btn-pri" @click="runApply" :disabled="loading">{{ loading?'应用中...':'应用补丁' }}</button>
    </div>

    <!-- 结果展示 -->
    <div v-if="result" class="res-ct">
      <h3>对比结果</h3>
      <pre class="res">{{ result }}</pre>
    </div>
    <div v-if="applyResult" class="res-ct">
      <h3>补丁应用结果</h3>
      <code class="res">{{ applyResult }}</code>
    </div>
    <div v-if="error" class="err">{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { diffApi } from '@/api/diff'

const mode = ref<'text'|'files'|'apply'>('text')
const textLeft = ref('')
const textRight = ref('')
const fileLeft = ref('')
const fileRight = ref('')
const patchFile = ref('')
const patchContent = ref('')
const diffFormat = ref('unified')
const result = ref('')
const applyResult = ref('')
const error = ref('')
const loading = ref(false)
const formats = ['unified', 'split', 'html']

async function runTextDiff() {
  try { loading.value=true;error.value='';result.value=''
    const r=await diffApi.text({text1:textLeft.value,text2:textRight.value,format:diffFormat.value})
    result.value=JSON.stringify(r.data,null,2)
  } catch(e:any) { error.value=e.response?.data?.detail??e.message }
  finally { loading.value=false }
}
async function runFileDiff() {
  try { loading.value=true;error.value='';result.value=''
    const r=await diffApi.files({file1:fileLeft.value,file2:fileRight.value})
    result.value=JSON.stringify(r.data,null,2)
  } catch(e:any) { error.value=e.response?.data?.detail??e.message }
  finally { loading.value=false }
}
async function runApply() {
  try { loading.value=true;error.value='';applyResult.value=''
    const r=await diffApi.apply({filePath:patchFile.value,patch:patchContent.value})
    applyResult.value=JSON.stringify(r.data,null,2)
  } catch(e:any) { error.value=e.response?.data?.detail??e.message }
  finally { loading.value=false }
}
</script>

<style scoped>
.pg{max-width:1200px;margin:0 auto;padding:24px}
.pg-h{font-size:1.5rem;font-weight:600;margin-bottom:20px;color:var(--color-ide-fg)}
.tabs-bar{display:flex;gap:4px;margin-bottom:20px;border-bottom:1px solid var(--color-ide-border);padding-bottom:12px}
.tab{padding:6px 16px;border:1px solid var(--color-ide-border);border-radius:6px 6px 0 0;background:var(--color-ide-bg2);color:var(--color-ide-fg2);cursor:pointer;font-size:0.875rem}
.tab.act{background:var(--color-ide-bg);color:var(--color-ide-fg);border-bottom-color:transparent;font-weight:600}
.ct{margin-bottom:20px}
.row-flex{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}
.hflex{display:flex;flex-direction:column;gap:6px}
label{font-size:0.8rem;font-weight:500;color:var(--color-ide-fg2)}
.ta,.inp{width:100%;padding:10px;border:1px solid var(--color-ide-border);border-radius:6px;background:var(--color-ide-bg2);color:var(--color-ide-fg);font-family:monospace;font-size:0.85rem;resize:vertical}
.bar{display:flex;align-items:center;gap:12px;margin-bottom:16px}
.lbl{font-size:0.8rem;color:var(--color-ide-fg2)}
select{padding:6px 10px;border:1px solid var(--color-ide-border);border-radius:4px;background:var(--color-ide-bg2);color:var(--color-ide-fg)}
.btn{padding:8px 20px;border:none;border-radius:6px;font-size:0.875rem;cursor:pointer;font-weight:500;transition:all .15s}
.btn-pri{background:var(--color-ide-accent);color:#fff}
.btn-pri:disabled{opacity:0.5;cursor:not-allowed}
.btn-pri:hover:not(:disabled){opacity:0.85}
.res-ct{margin-top:24px;background:var(--color-ide-bg2);border:1px solid var(--color-ide-border);border-radius:8px;padding:16px}
.res-ct h3{margin:0 0 12px;font-size:0.95rem;color:var(--color-ide-fg)}
.res{background:var(--color-ide-bg);color:var(--color-ide-fg);padding:12px;border-radius:4px;font-size:0.8rem;line-height:1.4;white-space:pre-wrap;overflow-x:auto;max-height:400px;overflow-y:auto}
.err{color:var(--color-ide-err,#e05555);background:var(--color-ide-err-bg,rgba(224,85,85,.1));padding:10px;border-radius:6px;margin-top:12px;font-size:0.85rem}
</style>