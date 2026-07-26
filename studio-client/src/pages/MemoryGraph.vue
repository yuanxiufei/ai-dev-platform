<template>
  <div class="page"><h2>内存图谱</h2><p class="sub">Agent 内存节点与边的关系可视化数据</p>
    <div class="flex"><button class="bt btp" @click="fetchAll">加载数据</button></div>
    <div v-if="nodes.length" class="m">
      <div class="sec"><h3>节点 ({{nodes.length}})</h3>
        <div v-for="n in nodes" :key="n.id" class="row"><span class="nid">{{n.id}}</span><span class="lbl">{{n.label||'-'}}</span><span class="tp">{{n.type||'-'}}</span></div></div>
      <div class="sec"><h3>边 ({{edges.length}})</h3>
        <div v-for="(e,i) in edges" :key="i" class="row"><span>{{e.source}} → {{e.target}}</span><span class="rl">{{e.relation||'-'}}</span></div></div>
    </div>
    <div v-else class="em">暂无数据</div>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { client } from '@/api/client'
const nodes = ref<any[]>([])
const edges = ref<any[]>([])
async function fetchAll() {
  try { const r = await client.get('/api/v1/system/memory-graph/graph-data'); nodes.value = r.data?.nodes??[]; edges.value = r.data?.edges??[] } catch {}
}
</script>
<style scoped>
.page{max-width:1000px;margin:0 auto;padding:24px}h2{margin:0 0 4px}.sub{color:var(--color-ide-text-secondary);font-size:14px;margin-bottom:16px}
.flex{display:flex;gap:8px;margin-bottom:16px}.m{display:grid;grid-template-columns:1fr 1fr;gap:16px}.sec h3{font-size:14px;margin:0 0 8px}
.row{display:flex;gap:10px;padding:6px 10px;border:1px solid var(--color-ide-border);border-radius:6px;background:var(--color-ide-bg-secondary);font-size:12px;margin-bottom:4px}.nid{font-family:monospace;font-weight:600}.lbl{flex:1}.tp{color:var(--color-ide-accent);font-size:11px}.rl{color:var(--color-ide-text-secondary);font-size:11px}
.em{text-align:center;padding:40px;color:var(--color-ide-text-secondary)}
.bt{padding:5px 12px;border:none;border-radius:6px;cursor:pointer;font-size:13px;background:var(--color-ide-bg-tertiary);color:var(--color-ide-text-primary)}.btp{background:var(--color-ide-accent);color:#fff}
</style>
