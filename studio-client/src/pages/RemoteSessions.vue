<template>
  <div class="page">
    <h2>远程会话</h2>
    <p class="sub">远程连接、端口转发与工作区信任管理</p>

    <div class="tabs">
      <button :class="['tab', { act: tab === 'sessions' }]" @click="tab = 'sessions'">会话 ({{ sessions.length }})</button>
      <button :class="['tab', { act: tab === 'ports' }]" @click="loadPorts(); tab = 'ports'">端口转发</button>
      <button :class="['tab', { act: tab === 'trust' }]" @click="tab = 'trust'">工作区信任</button>
    </div>

    <!-- ═══ Sessions ═══ -->
    <div v-if="tab === 'sessions'" class="panel">
      <div class="sec">
        <h3>创建会话</h3>
        <div class="flex wrap">
          <textarea v-model="metaJson" placeholder='元数据 JSON（可选），如 {"workspace":"/path/to/project"}' class="in ta" rows="2" />
          <button class="bt btp" @click="createSess" :disabled="creating">
            {{ creating ? '创建中…' : '创建会话' }}
          </button>
        </div>
      </div>

      <div class="sec">
        <div class="head">
          <h3>活跃会话</h3>
          <button class="bt" @click="loadSessions" :disabled="loading">刷新</button>
        </div>
        <div v-if="loading" class="em">加载中…</div>
        <div v-else-if="!sessions.length" class="em">暂无活跃会话</div>
        <div v-for="s in sessions" :key="s.connection_id" class="card">
          <div class="card-hd">
            <span class="cid">{{ s.connection_id }}</span>
            <span :class="['badge', stateClass(s.state)]">{{ s.state }}</span>
            <span class="badge">{{ s.connection_type }}</span>
            <span class="spacer" />
            <span class="ts" title="最后心跳">{{ fmtTime(s.last_heartbeat) }}</span>
            <button class="bt bts" @click="confirmEnd(s.connection_id)">结束</button>
          </div>
          <div class="card-body">
            <span class="lbl">连接时间：</span>{{ fmtTime(s.connected_at) }}
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ Port Forwarding ═══ -->
    <div v-if="tab === 'ports'" class="panel">
      <div class="sec">
        <h3>创建映射</h3>
        <div class="flex wrap">
          <select v-model="selConnId" class="in">
            <option value="">-- 选择会话 --</option>
            <option v-for="s in sessions" :key="s.connection_id" :value="s.connection_id">
              {{ s.connection_id }} ({{ s.state }})
            </option>
          </select>
          <input v-model.number="pport" type="number" placeholder="本地端口" class="in w80" />
          <input v-model="pportName" placeholder="服务名（可选）" class="in w120" />
          <button class="bt btp" @click="createPort" :disabled="creatingPort">
            {{ creatingPort ? '创建中…' : '创建映射' }}
          </button>
        </div>
      </div>

      <div class="sec">
        <div class="head">
          <h3>端口映射列表</h3>
          <button class="bt" @click="loadPorts">刷新</button>
        </div>
        <div v-if="!ports.length" class="em">暂无端口映射</div>
        <div v-for="p in ports" :key="p.mapping_id" class="card">
          <div class="card-hd">
            <span class="cid">localhost:{{ p.local_port }} → :{{ p.proxy_port }}</span>
            <span :class="['badge', p.status === 'active' ? 'ok' : 'warn']">{{ p.status }}</span>
            <span class="badge2">{{ p.visibility }}</span>
            <span class="spacer" />
            <span class="lbl">{{ p.service_name || '-' }}</span>
            <button class="bt bts" @click="closePort(p.mapping_id)">关闭</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ═══ Workspace Trust ═══ -->
    <div v-if="tab === 'trust'" class="panel">
      <div class="sec">
        <h3>查询工作区信任</h3>
        <div class="flex">
          <input v-model="wsPath" placeholder="工作区路径（如 /home/user/project）" class="in flex1" @keyup.enter="getTrust" />
          <button class="bt btp" @click="getTrust" :disabled="trustLoading">查询</button>
        </div>
      </div>

      <div v-if="trust" class="sec">
        <h3>信任详情</h3>
        <div class="card">
          <div class="card-hd">
            <span class="cid">{{ trust.workspace_path }}</span>
            <span :class="['badge', trust.trust_level === 'trusted' ? 'ok' : 'warn']">{{ trust.trust_level }}</span>
          </div>
          <div class="card-body grid">
            <div><span class="lbl">授权人：</span>{{ trust.granted_by || '-' }}</div>
            <div><span class="lbl">授权时间：</span>{{ trust.granted_at ? fmtTime(trust.granted_at) : '-' }}</div>
            <div><span class="lbl">原因：</span>{{ trust.reason || '-' }}</div>
            <div>
              <span :class="['perm', trust.can_exec_shell ? 'ok' : 'err']">Shell: {{ trust.can_exec_shell ? '✓' : '✗' }}</span>
              <span :class="['perm', trust.can_write_files ? 'ok' : 'err']">写入: {{ trust.can_write_files ? '✓' : '✗' }}</span>
              <span :class="['perm', trust.can_network ? 'ok' : 'err']">网络: {{ trust.can_network ? '✓' : '✗' }}</span>
            </div>
          </div>
        </div>
      </div>

      <div class="sec">
        <h3>授权信任</h3>
        <div class="flex wrap">
          <input v-model="grantPath" placeholder="工作区路径" class="in flex1" />
          <select v-model="grantLevel" class="in">
            <option value="trusted">trusted — 完全信任</option>
            <option value="restricted">restricted — 受限</option>
            <option value="untrusted">untrusted — 不信任</option>
          </select>
          <button class="bt btp" @click="doGrant" :disabled="granting">
            {{ granting ? '授权中…' : '授权' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Confirm Dialog -->
    <teleport to="body">
      <div v-if="endConfirmId" class="modal-mask" @click.self="endConfirmId = ''">
        <div class="modal-box">
          <h4>确认结束会话</h4>
          <p class="confirm-text">确定要结束会话 <code>{{ endConfirmId }}</code> 吗？此操作不可撤销。</p>
          <div class="modal-acts">
            <button class="bt" @click="endConfirmId = ''">取消</button>
            <button class="bt bts" @click="doEndSession">确认结束</button>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { remoteApi, type RemoteSession, type PortMapping, type WorkspaceTrust } from '@/api/remote'

const tab = ref<'sessions' | 'ports' | 'trust'>('sessions')

// ── Sessions ──
const sessions = ref<RemoteSession[]>([])
const loading = ref(false)
const creating = ref(false)
const metaJson = ref('')
const endConfirmId = ref('')

onMounted(() => loadSessions())

async function loadSessions() {
  loading.value = true
  try {
    const r = await remoteApi.listSessions()
    sessions.value = (r.data as any)?.data ?? []
  } catch { /* ignore */ }
  finally { loading.value = false }
}

async function createSess() {
  let meta: Record<string, any> | undefined
  if (metaJson.value.trim()) {
    try { meta = JSON.parse(metaJson.value) }
    catch { alert('元数据 JSON 格式错误'); return }
  }
  creating.value = true
  try {
    await remoteApi.createSession(meta)
    metaJson.value = ''
    await loadSessions()
  } catch (e: any) { alert(e?.response?.data?.detail ?? e?.message ?? '创建失败') }
  finally { creating.value = false }
}

function confirmEnd(id: string) { endConfirmId.value = id }

async function doEndSession() {
  if (!endConfirmId.value) return
  try { await remoteApi.endSession(endConfirmId.value); await loadSessions() }
  catch (e: any) { alert(e?.response?.data?.detail ?? e?.message ?? '操作失败') }
  finally { endConfirmId.value = '' }
}

function stateClass(state: string): string {
  switch (state?.toLowerCase()) {
    case 'connected': return 'ok'
    case 'disconnected': return 'err'
    case 'error': return 'err'
    case 'reconnecting': return 'warn'
    case 'handshaking': return 'warn'
    default: return ''
  }
}

// ── Port Forwarding ──
const ports = ref<PortMapping[]>([])
const creatingPort = ref(false)
const selConnId = ref('')
const pport = ref(8080)
const pportName = ref('')

async function loadPorts() {
  try {
    // Load sessions first to populate dropdown, then load all ports
    if (!sessions.value.length) await loadSessions()
    const r = await remoteApi.listPorts()
    ports.value = (r.data as any)?.data ?? []
  } catch { /* ignore */ }
}

async function createPort() {
  const cid = selConnId.value || sessions.value[0]?.connection_id
  if (!cid) { alert('请先选择一个活跃会话'); return }
  creatingPort.value = true
  try {
    await remoteApi.createPort(cid, pport.value, pportName.value)
    pportName.value = ''
    await loadPorts()
  } catch (e: any) { alert(e?.response?.data?.detail ?? e?.message ?? '创建失败') }
  finally { creatingPort.value = false }
}

async function closePort(id: string) {
  try { await remoteApi.closePort(id); await loadPorts() }
  catch (e: any) { alert(e?.response?.data?.detail ?? e?.message ?? '关闭失败') }
}

// ── Workspace Trust ──
const trust = ref<WorkspaceTrust | null>(null)
const trustLoading = ref(false)
const wsPath = ref('')

async function getTrust() {
  if (!wsPath.value) { alert('请输入工作区路径'); return }
  trustLoading.value = true
  try {
    const r = await remoteApi.getTrust(wsPath.value)
    trust.value = r.data as WorkspaceTrust
  } catch (e: any) {
    trust.value = null
    alert(e?.response?.data?.detail ?? e?.message ?? '查询失败')
  }
  finally { trustLoading.value = false }
}

const grantPath = ref('')
const grantLevel = ref('trusted')
const granting = ref(false)

async function doGrant() {
  if (!grantPath.value) { alert('请输入工作区路径'); return }
  granting.value = true
  try {
    await remoteApi.grantTrust(grantPath.value, grantLevel.value)
    wsPath.value = grantPath.value
    await getTrust()
    grantPath.value = ''
  } catch (e: any) { alert(e?.response?.data?.detail ?? e?.message ?? '授权失败') }
  finally { granting.value = false }
}

// ── Helpers ──
function fmtTime(ts: string): string {
  if (!ts) return '-'
  try { return new Date(ts).toLocaleString() } catch { return ts }
}
</script>

<style scoped>
.page { max-width: 900px; margin: 0 auto; padding: 24px; }
h2 { margin: 0 0 4px; }
.sub { color: var(--color-ide-text-secondary); font-size: 14px; margin-bottom: 16px; }

/* ── Tabs ── */
.tabs { display: flex; gap: 0; margin-bottom: 20px; border-bottom: 1px solid var(--color-ide-border); }
.tab { padding: 8px 18px; border: none; border-bottom: 2px solid transparent; background: none; color: var(--color-ide-text-secondary); font-size: 13px; cursor: pointer; transition: .15s; }
.tab:hover { color: var(--color-ide-text-primary); }
.tab.act { color: var(--color-ide-accent); border-bottom-color: var(--color-ide-accent); font-weight: 600; }

/* ── Panel ── */
.panel { }
.sec { margin-bottom: 24px; }
.sec h3 { font-size: 15px; margin-bottom: 10px; font-weight: 600; }
.head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.head h3 { margin-bottom: 0; }

/* ── Inputs ── */
.in { padding: 7px 10px; border: 1px solid var(--color-ide-border); border-radius: 6px; background: var(--color-ide-bg-secondary); color: var(--color-ide-text-primary); font-size: 13px; }
.in:focus { outline: none; border-color: var(--color-ide-accent); }
.ta { resize: vertical; font-family: monospace; font-size: 12px; width: 100%; }
select.in { cursor: pointer; }
.w80 { width: 100px; }
.w120 { width: 140px; }
.flex1 { flex: 1; min-width: 200px; }
.flex { display: flex; gap: 8px; align-items: center; }
.wrap { flex-wrap: wrap; }

/* ── Buttons ── */
.bt { padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; background: var(--color-ide-bg-tertiary); color: var(--color-ide-text-primary); white-space: nowrap; transition: .15s; }
.bt:hover:not(:disabled) { opacity: .85; }
.bt:disabled { opacity: .5; cursor: not-allowed; }
.btp { background: var(--color-ide-accent); color: #fff; }
.bts { color: #e57373; font-size: 12px; padding: 4px 10px; }

/* ── Cards ── */
.card { border: 1px solid var(--color-ide-border); border-radius: 8px; background: var(--color-ide-bg-secondary); margin-bottom: 8px; overflow: hidden; }
.card-hd { display: flex; gap: 10px; align-items: center; padding: 10px 14px; background: var(--color-ide-bg-tertiary); font-size: 13px; }
.card-body { padding: 10px 14px; font-size: 12px; color: var(--color-ide-text-secondary); }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }

/* ── Misc ── */
.cid { font-family: monospace; font-weight: 600; font-size: 12px; color: var(--color-ide-text-primary); }
.badge { font-size: 11px; padding: 2px 7px; border-radius: 10px; background: var(--color-ide-bg-tertiary); color: var(--color-ide-text-secondary); }
.badge2 { font-size: 11px; padding: 2px 7px; border-radius: 4px; background: var(--color-ide-bg-primary); color: var(--color-ide-text-secondary); }
.ok { background: #1e3a2e; color: #81c784; }
.err { background: #3e1a1a; color: #e57373; }
.warn { background: #3e351a; color: #ffd54f; }
.spacer { flex: 1; }
.ts { font-size: 11px; color: var(--color-ide-text-secondary); }
.lbl { font-size: 12px; color: var(--color-ide-text-secondary); }
.perm { font-size: 12px; margin-right: 12px; }
.perm.ok { background: none; color: #81c784; }
.perm.err { background: none; color: #e57373; }
.em { text-align: center; padding: 32px; color: var(--color-ide-text-secondary); font-size: 13px; }

/* ── Modal ── */
.modal-mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.modal-box { background: var(--color-ide-bg-primary); border: 1px solid var(--color-ide-border); border-radius: 12px; padding: 24px; min-width: 380px; max-width: 480px; }
.modal-box h4 { margin: 0 0 12px; font-size: 16px; }
.confirm-text { font-size: 13px; color: var(--color-ide-text-secondary); margin-bottom: 18px; }
.confirm-text code { background: var(--color-ide-bg-tertiary); padding: 2px 6px; border-radius: 4px; font-size: 11px; }
.modal-acts { display: flex; gap: 8px; justify-content: flex-end; }
</style>
