<template>
  <div class="page">
    <h2>CLI 历史</h2>
    <p class="sub">查看、搜索与过滤终端命令执行记录</p>

    <!-- ═══ Stats Bar ═══ -->
    <div v-if="stats" class="stats">
      <div class="stat"><span class="stat-num">{{ stats.total }}</span> 总命令</div>
      <div class="stat ok"><span class="stat-num">{{ stats.success }}</span> 成功</div>
      <div class="stat err"><span class="stat-num">{{ stats.failed }}</span> 失败</div>
      <div class="stat warn"><span class="stat-num">{{ stats.avgDurationMs }}</span> ms 平均耗时</div>
    </div>

    <!-- ═══ Filters & Search ═══ -->
    <div class="filters">
      <div class="flex gap">
        <input v-model="search" placeholder="搜索命令或工作目录…" class="in flex1" @keyup.enter="load(0)" />
        <select v-model="exitFilter" class="in w100" @change="load(0)">
          <option value="all">全部状态</option>
          <option value="success">仅成功</option>
          <option value="failure">仅失败</option>
        </select>
        <button class="bt btp" @click="load(0)">搜索</button>
        <button class="bt" @click="loadStats">统计</button>
      </div>
    </div>

    <!-- ═══ Entries List ═══ -->
    <div v-if="loading" class="em">加载中…</div>
    <div v-else-if="!entries.length" class="em">暂无命令记录</div>
    <div v-else class="list">
      <div v-for="e in entries" :key="e.id" class="entry" @click="toggleDetail(e.id)">
        <div class="entry-left">
          <span :class="['dot', e.exit_code === 0 ? 'ok' : 'err']" />
          <div class="entry-main">
            <code class="cmdline">{{ e.command }}</code>
            <div class="meta">
              <span class="meta-item">{{ e.cwd || '-' }}</span>
              <span class="meta-item" v-if="e.start_time">{{ fmtTime(e.start_time) }}</span>
              <span class="meta-item">{{ fmtDur(e.duration_ms) }}</span>
              <span class="meta-item">PID {{ e.pid }}</span>
            </div>
          </div>
        </div>
        <div class="entry-right">
          <span :class="['tag', e.exit_code === 0 ? 'ok' : 'err']">{{ e.exit_code === 0 ? 'PASS' : `ERR ${e.exit_code}` }}</span>
          <button class="bt btm" @click.stop="copyCmd(e.command)" title="复制命令">⎘</button>
        </div>
      </div>

      <!-- ═══ Detail Panel ═══ -->
      <div v-if="selectedId && selected" class="detail">
        <div class="detail-tabs">
          <button :class="['dt', { act: detailTab === 'stdout' }]" @click="detailTab = 'stdout'">stdout</button>
          <button :class="['dt', { act: detailTab === 'stderr' }]" @click="detailTab = 'stderr'">stderr</button>
          <button :class="['dt', { act: detailTab === 'info' }]" @click="detailTab = 'info'">详情</button>
          <span class="spacer" />
          <button class="bt" @click="selectedId = ''">✕ 收起</button>
        </div>
        <div v-if="detailTab === 'stdout'" class="out">
          <pre v-if="selected.stdout">{{ selected.stdout }}</pre>
          <div v-else class="em">(无输出)</div>
        </div>
        <div v-if="detailTab === 'stderr'" class="out">
          <pre v-if="selected.stderr">{{ selected.stderr }}</pre>
          <div v-else class="em">(无错误)</div>
        </div>
        <div v-if="detailTab === 'info'" class="detail-info">
          <div><span class="lbl">命令：</span><code>{{ selected.command }}</code></div>
          <div><span class="lbl">目录：</span>{{ selected.cwd || '-' }}</div>
          <div><span class="lbl">退出码：</span><span :class="{ 'ok': selected.exit_code === 0, 'err': selected.exit_code !== 0 }">{{ selected.exit_code }}</span></div>
          <div><span class="lbl">PID：</span>{{ selected.pid }}</div>
          <div><span class="lbl">开始时间：</span>{{ selected.start_time ? fmtTime(selected.start_time) : '-' }}</div>
          <div><span class="lbl">结束时间：</span>{{ selected.end_time ? fmtTime(selected.end_time) : '-' }}</div>
          <div><span class="lbl">耗时：</span>{{ fmtDur(selected.duration_ms) }}</div>
          <div><span class="lbl">环境变量：</span></div>
          <pre v-if="selected.env" class="env">{{ selected.env }}</pre>
          <div v-else class="em2">(无)</div>
        </div>
      </div>
    </div>

    <!-- ═══ Pagination ═══ -->
    <div v-if="total > limit" class="pager">
      <button class="bt" :disabled="offset <= 0" @click="load(offset - limit)">← 上一页</button>
      <span class="pginfo">{{ offset + 1 }}-{{ Math.min(offset + limit, total) }} / {{ total }}</span>
      <button class="bt" :disabled="offset + limit >= total" @click="load(offset + limit)">下一页 →</button>
    </div>

    <!-- ═══ Toast ═══ -->
    <teleport to="body">
      <div v-if="toast" class="toast">{{ toast }}</div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { cliHistoryApi, type CLIEntry, type CLIStats } from '@/api/cliHistory'

const limit = 15

// ── State ──
const entries = ref<CLIEntry[]>([])
const total = ref(0)
const offset = ref(0)
const loading = ref(false)
const search = ref('')
const exitFilter = ref<'all' | 'success' | 'failure'>('all')
const stats = ref<CLIStats | null>(null)
const selectedId = ref<string | number>('')
const detailTab = ref<'stdout' | 'stderr' | 'info'>('stdout')
const toast = ref('')

const selected = computed(() => entries.value.find(e => e.id === selectedId.value) ?? null)

onMounted(() => load(0))

// ── Load ──
async function load(newOffset: number) {
  offset.value = newOffset
  loading.value = true
  try {
    const params: Record<string, any> = { limit, offset: newOffset }
    if (search.value) params.search = search.value
    if (exitFilter.value === 'success') params.exit_code = 0
    if (exitFilter.value === 'failure') params.exit_not_zero = true

    const r = await cliHistoryApi.listEntries(params)
    entries.value = (r.data as any)?.data ?? (r.data as any)?.items ?? []
    total.value = (r.data as any)?.total ?? 0
  } catch { /* ignore */ }
  finally { loading.value = false }
}

async function loadStats() {
  try {
    const r = await cliHistoryApi.getStats()
    stats.value = r.data as CLIStats
  } catch { /* ignore */ }
}

// ── Actions ──
function toggleDetail(id: string | number) {
  selectedId.value = selectedId.value === id ? '' : id
  if (selectedId.value) detailTab.value = 'stdout'
}

async function copyCmd(cmd: string) {
  try { await navigator.clipboard.writeText(cmd); showToast('已复制 ✓') }
  catch { showToast('复制失败') }
}

function showToast(msg: string) {
  toast.value = msg
  setTimeout(() => toast.value = '', 1800)
}

// ── Formatting ──
function fmtTime(ts: string): string {
  if (!ts) return '-'
  try { return new Date(ts).toLocaleString() } catch { return ts }
}

function fmtDur(ms: number | undefined): string {
  if (ms == null) return '-'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const m = Math.floor(ms / 60000)
  const s = ((ms % 60000) / 1000).toFixed(0)
  return `${m}m ${s}s`
}
</script>

<style scoped>
.page { max-width: 960px; margin: 0 auto; padding: 24px; }
h2 { margin: 0 0 4px; }
.sub { color: var(--color-ide-text-secondary); font-size: 14px; margin-bottom: 16px; }

/* ── Stats ── */
.stats { display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.stat { background: var(--color-ide-bg-secondary); border: 1px solid var(--color-ide-border); border-radius: 8px; padding: 10px 16px; font-size: 13px; color: var(--color-ide-text-secondary); }
.stat-num { font-size: 20px; font-weight: 700; color: var(--color-ide-text-primary); display: block; }
.stat.ok .stat-num { color: #81c784; }
.stat.err .stat-num { color: #e57373; }
.stat.warn .stat-num { color: #ffd54f; }

/* ── Filters ── */
.filters { margin-bottom: 16px; }
.in { padding: 7px 10px; border: 1px solid var(--color-ide-border); border-radius: 6px; background: var(--color-ide-bg-secondary); color: var(--color-ide-text-primary); font-size: 13px; }
.in:focus { outline: none; border-color: var(--color-ide-accent); }
select.in { cursor: pointer; }
.flex { display: flex; align-items: center; }
.gap { gap: 8px; }
.flex1 { flex: 1; min-width: 200px; }
.w100 { width: 110px; }

/* ── Buttons ── */
.bt { padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer; font-size: 13px; background: var(--color-ide-bg-tertiary); color: var(--color-ide-text-primary); white-space: nowrap; transition: .15s; }
.bt:hover:not(:disabled) { opacity: .85; }
.bt:disabled { opacity: .4; cursor: not-allowed; }
.btp { background: var(--color-ide-accent); color: #fff; }
.btm { padding: 4px 8px; font-size: 13px; line-height: 1; border-radius: 4px; opacity: 0; transition: .15s; }

/* ── Entry List ── */
.list { display: flex; flex-direction: column; gap: 4px; }
.entry { display: flex; align-items: center; border: 1px solid var(--color-ide-border); border-radius: 8px; padding: 10px 14px; cursor: pointer; background: var(--color-ide-bg-secondary); transition: .15s; gap: 12px; }
.entry:hover { border-color: var(--color-ide-accent); background: var(--color-ide-bg-tertiary); }
.entry:hover .btm { opacity: 1; }
.entry-left { display: flex; gap: 10px; align-items: flex-start; flex: 1; min-width: 0; }
.entry-main { flex: 1; min-width: 0; }
.entry-right { display: flex; gap: 8px; align-items: center; flex-shrink: 0; }

.dot { width: 8px; height: 8px; border-radius: 50%; margin-top: 5px; flex-shrink: 0; }
.ok { color: #81c784; }
.err { color: #e57373; }
.dot.ok { background: #81c784; }
.dot.err { background: #e57373; }

.cmdline { font-family: monospace; font-size: 13px; color: var(--color-ide-text-primary); word-break: break-all; line-height: 1.4; }
.meta { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 4px; font-size: 11px; color: var(--color-ide-text-secondary); }
.meta-item { white-space: nowrap; }
.tag { font-size: 10px; padding: 2px 6px; border-radius: 4px; font-weight: 700; font-family: monospace; white-space: nowrap; }
.tag.ok { background: #1e3a2e; color: #81c784; }
.tag.err { background: #3e1a1a; color: #e57373; }

/* ── Detail Panel ── */
.detail { border: 1px solid var(--color-ide-accent); border-radius: 8px; overflow: hidden; margin-top: 8px; background: var(--color-ide-bg-secondary); }
.detail-tabs { display: flex; gap: 0; align-items: center; border-bottom: 1px solid var(--color-ide-border); background: var(--color-ide-bg-tertiary); padding: 0 8px; }
.dt { padding: 8px 14px; border: none; border-bottom: 2px solid transparent; background: none; color: var(--color-ide-text-secondary); font-size: 12px; cursor: pointer; transition: .15s; }
.dt:hover { color: var(--color-ide-text-primary); }
.dt.act { color: var(--color-ide-accent); border-bottom-color: var(--color-ide-accent); font-weight: 600; }
.spacer { flex: 1; }
.out { padding: 14px; max-height: 300px; overflow: auto; }
.out pre { margin: 0; font-family: monospace; font-size: 12px; white-space: pre-wrap; word-break: break-all; color: var(--color-ide-text-primary); line-height: 1.5; }
.detail-info { padding: 14px; font-size: 12px; display: flex; flex-direction: column; gap: 6px; }
.detail-info code { background: var(--color-ide-bg-tertiary); padding: 2px 6px; border-radius: 4px; font-size: 11px; }
.env { margin: 4px 0 0; font-family: monospace; font-size: 11px; background: var(--color-ide-bg-primary); padding: 8px; border-radius: 4px; max-height: 200px; overflow: auto; white-space: pre-wrap; }

/* ── Misc ── */
.lbl { font-size: 12px; color: var(--color-ide-text-secondary); }
.em { text-align: center; padding: 32px; color: var(--color-ide-text-secondary); font-size: 13px; }
.em2 { font-size: 12px; color: var(--color-ide-text-secondary); }
.pager { display: flex; justify-content: center; align-items: center; gap: 14px; margin-top: 20px; }
.pginfo { font-size: 13px; color: var(--color-ide-text-secondary); }

/* ── Toast ── */
.toast { position: fixed; bottom: 32px; left: 50%; transform: translateX(-50%); background: var(--color-ide-bg-tertiary); border: 1px solid var(--color-ide-border); border-radius: 8px; padding: 8px 20px; font-size: 13px; color: var(--color-ide-text-primary); z-index: 2000; box-shadow: 0 4px 12px rgba(0,0,0,.3); }
</style>
