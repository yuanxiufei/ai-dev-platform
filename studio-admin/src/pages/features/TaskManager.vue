<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { tasksApi, type TaskData, type TaskStepData } from '@/api/model-features'
import { RefreshCw, Plus, Search, Trash2, Play, CheckCircle, Clock, AlertCircle, XCircle, ChevronRight } from '@/components/icons'

const tasks = ref<TaskData[]>([])
const categories = ref<{ name: string; count: number }[]>([])
const total = ref(0)
const page = ref(1)
const filterStatus = ref('')
const filterCategory = ref('')
const loading = ref(false)
const showModal = ref(false)
const selectedTask = ref<TaskData | null>(null)
const showDetail = ref(false)
const newStepTitle = ref('')

const form = reactive({
  title: '', description: '', priority: 'medium', category: 'general', due_date: '',
  steps: [] as { title: string; description: string }[],
})

const statusColor: Record<string, string> = {
  todo: 'bg-gray-600', in_progress: 'bg-blue-500', blocked: 'bg-orange-500',
  completed: 'bg-green-500', cancelled: 'bg-red-500',
}
const statusIcon: Record<string, any> = {
  todo: Clock, in_progress: Play, blocked: AlertCircle, completed: CheckCircle, cancelled: XCircle,
}
const prioritySort = { critical: 0, high: 1, medium: 2, low: 3 }

async function loadTasks() {
  loading.value = true
  try {
    const [tRes, cRes] = await Promise.all([
      tasksApi.list({ page: page.value, size: 50, status: filterStatus.value || undefined, category: filterCategory.value || undefined }),
      tasksApi.categories(),
    ])
    tasks.value = tRes.data; total.value = tRes.total; categories.value = cRes.categories
  } finally { loading.value = false }
}

function openCreate() { selectedTask.value = null; resetForm(); showModal.value = true }

function addStepField() { form.steps.push({ title: '', description: '' }) }
function removeStepField(idx: number) { form.steps.splice(idx, 1) }

async function saveTask() {
  if (!form.title) return
  if (selectedTask.value) {
    await tasksApi.update(selectedTask.value.id, { ...form, steps: undefined })
  } else {
    await tasksApi.create({ ...form })
  }
  showModal.value = false; resetForm(); loadTasks()
}

async function autoGenerate() {
  const count = prompt('生成步骤数量 (1-10):', '3')
  if (!count) return
  await tasksApi.autoGenerate(form.title, form.description, form.category, parseInt(count))
  loadTasks(); showModal.value = false; resetForm()
}

async function updateStatus(taskId: string, newStatus: string) {
  await tasksApi.update(taskId, { status: newStatus })
  loadTasks()
}

async function deleteTask(id: string) {
  if (!confirm('删除此任务？')) return
  await tasksApi.delete(id); loadTasks()
}

async function viewDetail(id: string) {
  const res = await tasksApi.get(id)
  selectedTask.value = res.task; showDetail.value = true
}

async function startTask(id: string) {
  const res = await tasksApi.start(id)
  selectedTask.value = res.task; showDetail.value = true
  loadTasks()
}

function resetForm() {
  form.title = ''; form.description = ''; form.priority = 'medium'
  form.category = 'general'; form.due_date = ''; form.steps = []
}

onMounted(loadTasks)
</script>

<template>
  <div class="p-6">
    <header class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-white">任务管理</h1>
        <p class="text-sm text-gray-400 mt-1">AI 多步骤工作流 — 跟踪项目生成、代码审查等任务进度</p>
      </div>
      <button @click="openCreate" class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium">
        <Plus class="w-4 h-4" /> 创建任务
      </button>
    </header>

    <!-- Filters -->
    <div class="flex items-center gap-3 mb-4">
      <select v-model="filterStatus" @change="loadTasks" class="px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white">
        <option value="">全部状态</option>
        <option value="todo">待开始</option>
        <option value="in_progress">进行中</option>
        <option value="blocked">已阻塞</option>
        <option value="completed">已完成</option>
        <option value="cancelled">已取消</option>
      </select>
      <select v-model="filterCategory" @change="loadTasks" class="px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white">
        <option value="">全部分类</option>
        <option v-for="c in categories" :key="c.name" :value="c.name">{{ c.name }} ({{ c.count }})</option>
      </select>
    </div>

    <div v-if="loading" class="flex items-center justify-center py-12"><RefreshCw class="w-6 h-6 animate-spin text-gray-500" /></div>
    <div v-else-if="tasks.length === 0" class="text-center py-12 text-gray-500">暂无任务</div>
    <div v-else class="space-y-2">
      <div v-for="task in tasks" :key="task.id" class="flex items-center gap-4 p-4 rounded-xl bg-surface-800 border border-white/5 hover:border-brand-500/30 transition group cursor-pointer" @click="viewDetail(task.id)">
        <component :is="statusIcon[task.status]" :class="['w-5 h-5 shrink-0', task.status === 'completed' ? 'text-green-400' : task.status === 'in_progress' ? 'text-blue-400' : task.status === 'blocked' ? 'text-orange-400' : 'text-gray-500']" />
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <h3 class="font-medium text-white truncate">{{ task.title }}</h3>
            <span :class="['text-xs px-1.5 py-0.5 rounded', statusColor[task.status] + ' text-white']">{{ { todo: '待开始', in_progress: '进行中', blocked: '阻塞', completed: '完成', cancelled: '取消' }[task.status] }}</span>
            <span :class="['text-xs px-1.5 py-0.5 rounded',
              task.priority === 'critical' ? 'bg-red-500/20 text-red-400' :
              task.priority === 'high' ? 'bg-orange-500/20 text-orange-400' :
              'bg-surface-700 text-gray-400']">{{ task.priority }}</span>
            <span class="text-xs text-gray-500">{{ task.category }}</span>
          </div>
          <div class="flex items-center gap-2">
            <div class="flex-1 h-1.5 bg-surface-700 rounded-full overflow-hidden">
              <div :class="['h-full rounded-full transition-all', task.progress >= 100 ? 'bg-green-500' : 'bg-brand-500']" :style="{ width: task.progress + '%' }" />
            </div>
            <span class="text-xs text-gray-500">{{ task.progress }}%</span>
          </div>
        </div>
        <div class="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition">
          <button v-if="task.status === 'todo'" @click.stop="startTask(task.id)" title="开始" class="p-1.5 rounded-lg hover:bg-blue-500/20"><Play class="w-4 h-4 text-blue-400" /></button>
          <select v-if="task.status === 'in_progress'" @click.stop @change="updateStatus(task.id, ($event.target as HTMLSelectElement).value)" class="text-xs px-2 py-1 rounded bg-surface-700 border border-white/10 text-white">
            <option value="in_progress">进行中</option>
            <option value="blocked">阻塞</option>
            <option value="completed">完成</option>
          </select>
          <button @click.stop="deleteTask(task.id)" class="p-1.5 rounded-lg hover:bg-red-500/20"><Trash2 class="w-4 h-4 text-red-400" /></button>
        </div>
      </div>
    </div>

    <!-- Detail Modal -->
    <Teleport to="body">
      <div v-if="showDetail && selectedTask" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="showDetail = false">
        <div class="bg-surface-900 rounded-xl border border-white/10 w-[600px] max-h-[80vh] flex flex-col">
          <div class="flex items-center justify-between p-4 border-b border-white/10">
            <h3 class="font-medium text-white">{{ selectedTask.title }}</h3>
            <button @click="showDetail = false" class="text-gray-400">✕</button>
          </div>
          <div class="flex-1 overflow-auto p-4 space-y-3">
            <p class="text-sm text-gray-400">{{ selectedTask.description || '无描述' }}</p>
            <div class="flex items-center gap-3 text-sm text-gray-500">
              <span>进度: <strong class="text-white">{{ selectedTask.progress }}%</strong></span>
              <span>步骤: {{ selectedTask.steps.filter(s => s.status === 'completed').length }}/{{ selectedTask.steps.length }}</span>
            </div>
            <!-- Steps -->
            <div v-if="selectedTask.steps.length" class="space-y-2">
              <h4 class="text-sm font-medium text-white">任务步骤</h4>
              <div v-for="step in [...selectedTask.steps].sort((a, b) => a.order - b.order)" :key="step.id" class="flex items-start gap-3 p-3 rounded-lg bg-surface-800 border border-white/5">
                <component :is="statusIcon[step.status]" :class="['w-4 h-4 mt-0.5 shrink-0', step.status === 'completed' ? 'text-green-400' : step.status === 'in_progress' ? 'text-blue-400' : 'text-gray-600']" />
                <div class="flex-1 min-w-0">
                  <span class="text-sm text-white">{{ step.title }}</span>
                  <p v-if="step.description" class="text-xs text-gray-500 mt-0.5">{{ step.description }}</p>
                  <p v-if="step.result" class="text-xs text-green-400 mt-1 font-mono">{{ step.result.substring(0, 200) }}</p>
                </div>
                <span :class="['text-xs px-1.5 py-0.5 rounded', statusColor[step.status] + ' text-white']">{{ { todo: '待开始', in_progress: '进行中', blocked: '阻塞', completed: '完成', cancelled: '取消' }[step.status] }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Create Modal (simplified) -->
    <Teleport to="body">
      <div v-if="showModal" class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" @click.self="showModal = false">
        <div class="bg-surface-900 rounded-xl border border-white/10 w-[520px] max-h-[85vh] flex flex-col">
          <div class="flex items-center justify-between p-4 border-b border-white/10">
            <h3 class="font-medium text-white">创建任务</h3>
            <button @click="showModal = false" class="text-gray-400">✕</button>
          </div>
          <div class="flex-1 overflow-auto p-4 space-y-3">
            <div>
              <label class="block text-xs text-gray-400 mb-1">标题 *</label>
              <input v-model="form.title" placeholder="任务标题" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white" />
            </div>
            <div>
              <label class="block text-xs text-gray-400 mb-1">描述</label>
              <textarea v-model="form.description" rows="3" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white resize-none" />
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-xs text-gray-400 mb-1">优先级</label>
                <select v-model="form.priority" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white">
                  <option value="low">低</option><option value="medium">中</option><option value="high">高</option><option value="critical">紧急</option>
                </select>
              </div>
              <div>
                <label class="block text-xs text-gray-400 mb-1">分类</label>
                <input v-model="form.category" placeholder="studio" class="w-full px-3 py-2 bg-surface-800 border border-white/10 rounded-lg text-sm text-white" />
              </div>
            </div>
          </div>
          <div class="flex gap-2 justify-end p-4 border-t border-white/10">
            <button @click="autoGenerate" class="px-3 py-2 rounded-lg bg-purple-500/20 hover:bg-purple-500/30 text-purple-400 text-sm">🤖 AI 生成步骤</button>
            <button @click="showModal = false" class="px-4 py-2 rounded-lg bg-surface-800 hover:bg-surface-700 text-sm">取消</button>
            <button @click="saveTask" class="px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium">创建</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
