<template>
  <div class="page"><div class="hd"><h2>配置解析器</h2><p class="sub">解析 ${variable} 引用</p></div>
    <div class="lay"><div class="pn"><h3>变量列表</h3>
      <div v-for="v in vars" :key="v.name" class="vi"><code>{{ v.name }}</code><span>{{ v.description }}</span></div></div>
    <div class="pn"><h3>解析</h3><textarea v-model="txt" placeholder="输入含 ${...} 文本" class="ta" rows="6"/><button class="bt btp" @click="resolve" :disabled="!txt.trim()">解析</button>
    <div v-if="res !== null" class="rbox"><span>原始:</span><pre>{{ txt }}</pre><span>结果:</span><pre class="r">{{ res }}</pre></div></div></div></div>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { configResolverApi, type VariableDef } from '@/api/configResolver'
const vars = ref<VariableDef[]>([])
const txt = ref('')
const res = ref<string | null>(null)
async function resolve() {
  try { const r = await configResolverApi.resolve(txt.value); res.value = (r.data as any)?.resolved ?? r?.resolved ?? '' } catch { res.value = '解析失败' }
}
onMounted(async () => { try { const r = await configResolverApi.listVariables(); vars.value = (r.data as any)?.variables ?? [] } catch {} })
</script>
<style scoped>
.page{max-width:900px;margin:0 auto;padding:24px}.hd h2{margin:0;font-size:22px}.sub{color:var(--color-ide-text-secondary);font-size:14px;margin:4px 0 16px}
.lay{display:grid;grid-template-columns:260px 1fr;gap:20px}.pn h3{font-size:15px;margin:0 0 10px}
.vi{display:flex;gap:6px;font-size:12px;padding:3px 0;border-bottom:1px solid var(--color-ide-border)}.vi code{background:var(--color-ide-bg-tertiary);padding:1px 5px;border-radius:4px;font-size:11px}
.ta{width:100%;padding:10px;border:1px solid var(--color-ide-border);border-radius:8px;background:#0d1117;color:#d2d2d2;font-family:monospace;font-size:13px;resize:vertical;box-sizing:border-box;margin-bottom:8px}
.rbox{margin-top:12px}.rbox span{font-size:12px;color:var(--color-ide-text-secondary)}.rbox pre{background:var(--color-ide-bg-tertiary);padding:10px;border-radius:6px;font-size:13px;white-space:pre-wrap;margin:4px 0}pre.r{color:var(--color-ide-accent)}
.bt{padding:6px 14px;border:none;border-radius:6px;cursor:pointer;font-size:13px;background:var(--color-ide-bg-tertiary);color:var(--color-ide-text-primary)}.btp{background:var(--color-ide-accent);color:#fff}.bt:disabled{opacity:.4}
</style>
