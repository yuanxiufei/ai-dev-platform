<template>
  <div class="jobs-page">
    <div class="page-header">
      <h2>定时任务</h2>
      <button class="btn btn-primary" @click="showCreate = true">+ 新建任务</button>
    </div>

    <div class="jobs-grid">
      <div v-for="job in jobs" :key="job.id" class="job-card" :class="{ paused: !job.enabled }">
        <div class="job-top">
          <div class="job-title-row">
            <span class="job-icon" :style="{ background: statusColor(job.lastStatus) }">{{ job.icon }}</span>
            <div>
              <div class="job-title">{{ job.name }}</div>
              <div class="job-cron">{{ job.cron }} · {{ cronLabel(job.cron) }}</div>
            </div>
          </div>
          <div class="job-controls">
            <button class="btn-sm" :class="job.enabled ? 'btn-pause' : 'btn-start'" @click="toggleJob(job.id)">
              {{ job.enabled ? '暂停' : '启动' }}
            </button>
            <button class="btn-sm btn-danger" @click="deleteJob(job.id)">删除</button>
          </div>
        </div>
        <div class="job-body">
          <div class="job-field">
            <span class="field-label">技能</span>
            <span class="field-value">{{ job.skill }}</span>
          </div>
          <div class="job-field">
            <span class="field-label">提示词</span>
            <span class="field-value text-truncate">{{ job.prompt }}</span>
          </div>
          <div class="job-meta">
            <span class="meta-item">上次运行: {{ job.lastRun || '—' }}</span>
            <span class="meta-item" :class="'status-' + job.lastStatus">
              {{ statusText(job.lastStatus) }}
            </span>
            <span class="meta-item">下次: {{ nextRunLabel(job.cron) }}</span>
          </div>
        </div>
      </div>

      <div v-if="jobs.length === 0" class="empty-state">
        <p>暂无定时任务</p>
      </div>
    </div>

    <!-- Create Modal -->
    <Teleport to="body">
      <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
        <div class="modal-card">
          <h3>新建定时任务</h3>
          <form @submit.prevent="createJob">
            <div class="field">
              <label>任务名称</label>
              <input v-model="form.name" class="input" placeholder="例如：每日代码审查" />
            </div>
            <div class="field">
              <label>Cron 表达式</label>
              <input v-model="form.cron" class="input" placeholder="0 9 * * *" />
              <span class="field-hint">{{ cronLabel(form.cron || '0 0 * * *') }}</span>
            </div>
            <div class="field-row">
              <div class="field flex-1">
                <label>技能</label>
                <select v-model="form.skill" class="select">
                  <option value="code-review">代码审查</option>
                  <option value="test-gen">测试生成</option>
                  <option value="refactor">代码重构</option>
                  <option value="explain">代码解释</option>
                </select>
              </div>
              <div class="field flex-1">
                <label>模型</label>
                <select v-model="form.model" class="select">
                  <option value="deepseek-chat">DeepSeek Chat</option>
                  <option value="gpt-4o">GPT-4o</option>
                  <option value="claude-sonnet-4">Claude Sonnet</option>
                </select>
              </div>
            </div>
            <div class="field">
              <label>提示词</label>
              <textarea v-model="form.prompt" class="input textarea" rows="3" placeholder="描述任务内容" />
            </div>
            <div class="modal-actions">
              <button type="button" class="btn btn-ghost" @click="showCreate = false">取消</button>
              <button type="submit" class="btn btn-primary">创建任务</button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'

interface ScheduledJob {
  id: string
  name: string
  icon: string
  cron: string
  skill: string
  model: string
  prompt: string
  enabled: boolean
  lastRun: string
  lastStatus: 'success' | 'failed' | ''
}

const jobs = ref<ScheduledJob[]>([
  { id: '1', name: '每日代码审查', icon: '🔍', cron: '0 9 * * *', skill: 'code-review', model: 'deepseek-chat', prompt: '审查昨日提交的所有代码变更', enabled: true, lastRun: '2026-07-02 09:00', lastStatus: 'success' },
  { id: '2', name: '周报生成', icon: '📊', cron: '0 18 * * 5', skill: 'explain', model: 'gpt-4o', prompt: '生成本周工作总结和项目进度报告', enabled: true, lastRun: '2026-06-30 18:00', lastStatus: 'success' },
  { id: '3', name: '安全扫描', icon: '🛡️', cron: '0 2 * * *', skill: 'code-review', model: 'claude-sonnet-4', prompt: '扫描最新代码变更中的安全问题', enabled: false, lastRun: '', lastStatus: '' },
])

const showCreate = ref(false)
const form = reactive({ name: '', cron: '', skill: 'code-review', model: 'deepseek-chat', prompt: '' })

function statusColor(s: string) { return s === 'success' ? '#4EC9B0' : s === 'failed' ? '#F48771' : '#858585' }
function statusText(s: string) { return s === 'success' ? '成功' : s === 'failed' ? '失败' : '待运行' }

function cronLabel(cron: string): string {
  const parts = cron.trim().split(/\s+/)
  if (parts.length < 5) return '无效表达式'
  const [min, hour, dom, month, dow] = parts
  if (hour === '*' && min === '*') return '每分钟'
  if (dom === '*' && month === '*') {
    if (dow === '*') return `每天 ${hour}:${min.padStart(2, '0')}`
    return `每周${dowName(dow)} ${hour}:${min.padStart(2,'0')}`
  }
  return `${month}/${dom} ${hour}:${min.padStart(2,'0')}`
}

function dowName(d: string) {
  return { '0': '日', '1': '一', '2': '二', '3': '三', '4': '四', '5': '五', '6': '六' }[d] || d
}

function nextRunLabel(cron: string) {
  const now = new Date()
  return now.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' }) + ' ' +
    cron.trim().split(/\s+/).slice(0, 2).reverse().join(':').replace(':', ':').padStart(5, '0')
}

function createJob() {
  if (!form.name) return
  jobs.value.push({
    id: String(Date.now()),
    name: form.name,
    icon: '⏰',
    cron: form.cron || '0 0 * * *',
    skill: form.skill,
    model: form.model,
    prompt: form.prompt,
    enabled: true,
    lastRun: '',
    lastStatus: '',
  })
  form.name = ''; form.cron = ''; form.prompt = ''
  showCreate.value = false
}

function toggleJob(id: string) {
  const job = jobs.value.find(j => j.id === id)
  if (job) job.enabled = !job.enabled
}

function deleteJob(id: string) {
  jobs.value = jobs.value.filter(j => j.id !== id)
}
</script>

<style scoped>
.jobs-page { height: 100%; display: flex; flex-direction: column; background: var(--color-ide-bg); color: var(--color-ide-text); }
.page-header {
  flex-shrink: 0; display: flex; align-items: center; justify-content: space-between;
  padding: 12px 20px; background: var(--color-ide-bg-secondary); border-bottom: 1px solid var(--color-ide-border);
}
.page-header h2 { font-size: 15px; font-weight: 600; }
.jobs-grid { flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 10px; }
.job-card {
  background: var(--color-ide-surface); border: 1px solid var(--color-ide-border);
  border-radius: 6px; padding: 14px 16px;
}
.job-card.paused { opacity: 0.6; }
.job-top { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 10px; }
.job-title-row { display: flex; align-items: center; gap: 10px; }
.job-icon {
  width: 32px; height: 32px; border-radius: 6px; display: flex; align-items: center; justify-content: center; color: #fff; font-size: 16px;
}
.job-title { font-size: 14px; font-weight: 600; }
.job-cron { font-size: 11px; color: var(--color-ide-text-dim); font-family: monospace; margin-top: 2px; }
.job-controls { display: flex; gap: 6px; }
.job-body { }
.job-field { display: flex; gap: 8px; margin-bottom: 4px; }
.field-label { font-size: 11px; color: var(--color-ide-text-dim); width: 50px; }
.field-value { font-size: 12px; }
.text-truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.job-meta { display: flex; gap: 16px; margin-top: 8px; }
.meta-item { font-size: 11px; color: var(--color-ide-text-dim); }
.status-success { color: var(--color-ide-success); }
.status-failed { color: var(--color-ide-error); }
.empty-state { text-align: center; padding: 60px; color: var(--color-ide-text-dim); }
/* Modal */
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.5);
  display: flex; align-items: center; justify-content: center; z-index: 300;
}
.modal-card {
  background: var(--color-ide-surface); border: 1px solid var(--color-ide-border);
  border-radius: 6px; width: 440px; max-width: 90vw; padding: 24px;
  box-shadow: var(--shadow-lg);
}
.modal-card h3 { font-size: 16px; color: var(--color-ide-text); margin-bottom: 20px; }
.field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 14px; }
.field.flex-1 { flex: 1; }
.field label { font-size: 12px; color: var(--color-ide-text-dim); }
.field-hint { font-size: 11px; color: var(--color-ide-accent); }
.field-row { display: flex; gap: 12px; }
.input {
  padding: 8px 12px; font-size: 13px; background: var(--color-chat-input-bg);
  border: 1px solid var(--color-ide-border); border-radius: 3px; color: var(--color-ide-text); outline: none;
}
.input:focus { border-color: var(--color-ide-border-focus); }
.textarea { resize: vertical; font-family: inherit; }
.select {
  padding: 7px 8px; font-size: 12px; background: var(--color-chat-input-bg);
  border: 1px solid var(--color-ide-border); border-radius: 3px; color: var(--color-ide-text); outline: none;
}
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
.btn {
  padding: 6px 16px; font-size: 12px; border-radius: 3px; border: none; cursor: pointer; font-weight: 600;
}
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-primary:hover { background: var(--color-ide-accent-hover); }
.btn-ghost { background: transparent; color: var(--color-ide-text); }
.btn-ghost:hover { background: rgba(255,255,255,0.06); }
.btn-sm { padding: 4px 10px; font-size: 11px; border-radius: 3px; border: none; cursor: pointer; }
.btn-start { background: var(--color-ide-success); color: #000; }
.btn-pause { background: var(--color-ide-warning); color: #000; }
.btn-danger { background: transparent; color: var(--color-ide-error); }
.btn-danger:hover { background: rgba(244,135,113,0.1); }
</style>
