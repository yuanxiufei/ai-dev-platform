<template>
  <div class="page"><h2>问题匹配器</h2><p class="sub">解析命令行输出为结构化诊断 (TS/ESLint/Pytest/GCC 等)</p>
    <div class="flex"><select v-model="matcher" class="sel"><option v-for="m in matchers" :key="m.id" :value="m.id">{{m.name}} ({{m.pattern}})</option></select><button class="bt btp" @click="parse">解析</button></div>
    <textarea v-model="input" placeholder="粘贴命令行输出..." class="ta" rows="8"/>
    <div v-if="results.length" class="r"><h3>诊断结果 ({{results.length}})</h3>
      <div v-for="(r,i) in results" :key="i" class="ri"><span class="sev" :class="'s'+r.severity">{{r.severity||'-'}}</span><span class="f">{{r.file}}:{{r.line}}:{{r.column}}</span><span class="msg">{{r.message}}</span><code class="c">{{r.code}}</code></div></div>
  </div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { client } from '@/api/client'
const matchers = ref<any[]>([])
const matcher = ref('')
const input = ref('')
const results = ref<any[]>([])
async function fetchM() { try { const r = await client.get('/api/v1/system/problem-matchers'); matchers.value = r.data??[]; if(matchers.value.length) matcher.value = matchers.value[0].id } catch {} }
async function parse() {
  try { const r = await client.post('/api/v1/system/problem-matchers/parse',{matcher_id:matcher.value,output:input.value}); results.value = r.data?.diagnostics??[] } catch(e){ results.value = [] }
}
onMounted(fetchM)
</script>
<style scoped>
.page{max-width:900px;margin:0 auto;padding:24px}h2{margin:0 0 4px}.sub{color:var(--color-ide-text-secondary);font-size:14px;margin-bottom:16px}
.flex{display:flex;gap:8px;margin-bottom:12px}.sel{padding:6px 10px;border:1px solid var(--color-ide-border);border-radius:6px;background:var(--color-ide-bg-secondary);color:var(--color-ide-text-primary);font-size:13px;flex:1}
.ta{width:100%;padding:10px;border:1px solid var(--color-ide-border);border-radius:8px;background:#0d1117;color:#d2d2d2;font-family:monospace;font-size:13px;resize:vertical;box-sizing:border-box}
.r{margin-top:16px}.r h3{font-size:14px;margin-bottom:8px}
.ri{display:flex;gap:10px;align-items:center;padding:8px 10px;border:1px solid var(--color-ide-border);border-radius:6px;background:var(--color-ide-bg-secondary);font-size:13px;margin-bottom:4px}.sev{font-size:11px;padding:1px 6px;border-radius:6px;font-weight:700;text-transform:uppercase}.serror{background:#3e1a1a;color:#e57373}.swarning{background:#3e3a1e;color:#ffb74d}.sinfo{background:#1e3a5f;color:#64b5f6}.f{font-family:monospace;min-width:200px}.msg{flex:1;color:var(--color-ide-text-secondary)}.c{font-size:11px}
.bt{padding:5px 12px;border:none;border-radius:6px;cursor:pointer;font-size:13px;background:var(--color-ide-bg-tertiary);color:var(--color-ide-text-primary)}.btp{background:var(--color-ide-accent);color:#fff}
</style>
