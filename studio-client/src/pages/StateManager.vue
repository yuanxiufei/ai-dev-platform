<template>
  <div class="page"><h2>状态管理</h2><p class="sub">全局 / 工作区 / 会话状态 CRUD</p>
    <div class="tabs"><button v-for="k in ['global','workspace','session']" :key="k" :class="['tab',{active:scope===k}]" @click="scope=k;load()">{{k}}</button></div>
    <div class="flex"><input v-model="key" placeholder="Key" class="in" /><input v-model="value" placeholder="Value" class="in" /><button class="bt btp" @click="upsert" :disabled="!key.trim()">保存</button><button class="bt" @click="load">刷新</button></div>
    <div v-if="items.length" class="list"><div v-for="it in items" :key="it.key" class="row"><span class="k">{{it.key}}</span><span class="v">{{it.value}}</span><button class="bt bts" @click="del(it.key)">x</button></div></div>
    <div v-else class="em">暂无数据</div>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { client } from '@/api/client'
const scope = ref('global')
const key = ref('')
const value = ref('')
const items = ref<{key:string;value:any}[]>([])
async function load() {
  try { const r = await client.get(`/api/v1/system/state/${scope.value}`); items.value = r.data ?? [] } catch {}
}
async function upsert() {
  await client.post(`/api/v1/system/state/${scope.value}/${encodeURIComponent(key.value)}`,{value:value.value})
  key.value = ''; value.value = ''; await load()
}
async function del(k:string) { await client.delete(`/api/v1/system/state/${scope.value}/${encodeURIComponent(k)}`); await load() }
</script>
<style scoped>
.page{max-width:700px;margin:0 auto;padding:24px}h2{margin:0 0 4px;font-size:22px}.sub{color:var(--color-ide-text-secondary);font-size:14px;margin-bottom:16px}
.tabs{display:flex;gap:4px;margin-bottom:16px}.tab{padding:6px 16px;border:1px solid var(--color-ide-border);border-radius:6px;cursor:pointer;background:var(--color-ide-bg-tertiary);color:var(--color-ide-text-primary);font-size:13px}.tab.active{border-color:var(--color-ide-accent);background:var(--color-ide-bg-active)}
.flex{display:flex;gap:8px;margin-bottom:16px}.in{padding:6px 10px;border:1px solid var(--color-ide-border);border-radius:6px;background:var(--color-ide-bg-secondary);color:var(--color-ide-text-primary);font-size:13px;flex:1}
.list{display:grid;gap:6px}.row{display:flex;gap:8px;align-items:center;padding:8px 12px;border:1px solid var(--color-ide-border);border-radius:8px;background:var(--color-ide-bg-secondary);font-size:13px}.k{font-weight:700;min-width:150px}.v{flex:1;color:var(--color-ide-text-secondary);word-break:break-all}.em{text-align:center;padding:40px;color:var(--color-ide-text-secondary)}
.bt{padding:5px 12px;border:none;border-radius:6px;cursor:pointer;font-size:13px;background:var(--color-ide-bg-tertiary);color:var(--color-ide-text-primary)}.btp{background:var(--color-ide-accent);color:#fff}.bts{padding:2px 8px;font-size:11px;color:#e57373}.bt:disabled{opacity:.4}
</style>
