<template>
  <div class="page"><h2>CLI 历史</h2><p class="sub">命令执行历史记录 (JSONL)</p>
    <div class="flex"><input v-model.number="limit" type="number" placeholder="条数" class="in" /><input v-model.number="offset" type="number" placeholder="偏移" class="in" /><button class="bt btp" @click="fetch">查询</button></div>
    <div v-if="stats" class="stats">共 {{stats.total}} 条 | 成功 {{stats.success_count}} | 失败 {{stats.error_count}}</div>
    <div v-for="e in entries" :key="e.command+e.timestamp" class="row">
      <div class="hd"><span class="cmd">{{e.command}}</span><span :class="['badge',e.exit_code===0?'ok':'err']">{{e.exit_code}}</span><span class="dur">{{e.duration_ms}}ms</span><span class="ts">{{e.timestamp}}</span></div>
      <details v-if="e.stdout"><summary>stdout</summary><pre>{{e.stdout}}</pre></details>
      <details v-if="e.stderr"><summary class="errs">stderr</summary><pre class="e">{{e.stderr}}</pre></details>
    </div>
    <div v-if="!entries.length" class="em">暂无记录</div>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { cliHistoryApi, type CliHistoryEntry } from '@/api/cliHistory'
const entries = ref<CliHistoryEntry[]>([])
const stats = ref<any>(null)
const limit = ref(20)
const offset = ref(0)
async function fetch() {
  try { const r = await cliHistoryApi.list(limit.value, offset.value); entries.value = r.data?.entries ?? []; stats.value = r.data } catch {}
}
</script>
<style scoped>
.page{max-width:900px;margin:0 auto;padding:24px}h2{margin:0 0 4px}.sub{color:var(--color-ide-text-secondary);font-size:14px;margin-bottom:16px}
.flex{display:flex;gap:8px;margin-bottom:12px}.in{width:80px;padding:6px 10px;border:1px solid var(--color-ide-border);border-radius:6px;background:var(--color-ide-bg-secondary);color:var(--color-ide-text-primary);font-size:13px}
.stats{font-size:12px;color:var(--color-ide-text-secondary);margin-bottom:12px}
.row{padding:10px;border:1px solid var(--color-ide-border);border-radius:8px;background:var(--color-ide-bg-secondary);margin-bottom:8px;font-size:13px}.hd{display:flex;gap:10px;align-items:center}.cmd{font-weight:700;font-family:monospace}.dur{color:var(--color-ide-text-secondary);font-size:11px}.ts{color:var(--color-ide-text-secondary);font-size:11px;margin-left:auto}
.badge{font-size:11px;padding:2px 6px;border-radius:10px;background:var(--color-ide-bg-tertiary)}.ok{background:#1e3a2e;color:#81c784}.err{background:#3e1a1a;color:#e57373}
summary{font-size:12px;cursor:pointer;color:var(--color-ide-text-secondary);margin-top:4px}.errs{color:#e57373}
pre{background:#0d1117;color:#d2d2d2;padding:8px;border-radius:4px;font-size:11px;max-height:120px;overflow:auto;white-space:pre-wrap;margin-top:4px}pre.e{color:#e57373}
.em{text-align:center;padding:40px;color:var(--color-ide-text-secondary)}
.bt{padding:5px 12px;border:none;border-radius:6px;cursor:pointer;font-size:13px;background:var(--color-ide-bg-tertiary);color:var(--color-ide-text-primary)}.btp{background:var(--color-ide-accent);color:#fff}
</style>
