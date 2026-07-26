<template>
  <div class="ff-page">
    <div class="page-header">
      <h2>Feature Flags</h2>
      <p class="subtitle">特性开关管理 — 支持 Boolean / Percentage / Experiment 三种类型</p>
    </div>

    <!-- 新建区 -->
    <div class="create-section">
      <button class="btn btn-primary" @click="showForm = !showForm">
        {{ showForm ? '取消' : '+ 新建开关' }}
      </button>
      <form v-if="showForm" class="create-form" @submit.prevent="submitCreate">
        <input v-model="form.name" placeholder="开关名称" class="input" required />
        <input v-model="form.description" placeholder="描述" class="input" />
        <select v-model="form.flag_type" class="input">
          <option value="boolean">Boolean</option>
          <option value="percentage">Percentage</option>
          <option value="experiment">Experiment</option>
        </select>
        <label v-if="form.flag_type === 'percentage'" class="input-row">
          灰度比例:
          <input v-model.number="form.rollout_percent" type="number" min="0" max="100" class="input-sm" />
          %
        </label>
        <div v-if="form.flag_type === 'experiment'" class="variant-section">
          <p class="label">实验变体</p>
          <div v-for="(v, i) in form.variants" :key="i" class="variant-row">
            <input v-model="v.name" placeholder="变体名" class="input-sm" />
            <input v-model.number="v.weight" type="number" placeholder="权重" class="input-sm" min="1" />
            <button type="button" class="btn btn-sm btn-outline" @click="form.variants.splice(i, 1)">x</button>
          </div>
          <button type="button" class="btn btn-sm" @click="form.variants.push({ name: '', weight: 50 })">
            + 变体
          </button>
        </div>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary" :disabled="!form.name.trim()">创建/更新</button>
        </div>
      </form>
    </div>

    <!-- 开关列表 -->
    <div v-if="loading" class="loading">加载中...</div>
    <div v-else-if="flags.length === 0" class="empty">暂无特性开关</div>

    <div v-else class="flag-list">
      <div v-for="f in flags" :key="f.name" class="flag-card">
        <div class="flag-header">
          <span class="flag-name">{{ f.name }}</span>
          <span :class="['badge', typeClass(f.flag_type)]">{{ f.flag_type }}</span>
          <span :class="['badge', f.enabled ? 'badge-ok' : 'badge-off']">
            {{ f.enabled ? '启用' : '停用' }}
          </span>
        </div>
        <div v-if="f.description" class="flag-desc">{{ f.description }}</div>
        <div v-if="f.rollout_percent !== undefined && f.rollout_percent < 100" class="rollout">
          灰度: {{ f.rollout_percent }}%
        </div>
        <div v-if="f.variants?.length" class="variants">
          变体: {{ f.variants.map(v => `${v.name}(${v.weight}%)`).join(', ') }}
        </div>

        <div class="flag-actions">
          <div class="eval-section">
            <input v-model="evalInputs[f.name]" placeholder="User ID" class="input-sm" />
            <button class="btn btn-sm" @click="doEvaluate(f.name, evalInputs[f.name] || 'default')">
              评估
            </button>
          </div>
          <button class="btn btn-sm btn-outline" @click="toggleFlag(f)">切换</button>
          <button class="btn btn-sm btn-outline" @click="deleteFlag(f.name)">删除</button>
        </div>

        <div v-if="evalResults[f.name]" class="eval-result">
          <span :class="['result-dot', evalResults[f.name].active ? 'active' : 'inactive']"></span>
          {{ evalResults[f.name].active ? '命中' : '未命中' }}
          <span v-if="evalResults[f.name].variant"> | 变体: {{ evalResults[f.name].variant }}</span>
          <span v-if="evalResults[f.name].bucket !== undefined"> | bucket: {{ evalResults[f.name].bucket }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { featureFlagsApi, type FeatureFlag, type EvalResult } from '@/api/featureFlags'

const flags = ref<FeatureFlag[]>([])
const loading = ref(false)
const showForm = ref(false)
const evalInputs = reactive<Record<string, string>>({})
const evalResults = reactive<Record<string, EvalResult>>({})

const form = reactive({
  name: '',
  description: '',
  flag_type: 'boolean' as 'boolean' | 'percentage' | 'experiment',
  rollout_percent: 100,
  variants: [] as Array<{ name: string; weight: number }>,
})

function typeClass(t: string) {
  return { boolean: 'badge-info', percentage: 'badge-warn', experiment: 'badge-purple' }[t] ?? ''
}

async function fetchFlags() {
  loading.value = true
  try {
    const res = await featureFlagsApi.list()
    flags.value = res.data ?? []
  } finally {
    loading.value = false
  }
}

async function submitCreate() {
  await featureFlagsApi.createOrUpdate({
    name: form.name,
    description: form.description,
    flag_type: form.flag_type,
    rollout_percent: form.rollout_percent,
    variants: form.variants.filter(v => v.name),
  })
  showForm.value = false
  resetForm()
  await fetchFlags()
}

function resetForm() {
  form.name = ''
  form.description = ''
  form.flag_type = 'boolean'
  form.rollout_percent = 100
  form.variants = []
}

async function toggleFlag(f: FeatureFlag) {
  await featureFlagsApi.createOrUpdate({ ...f, enabled: !f.enabled })
  await fetchFlags()
}

async function deleteFlag(name: string) {
  if (!confirm(`确认删除开关 "${name}"？`)) return
  await featureFlagsApi.delete(name)
  await fetchFlags()
}

async function doEvaluate(name: string, userId: string) {
  try {
    const res = await featureFlagsApi.evaluate(name, userId)
    evalResults[name] = res.data ?? res
  } catch (e: any) {
    evalResults[name] = { flag_name: name, flag_type: '', active: false, variant: '', config: {} }
  }
}

onMounted(fetchFlags)
</script>

<style scoped>
.ff-page {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
}

.page-header h2 { margin: 0; font-size: 22px; }
.subtitle { color: var(--color-ide-text-secondary); margin: 4px 0 16px; font-size: 14px; }

.create-section { margin-bottom: 24px; }
.create-form {
  margin-top: 12px; padding: 16px;
  border: 1px solid var(--color-ide-border); border-radius: 8px;
  background: var(--color-ide-bg-secondary);
  display: flex; flex-direction: column; gap: 10px;
  max-width: 420px;
}
.input {
  padding: 6px 10px; border: 1px solid var(--color-ide-border);
  border-radius: 6px; background: var(--color-ide-bg-tertiary);
  color: var(--color-ide-text-primary); font-size: 13px;
}
.input-sm { width: 120px; }
.input-row { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.label { font-size: 12px; color: var(--color-ide-text-secondary); margin: 4px 0 0; }
.variant-section { display: flex; flex-direction: column; gap: 6px; }
.variant-row { display: flex; gap: 6px; align-items: center; }
.form-actions { margin-top: 4px; }

.flag-list { display: grid; gap: 12px; }
.flag-card {
  padding: 14px; border: 1px solid var(--color-ide-border);
  border-radius: 8px; background: var(--color-ide-bg-secondary);
}
.flag-header { display: flex; gap: 8px; align-items: center; margin-bottom: 6px; }
.flag-name { font-weight: 700; font-size: 15px; }
.flag-desc { font-size: 13px; color: var(--color-ide-text-secondary); margin-bottom: 4px; }
.rollout { font-size: 12px; color: var(--color-ide-text-secondary); }
.variants { font-size: 12px; color: var(--color-ide-text-secondary); }

.flag-actions {
  display: flex; gap: 8px; align-items: center;
  margin-top: 10px; padding-top: 10px;
  border-top: 1px solid var(--color-ide-border);
}
.eval-section { display: flex; gap: 6px; align-items: center; flex: 1; }

.eval-result {
  margin-top: 8px; padding: 6px 10px;
  background: var(--color-ide-bg-tertiary); border-radius: 6px;
  font-size: 13px; display: flex; align-items: center; gap: 6px;
}
.result-dot { width: 8px; height: 8px; border-radius: 50%; }
.result-dot.active { background: #81c784; }
.result-dot.inactive { background: #e57373; }

.badge {
  font-size: 11px; padding: 2px 8px; border-radius: 10px;
  background: var(--color-ide-bg-tertiary); color: var(--color-ide-text-secondary);
}
.badge-info { background: #1e3a5f; color: #64b5f6; }
.badge-warn { background: #3e3a1e; color: #ffb74d; }
.badge-purple { background: #2e1e4a; color: #ba68c8; }
.badge-ok { background: #1e3a2e; color: #81c784; }
.badge-off { background: #3e1e1e; color: #e57373; }

.loading, .empty { text-align: center; padding: 40px; color: var(--color-ide-text-secondary); }

.btn {
  padding: 6px 14px; border: none; border-radius: 6px; cursor: pointer;
  font-size: 13px; background: var(--color-ide-bg-tertiary);
  color: var(--color-ide-text-primary);
  transition: opacity 0.15s;
}
.btn:hover { opacity: 0.85; }
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-outline { border: 1px solid var(--color-ide-border); background: transparent; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
