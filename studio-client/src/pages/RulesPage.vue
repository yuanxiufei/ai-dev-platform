<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  listRules, createRule, updateRule, deleteRule, toggleRule, getRulesStats,
  type RuleItem, type RuleCreatePayload, type RuleUpdatePayload,
} from '@/api/rules'
import {
  ScrollText, Plus, Trash2, Edit3, Search, Loader2, X,
  Globe, FolderGit2, Tag, Clock, Shield,
} from 'lucide-vue-next'
import ToggleSwitch from '@/components/ToggleSwitch.vue'

const rules = ref<RuleItem[]>([])
const loading = ref(true)
const total = ref(0)
const page = ref(1)
const size = 20

const selectedType = ref('')
const searchQuery = ref('')
const debounceTimer = ref<ReturnType<typeof setTimeout>>()

const editRule = ref<RuleItem | null>(null)
const showCreate = ref(false)
const toast = ref('')

const stats = ref({ total: 0, enabled: 0, by_type: {} as Record<string, number>, by_scope: {} as Record<string, number> })

const form = ref<RuleCreatePayload>({
  name: '', description: '', rule_type: 'always', scope: 'project', content: '', triggers: [], priority: 0,
})

const tagInput = ref('')

const typeOptions = [
  { value: '', label: '全部', color: '' },
  { value: 'always', label: '始终生效', color: 'bg-green-400' },
  { value: 'requested', label: '按需加载', color: 'bg-amber-400' },
  { value: 'manual', label: '手动激活', color: 'bg-gray-500' },
]
const typeLabel: Record<string, string> = { always: '始终生效', requested: '按需加载', manual: '手动激活' }
const typeColor: Record<string, string> = {
  always: 'bg-green-500/10 text-green-400 border-green-500/20',
  requested: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  manual: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
}

function showToast(msg: string) {
  toast.value = msg
  setTimeout(() => { toast.value = '' }, 3000)
}

async function fetchRules() {
  loading.value = true
  try {
    const res = await listRules({
      page: page.value, size,
      type: selectedType.value || undefined,
      search: searchQuery.value || undefined,
    })
    rules.value = res.data.data
    total.value = res.data.total
  } catch {
    // ignore
  } finally { loading.value = false }
}

async function fetchStats() {
  try {
    const res = await getRulesStats()
    stats.value = res.data
  } catch { /* */ }
}

function debouncedSearch() {
  if (debounceTimer.value) clearTimeout(debounceTimer.value)
  debounceTimer.value = setTimeout(() => {
    page.value = 1
    fetchRules()
  }, 300)
}

function handleTypeChange(type: string) {
  selectedType.value = type
  page.value = 1
  fetchRules()
}

async function handleCreate() {
  if (!form.value.name || !form.value.content) return
  try {
    await createRule(form.value)
    showCreate.value = false
    form.value = { name: '', description: '', rule_type: 'always', scope: 'project', content: '', triggers: [], priority: 0 }
    showToast('规则已创建')
    await Promise.all([fetchRules(), fetchStats()])
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '创建失败')
  }
}

async function handleEdit(rule: RuleItem) {
  editRule.value = { ...rule }
}

async function saveEdit() {
  if (!editRule.value) return
  try {
    const { id, created_at, updated_at, ...rest } = editRule.value
    const payload: RuleUpdatePayload = { ...rest }
    await updateRule(id, payload)
    editRule.value = null
    showToast('规则已更新')
    await fetchRules()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '更新失败')
  }
}

async function handleDelete(id: string) {
  if (!confirm('确定删除此规则？')) return
  try {
    await deleteRule(id)
    showToast('规则已删除')
    await Promise.all([fetchRules(), fetchStats()])
  } catch (e: any) {
    showToast(e?.response?.data?.detail || '删除失败')
  }
}

async function handleToggle(rule: RuleItem) {
  try {
    await toggleRule(rule.id)
    rule.enabled = !rule.enabled
    fetchStats()
  } catch { /* */ }
}

function addTrigger() {
  const t = tagInput.value.trim()
  if (t && !form.value.triggers?.includes(t)) {
    form.value.triggers = [...(form.value.triggers || []), t]
    tagInput.value = ''
  }
}
function removeTrigger(t: string) {
  form.value.triggers = (form.value.triggers || []).filter(x => x !== t)
}

function addEditTrigger() {
  if (!editRule.value) return
  const t = tagInput.value.trim()
  if (t && !(editRule.value.triggers || []).includes(t)) {
    editRule.value.triggers = [...(editRule.value.triggers || []), t]
    tagInput.value = ''
  }
}
function removeEditTrigger(t: string) {
  if (!editRule.value) return
  editRule.value.triggers = (editRule.value.triggers || []).filter(x => x !== t)
}

onMounted(() => {
  Promise.all([fetchRules(), fetchStats()])
})

const enabledCount = computed(() => rules.value.filter(r => r.enabled).length)
</script>

<template>
  <div class="h-full flex flex-col">
    <!-- Toast -->
    <Transition name="toast">
      <div v-if="toast" class="fixed top-6 left-1/2 -translate-x-1/2 z-50 px-5 py-2.5 rounded-xl text-sm font-medium bg-green-500/15 border border-green-500/25 text-green-400 backdrop-blur-xl shadow-xl">
        {{ toast }}
      </div>
    </Transition>

    <!-- Header -->
    <div class="flex items-center justify-between px-8 pt-8 pb-6 border-b border-white/5">
      <div>
        <h1 class="text-2xl font-bold text-white flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-amber-500/20 to-orange-500/10 border border-amber-500/20 flex items-center justify-center">
            <ScrollText class="w-5 h-5 text-amber-400" />
          </div>
          规则管理
        </h1>
        <p class="text-sm text-gray-500 mt-1.5 ml-[3.25rem]">管理 AI 助手的行为规则，控制代码生成、安全审查、编码规范</p>
      </div>
      <button
        @click="showCreate = true"
        class="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium transition-colors shadow-lg shadow-brand-500/15"
      >
        <Plus class="w-4 h-4" />
        创建规则
      </button>
    </div>

    <div class="flex-1 flex overflow-hidden">
      <!-- Left sidebar -->
      <div class="w-52 shrink-0 border-r border-white/5 p-4 space-y-1">
        <p class="text-[11px] font-medium text-gray-500 uppercase tracking-wider px-2 mb-3">筛选</p>
        <button
          v-for="opt in typeOptions"
          :key="opt.value"
          @click="handleTypeChange(opt.value)"
          :class="[
            'w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all duration-200 text-left',
            selectedType === opt.value ? 'bg-brand-500/10 text-brand-400 font-medium' : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]',
          ]"
        >
          <div v-if="opt.color" :class="['w-1.5 h-1.5 rounded-full', opt.color]" />
          {{ opt.label }}
        </button>

        <div class="mt-6 px-2 space-y-2 text-xs">
          <div class="flex justify-between text-gray-600">
            <span class="flex items-center gap-1.5"><FolderGit2 class="w-3 h-3" /> 项目</span>
            <span>{{ stats.by_scope?.project || 0 }}</span>
          </div>
          <div class="flex justify-between text-gray-600">
            <span class="flex items-center gap-1.5"><Globe class="w-3 h-3" /> 用户</span>
            <span>{{ stats.by_scope?.user || 0 }}</span>
          </div>
        </div>

        <div class="mt-6 pt-4 border-t border-white/5 px-2">
          <div class="flex items-center gap-1.5 text-xs text-gray-600">
            <div class="w-1.5 h-1.5 rounded-full bg-green-400" />
            <span>{{ stats.enabled }} / {{ stats.total }} 已启用</span>
          </div>
        </div>
      </div>

      <!-- Main content -->
      <div class="flex-1 overflow-y-auto p-6">
        <!-- Search -->
        <div class="relative max-w-md mb-6">
          <Search class="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-600" />
          <input
            v-model="searchQuery"
            @input="debouncedSearch"
            placeholder="搜索规则名称或描述..."
            class="w-full bg-white/[0.03] border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-500/40 focus:bg-white/[0.05] transition-all"
          />
        </div>

        <!-- Loading -->
        <div v-if="loading" class="flex items-center justify-center py-24">
          <Loader2 class="w-8 h-8 animate-spin text-amber-400" />
        </div>

        <!-- Empty -->
        <div v-else-if="!rules.length" class="flex flex-col items-center justify-center py-24 text-gray-600">
          <Shield class="w-12 h-12 mb-4 opacity-30" />
          <p class="text-sm">还没有规则</p>
          <p class="text-xs mt-1 opacity-70 mb-6">创建第一条规则来约束 AI 行为</p>
          <button @click="showCreate = true" class="flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 text-sm transition-colors">
            <Plus class="w-4 h-4" />
            创建规则
          </button>
        </div>

        <!-- Rules list -->
        <div v-else class="space-y-3">
          <div
            v-for="rule in rules"
            :key="rule.id"
            :class="[
              'rounded-2xl border p-5 transition-all duration-200 group',
              rule.enabled ? 'border-white/8 bg-white/[0.02] hover:border-white/15' : 'border-white/5 bg-white/[0.01] opacity-60',
            ]"
          >
            <div class="flex items-start gap-4">
              <div class="pt-0.5">
                <ToggleSwitch :model-value="rule.enabled" size="md" @update:model-value="handleToggle(rule)" />
              </div>

              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-3 mb-1.5">
                  <h3 class="text-sm font-semibold text-white">{{ rule.name }}</h3>
                  <span :class="['text-[10px] px-2 py-0.5 rounded-full font-medium border', typeColor[rule.rule_type] || '']">
                    {{ typeLabel[rule.rule_type] }}
                  </span>
                  <span :class="['text-[10px] px-2 py-0.5 rounded-full border', rule.scope === 'project' ? 'bg-blue-500/10 text-blue-400 border-blue-500/20' : 'bg-purple-500/10 text-purple-400 border-purple-500/20']">
                    <FolderGit2 v-if="rule.scope === 'project'" class="w-2.5 h-2.5 inline mr-0.5" />
                    <Globe v-else class="w-2.5 h-2.5 inline mr-0.5" />
                    {{ rule.scope === 'project' ? '项目' : '用户' }}
                  </span>
                  <span class="text-[10px] text-gray-600 flex items-center gap-1 ml-auto">
                    <Clock class="w-3 h-3" />
                    {{ rule.updated_at?.slice(0, 10) || '-' }}
                  </span>
                </div>
                <p class="text-xs text-gray-500 mb-3">{{ rule.description || '无描述' }}</p>

                <!-- Triggers -->
                <div v-if="rule.triggers?.length" class="flex items-center gap-1.5 mb-3 flex-wrap">
                  <span class="text-[10px] text-gray-600">触发:</span>
                  <code v-for="t in rule.triggers" :key="t" class="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/5 text-gray-500 font-mono">{{ t }}</code>
                </div>

                <!-- Content preview -->
                <div class="p-2.5 rounded-lg bg-white/[0.02] border border-white/5">
                  <pre class="text-[11px] text-gray-500 whitespace-pre-wrap font-mono leading-relaxed line-clamp-3">{{ rule.content }}</pre>
                </div>
              </div>

              <!-- Actions -->
              <div class="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
                <button @click="handleEdit(rule)" class="p-2 rounded-lg text-gray-600 hover:text-gray-400 hover:bg-white/5 transition-colors" title="编辑">
                  <Edit3 class="w-4 h-4" />
                </button>
                <button @click="handleDelete(rule.id)" class="p-2 rounded-lg text-gray-600 hover:text-red-400 hover:bg-red-500/10 transition-colors" title="删除">
                  <Trash2 class="w-4 h-4" />
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="total > size" class="flex items-center justify-center gap-3 pt-6 mt-6 border-t border-white/5">
          <button :disabled="page <= 1" @click="page--; fetchRules()" class="px-4 py-2 rounded-xl bg-white/[0.03] border border-white/10 text-xs text-gray-400 hover:bg-white/[0.06] disabled:opacity-30 transition-colors">上一页</button>
          <span class="text-xs text-gray-600">{{ page }} / {{ Math.ceil(total / size) }}</span>
          <button :disabled="page >= Math.ceil(total / size)" @click="page++; fetchRules()" class="px-4 py-2 rounded-xl bg-white/[0.03] border border-white/10 text-xs text-gray-400 hover:bg-white/[0.06] disabled:opacity-30 transition-colors">下一页</button>
        </div>
      </div>
    </div>

    <!-- Create Modal -->
    <Teleport to="body">
      <div v-if="showCreate" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" @click.self="showCreate = false">
        <div class="bg-surface-900 rounded-2xl border border-white/10 w-[680px] max-h-[85vh] flex flex-col shadow-2xl">
          <div class="flex items-center justify-between p-5 border-b border-white/8">
            <h3 class="text-lg font-semibold text-white flex items-center gap-2"><Plus class="w-4 h-4 text-brand-400" />创建规则</h3>
            <button @click="showCreate = false" class="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 transition-colors"><X class="w-4 h-4" /></button>
          </div>
          <div class="flex-1 overflow-y-auto p-5 space-y-4">
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1.5">名称 <span class="text-red-400">*</span></label>
              <input v-model="form.name" placeholder="例如：Python 代码规范" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-500/40 transition-all" />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1.5">描述</label>
              <input v-model="form.description" placeholder="简要说明规则用途..." class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-500/40 transition-all" />
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-xs font-medium text-gray-400 mb-1.5">类型</label>
                <select v-model="form.rule_type" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white focus:outline-none focus:border-brand-500/40 transition-all">
                  <option value="always">始终生效</option>
                  <option value="requested">按需加载</option>
                  <option value="manual">手动激活</option>
                </select>
              </div>
              <div>
                <label class="block text-xs font-medium text-gray-400 mb-1.5">作用域</label>
                <select v-model="form.scope" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white focus:outline-none focus:border-brand-500/40 transition-all">
                  <option value="project">项目</option>
                  <option value="user">用户</option>
                </select>
              </div>
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1.5">触发文件 (glob)</label>
              <div class="flex gap-2">
                <input v-model="tagInput" @keyup.enter="addTrigger" placeholder="**/*.py → 回车添加" class="flex-1 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm font-mono text-white placeholder-gray-600 focus:outline-none focus:border-brand-500/40 transition-all" />
                <button @click="addTrigger" class="px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-sm text-gray-400 hover:text-white transition-colors">+</button>
              </div>
              <div v-if="form.triggers?.length" class="flex flex-wrap gap-1 mt-2">
                <span v-for="t in form.triggers" :key="t" class="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-brand-500/10 text-brand-400 font-mono">
                  {{ t }}
                  <button @click="removeTrigger(t)" class="hover:text-red-400"><X class="w-3 h-3" /></button>
                </span>
              </div>
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1.5">规则内容 <span class="text-red-400">*</span></label>
              <textarea v-model="form.content" rows="8" placeholder="编写规则内容..." class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white font-mono placeholder-gray-600 focus:outline-none focus:border-brand-500/40 transition-all resize-none"></textarea>
            </div>
          </div>
          <div class="flex gap-3 justify-end p-5 border-t border-white/8">
            <button @click="showCreate = false" class="px-5 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-sm text-gray-400 hover:text-white transition-colors">取消</button>
            <button @click="handleCreate()" :disabled="!form.name || !form.content" class="px-5 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors">创建规则</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Edit Modal -->
    <Teleport to="body">
      <div v-if="editRule" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" @click.self="editRule = null">
        <div class="bg-surface-900 rounded-2xl border border-white/10 w-[680px] max-h-[85vh] flex flex-col shadow-2xl">
          <div class="flex items-center justify-between p-5 border-b border-white/8">
            <h3 class="text-lg font-semibold text-white flex items-center gap-2"><Edit3 class="w-4 h-4 text-brand-400" />编辑规则</h3>
            <button @click="editRule = null" class="p-1.5 rounded-lg hover:bg-white/5 text-gray-500 transition-colors"><X class="w-4 h-4" /></button>
          </div>
          <div class="flex-1 overflow-y-auto p-5 space-y-4">
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1.5">名称</label>
              <input v-model="editRule.name" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white focus:outline-none focus:border-brand-500/40 transition-all" />
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1.5">描述</label>
              <input v-model="editRule.description" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white focus:outline-none focus:border-brand-500/40 transition-all" />
            </div>
            <div class="grid grid-cols-2 gap-4">
              <div>
                <label class="block text-xs font-medium text-gray-400 mb-1.5">类型</label>
                <select v-model="editRule.rule_type" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white focus:outline-none focus:border-brand-500/40 transition-all">
                  <option value="always">始终生效</option>
                  <option value="requested">按需加载</option>
                  <option value="manual">手动激活</option>
                </select>
              </div>
              <div>
                <label class="block text-xs font-medium text-gray-400 mb-1.5">作用域</label>
                <select v-model="editRule.scope" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white focus:outline-none focus:border-brand-500/40 transition-all">
                  <option value="project">项目</option>
                  <option value="user">用户</option>
                </select>
              </div>
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1.5">触发文件</label>
              <div class="flex gap-2">
                <input v-model="tagInput" @keyup.enter="addEditTrigger" placeholder="**/*.py → 回车添加" class="flex-1 rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm font-mono text-white placeholder-gray-600 focus:outline-none focus:border-brand-500/40 transition-all" />
                <button @click="addEditTrigger" class="px-3 py-2 rounded-xl bg-white/[0.04] border border-white/10 text-sm text-gray-400 hover:text-white transition-colors">+</button>
              </div>
              <div v-if="editRule.triggers?.length" class="flex flex-wrap gap-1 mt-2">
                <span v-for="t in editRule.triggers" :key="t" class="flex items-center gap-1 text-[10px] px-2 py-0.5 rounded bg-brand-500/10 text-brand-400 font-mono">
                  {{ t }}
                  <button @click="removeEditTrigger(t)" class="hover:text-red-400"><X class="w-3 h-3" /></button>
                </span>
              </div>
            </div>
            <div>
              <label class="block text-xs font-medium text-gray-400 mb-1.5">内容</label>
              <textarea v-model="editRule.content" rows="8" class="w-full rounded-xl border border-white/10 bg-white/[0.03] px-4 py-2.5 text-sm text-white font-mono focus:outline-none focus:border-brand-500/40 transition-all resize-none"></textarea>
            </div>
          </div>
          <div class="flex gap-3 justify-end p-5 border-t border-white/8">
            <button @click="editRule = null" class="px-5 py-2.5 rounded-xl bg-white/[0.04] border border-white/10 text-sm text-gray-400 hover:text-white transition-colors">取消</button>
            <button @click="saveEdit()" class="px-5 py-2.5 rounded-xl bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium transition-colors">保存</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.toast-enter-active, .toast-leave-active { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(-12px) translateX(-50%); }
</style>
