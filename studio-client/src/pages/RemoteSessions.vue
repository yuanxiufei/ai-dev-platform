<template>
  <div class="page"><h2>远程会话</h2><p class="sub">远程连接、端口转发与工作区信任管理</p>
    <div class="sec"><h3>会话</h3><input v-model="metaJson" placeholder='元数据 JSON (可选)' class="in" /><button class="bt btp" @click="createSess">创建会话</button><button class="bt" @click="loadSessions">刷新</button>
      <div v-for="s in sessions" :key="s.connection_id" class="row"><span class="id">{{s.connection_id}}</span><span class="badge">{{s.state}}</span><span>{{s.connection_type}}</span><button class="bt bts" @click="endSess(s.connection_id)">x</button></div></div>
    <div class="sec"><h3>端口转发</h3><div class="flex"><input v-model.number="port" type="number" placeholder="本地端口" class="in" /><input v-model="portName" placeholder="服务名" class="in" /><button class="bt btp" @click="createPort">创建</button></div>
      <div v-for="p in ports" :key="p.mapping_id" class="row"><span>L{{p.local_port}}→{{p.proxy_port}}</span><span>{{p.service_name||'-'}}</span><span class="badge">{{p.status}}</span></div></div>
    <div class="sec"><h3>工作区信任</h3><input v-model="wsPath" placeholder="工作区路径" class="in" /><button class="bt btp" @click="grantTrust">授权信任</button>
      <div v-if="trust" class="row"><span>{{trust.workspace_path}}</span><span class="badge">{{trust.trust_level}}</span><span>{{trust.granted_at}}</span></div></div>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { remoteApi, type RemoteSession, type PortMapping, type WorkspaceTrust } from '@/api/remote'
const sessions = ref<RemoteSession[]>([])
const ports = ref<PortMapping[]>([])
const trust = ref<WorkspaceTrust | null>(null)
const metaJson = ref('')
const port = ref(8080)
const portName = ref('')
const wsPath = ref('')

async function loadSessions() { try { const r = await remoteApi.listSessions(); sessions.value = (r.data as any)?.data ?? [] } catch {} }
async function createSess() { try { const m = metaJson.value ? JSON.parse(metaJson.value) : {}; await remoteApi.createSession(m); loadSessions() } catch (e:any) { alert(e?.message) } }
async function endSess(id:string) { await remoteApi.endSession(id); loadSessions() }
async function createPort() { try { const r = await remoteApi.createPort(sessions.value[0]?.connection_id ?? '', port.value, portName.value); ports.value = (r.data as any)?.data ?? [] } catch {} }
async function grantTrust() { try { const r = await remoteApi.grantTrust(wsPath.value); trust.value = (r.data ?? r) as WorkspaceTrust } catch (e:any) { alert(e?.message) } }
</script>
<style scoped>
.page{max-width:800px;margin:0 auto;padding:24px}h2{margin:0 0 4px}.sub{color:var(--color-ide-text-secondary);font-size:14px;margin-bottom:16px}
.sec{margin-bottom:24px}.sec h3{font-size:15px;margin-bottom:10px}
.in{padding:6px 10px;border:1px solid var(--color-ide-border);border-radius:6px;background:var(--color-ide-bg-secondary);color:var(--color-ide-text-primary);font-size:13px;margin-right:8px;margin-bottom:8px}
.flex{display:flex;gap:8px;align-items:center}
.row{display:flex;gap:12px;align-items:center;padding:8px 12px;border:1px solid var(--color-ide-border);border-radius:8px;background:var(--color-ide-bg-secondary);font-size:13px;margin-top:6px}.id{font-family:monospace;font-weight:600}
.badge{font-size:11px;padding:2px 6px;border-radius:10px;background:var(--color-ide-bg-tertiary);color:var(--color-ide-text-secondary)}
.bt{padding:5px 12px;border:none;border-radius:6px;cursor:pointer;font-size:13px;background:var(--color-ide-bg-tertiary);color:var(--color-ide-text-primary);margin-right:6px}.btp{background:var(--color-ide-accent);color:#fff}.bts{color:#e57373;font-size:12px;padding:2px 8px}
</style>
