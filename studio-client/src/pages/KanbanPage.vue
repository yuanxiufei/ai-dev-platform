<template>
  <div class="kanban-page">
    <div class="kanban-header">
      <h2 class="page-title">Kanban 看板</h2>
      <div class="header-actions">
        <button class="btn btn-primary" @click="showCreateModal = true">+ 新建任务</button>
      </div>
    </div>

    <!-- Columns -->
    <div class="kanban-board">
      <div v-for="col in columns" :key="col.key" class="kanban-column"
        @dragover.prevent
        @drop="(e) => onDrop(e, col.key)"
      >
        <div class="column-header" :style="{ borderTopColor: col.color }">
          <div class="column-title-row">
            <span class="column-dot" :style="{ background: col.color }" />
            <span class="column-title">{{ col.label }}</span>
            <span class="column-count">{{ tasksByCol(col.key).length }}</span>
          </div>
        </div>
        <div class="column-body">
          <div
            v-for="task in tasksByCol(col.key)"
            :key="task.id"
            class="task-card"
            draggable="true"
            @dragstart="(e) => onDragStart(e, task.id)"
            @click="openTask(task)"
          >
            <div class="task-header">
              <span class="priority-dot" :class="'p-' + task.priority" />
              <span class="task-title">{{ task.title }}</span>
            </div>
            <p class="task-desc" v-if="task.description">{{ task.description }}</p>
            <div class="task-meta">
              <span class="task-tag" v-if="task.assignee">{{ task.assignee }}</span>
              <span class="task-date">{{ formatDate(task.createdAt) }}</span>
            </div>
          </div>
          <button class="add-task-btn" @click="openCreate(col.key)">+ 添加</button>
        </div>
      </div>
    </div>

    <!-- Create/Edit Modal -->
    <Teleport to="body">
      <div v-if="showCreateModal || editingTask" class="modal-overlay" @click.self="closeModal">
        <div class="modal-card">
          <h3 class="modal-title">{{ editingTask ? '编辑任务' : '新建任务' }}</h3>
          <form @submit.prevent="saveTask" class="modal-body">
            <div class="field">
              <label>标题</label>
              <input v-model="form.title" class="input" placeholder="任务标题" required />
            </div>
            <div class="field">
              <label>描述</label>
              <textarea v-model="form.description" class="input textarea" rows="3" placeholder="详细描述（可选）" />
            </div>
            <div class="field-row">
              <div class="field flex-1">
                <label>优先级</label>
                <select v-model="form.priority" class="select">
                  <option value="low">低</option>
                  <option value="medium">中</option>
                  <option value="high">高</option>
                  <option value="urgent">紧急</option>
                </select>
              </div>
              <div class="field flex-1">
                <label>状态</label>
                <select v-model="form.status" class="select">
                  <option v-for="c in columns" :key="c.key" :value="c.key">{{ c.label }}</option>
                </select>
              </div>
            </div>
            <div class="field">
              <label>负责人</label>
              <input v-model="form.assignee" class="input" placeholder="指派给（可选）" />
            </div>
            <div class="modal-actions">
              <button v-if="editingTask" type="button" class="btn btn-danger" @click="deleteTask">删除</button>
              <div class="flex-1" />
              <button type="button" class="btn btn-ghost" @click="closeModal">取消</button>
              <button type="submit" class="btn btn-primary">保存</button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'

interface Task {
  id: string
  title: string
  description: string
  status: string
  priority: 'low' | 'medium' | 'high' | 'urgent'
  assignee: string
  createdAt: string
}

const columns = [
  { key: 'backlog', label: '待规划', color: '#858585' },
  { key: 'todo', label: '待处理', color: '#3794FF' },
  { key: 'in-progress', label: '进行中', color: '#CCA700' },
  { key: 'review', label: '评审中', color: '#C586C0' },
  { key: 'done', label: '已完成', color: '#4EC9B0' },
]

const tasks = ref<Task[]>([
  { id: '1', title: '实现用户登录功能', description: '集成 JWT 认证，支持邮箱密码登录', status: 'done', priority: 'high', assignee: '小明', createdAt: '2026-07-01' },
  { id: '2', title: '优化代码生成速度', description: '使用缓存机制减少重复计算', status: 'in-progress', priority: 'high', assignee: '小红', createdAt: '2026-07-02' },
  { id: '3', title: '添加 Kanban 看板页面', description: '支持拖拽排序、任务管理', status: 'in-progress', priority: 'medium', assignee: '小张', createdAt: '2026-07-02' },
  { id: '4', title: '修复搜索功能 BUG', description: '输入中文时搜索结果不更新', status: 'todo', priority: 'urgent', assignee: '', createdAt: '2026-07-01' },
  { id: '5', title: '编写 API 文档', description: '使用 OpenAPI 3.0 规范', status: 'backlog', priority: 'low', assignee: '', createdAt: '2026-06-30' },
  { id: '6', title: '添加暗色主题切换', description: '支持 Dark/Light/HighContrast 三套主题', status: 'review', priority: 'medium', assignee: '小明', createdAt: '2026-06-29' },
])

const showCreateModal = ref(false)
const editingTask = ref<Task | null>(null)
const dragTaskId = ref<string | null>(null)

const form = reactive({
  title: '',
  description: '',
  priority: 'medium' as Task['priority'],
  status: 'backlog',
  assignee: '',
})

const defaultStatus = ref('backlog')

function tasksByCol(col: string) {
  return tasks.value.filter(t => t.status === col)
}

function openCreate(status: string) {
  defaultStatus.value = status
  resetForm(status)
  showCreateModal.value = true
}

function openTask(task: Task) {
  editingTask.value = task
  Object.assign(form, {
    title: task.title,
    description: task.description,
    priority: task.priority,
    status: task.status,
    assignee: task.assignee,
  })
}

function closeModal() {
  showCreateModal.value = false
  editingTask.value = null
}

function resetForm(status?: string) {
  form.title = ''
  form.description = ''
  form.priority = 'medium'
  form.status = status || 'backlog'
  form.assignee = ''
}

function saveTask() {
  if (editingTask.value) {
    Object.assign(editingTask.value, { ...form })
  } else {
    tasks.value.push({
      id: Date.now().toString(),
      ...form,
      createdAt: new Date().toISOString().split('T')[0],
    })
  }
  closeModal()
}

function deleteTask() {
  if (!editingTask.value) return
  const idx = tasks.value.findIndex(t => t.id === editingTask.value!.id)
  if (idx !== -1) tasks.value.splice(idx, 1)
  closeModal()
}

function onDragStart(e: DragEvent, taskId: string) {
  dragTaskId.value = taskId
  e.dataTransfer!.effectAllowed = 'move'
}

function onDrop(e: DragEvent, status: string) {
  const task = tasks.value.find(t => t.id === dragTaskId.value)
  if (task) task.status = status
  dragTaskId.value = null
}

function formatDate(d: string) {
  return d.slice(5)
}
</script>

<style scoped>
.kanban-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-ide-bg);
  color: var(--color-ide-text);
}
.kanban-header {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: var(--color-ide-bg-secondary);
  border-bottom: 1px solid var(--color-ide-border);
}
.page-title { font-size: 15px; font-weight: 600; color: var(--color-ide-text-bright); }
.kanban-board {
  flex: 1;
  display: flex;
  gap: 0;
  overflow-x: auto;
  padding: 12px 8px;
}
.kanban-column {
  flex: 1;
  min-width: 220px;
  max-width: 320px;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--color-ide-border);
}
.kanban-column:last-child { border-right: none; }
.column-header {
  flex-shrink: 0;
  padding: 8px 12px;
  border-top: 3px solid transparent;
}
.column-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.column-dot {
  width: 8px; height: 8px; border-radius: 50%;
}
.column-title {
  font-size: 12px; font-weight: 700;
  text-transform: uppercase; letter-spacing: 0.03em;
  color: var(--color-ide-text-dim);
}
.column-count {
  font-size: 11px; color: var(--color-ide-text-dim);
  background: var(--color-ide-surface-hover);
  padding: 0 6px; border-radius: 8px;
}
.column-body {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.task-card {
  background: var(--color-ide-surface);
  border: 1px solid var(--color-ide-border);
  border-radius: 4px;
  padding: 10px 12px;
  cursor: grab;
  transition: border-color 0.1s;
}
.task-card:hover { border-color: var(--color-ide-accent); }
.task-card:active { cursor: grabbing; }
.task-header {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.priority-dot {
  width: 8px; height: 8px; border-radius: 50%;
  margin-top: 5px; flex-shrink: 0;
}
.p-low { background: #4EC9B0; }
.p-medium { background: #CCA700; }
.p-high { background: #F48771; }
.p-urgent { background: #F44747; }
.task-title {
  font-size: 12.5px; font-weight: 600;
  color: var(--color-ide-text); line-height: 1.4;
}
.task-desc {
  font-size: 11px; color: var(--color-ide-text-dim);
  margin-top: 6px; line-height: 1.4;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.task-meta {
  display: flex; align-items: center; gap: 8px; margin-top: 8px;
}
.task-tag {
  font-size: 10px; padding: 1px 6px;
  background: rgba(55,148,255,0.12); color: var(--color-ide-info);
  border-radius: 3px;
}
.task-date { font-size: 10px; color: var(--color-ide-text-dim); }
.add-task-btn {
  width: 100%; padding: 6px; font-size: 11.5px;
  background: transparent; border: 1px dashed var(--color-ide-border);
  border-radius: 4px; color: var(--color-ide-text-dim); cursor: pointer;
}
.add-task-btn:hover {
  border-color: var(--color-ide-accent); color: var(--color-ide-accent);
}
/* Modal styles */
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.5); display: flex;
  align-items: center; justify-content: center; z-index: 300;
}
.modal-card {
  background: var(--color-ide-surface);
  border: 1px solid var(--color-ide-border);
  border-radius: 6px;
  width: 460px; max-width: 90vw;
  padding: 24px;
  box-shadow: var(--shadow-lg);
}
.modal-title { font-size: 16px; color: var(--color-ide-text); margin-bottom: 20px; }
.modal-body { display: flex; flex-direction: column; gap: 14px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.field.flex-1 { flex: 1; }
.field label { font-size: 12px; color: var(--color-ide-text-dim); }
.field-row { display: flex; gap: 12px; }
.input {
  padding: 8px 12px; font-size: 13px;
  background: var(--color-chat-input-bg); border: 1px solid var(--color-ide-border);
  border-radius: 3px; color: var(--color-ide-text); outline: none;
}
.input:focus { border-color: var(--color-ide-border-focus); }
.textarea { resize: vertical; font-family: inherit; }
.select {
  padding: 7px 8px; font-size: 12px;
  background: var(--color-chat-input-bg); border: 1px solid var(--color-ide-border);
  border-radius: 3px; color: var(--color-ide-text); outline: none;
}
.select:focus { border-color: var(--color-ide-border-focus); }
.modal-actions {
  display: flex; align-items: center; gap: 8px; margin-top: 4px;
}
.flex-1 { flex: 1; }
.btn {
  padding: 6px 16px; font-size: 12px; border-radius: 3px;
  border: none; cursor: pointer; font-weight: 600; transition: background 0.1s;
}
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-primary:hover { background: var(--color-ide-accent-hover); }
.btn-ghost { background: transparent; color: var(--color-ide-text); }
.btn-ghost:hover { background: rgba(255,255,255,0.06); }
.btn-danger { background: transparent; color: var(--color-ide-error); }
.btn-danger:hover { background: rgba(244,135,113,0.1); }
</style>
