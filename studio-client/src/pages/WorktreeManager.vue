<script setup lang="ts">
/**
 * Git Worktree 并行工作树管理
 * 创建/删除/检出/合并/任务管理
 */
import { ref, onMounted } from "vue"
import {
  GitBranch, GitMerge, FolderTree, Plus, Trash2, RefreshCw,
  ArrowRightLeft, FileDiff, ClipboardList, CheckCircle, XCircle,
  PlayCircle, AlertTriangle, Home,
} from "lucide-vue-next"
import {
  listWorktrees, getBranches, createWorktree, deleteWorktree, cleanupWorktrees,
  checkoutBranch, mergeBranch, getWorktreeDiff,
  listTasks, registerTask, completeTask,
  type WorktreeItem, type WorktreeStats, type BranchItem, type WorktreeTask,
} from "@/api/worktree"

// ── 状态 ──
const stats = ref<WorktreeStats | null>(null)
const branches = ref<BranchItem[]>([])
const tasks = ref<WorktreeTask[]>([])
const loading = ref(false)
const activeTab = ref<"worktrees" | "tasks">("worktrees")
const toastMsg = ref("")

// 新建 Worktree 表单
const showCreate = ref(false)
const createForm = ref({ branch: "", base_branch: "", description: "", create_new: true })

// 分支操作
const showCheckout = ref(false)
const showMerge = ref(false)
const branchOp = ref({ worktree_path: "", branch: "", source_branch: "", message: "" })

// 任务操作
const showTaskCreate = ref(false)
const taskForm = ref({ worktree_path: "", branch: "", description: "" })

// Diff
const showDiff = ref(false)
const diffContent = ref("")
const diffPath = ref("")

// ── 数据加载 ──
async function loadAll() {
  loading.value = true
  try {
    const [s, b, t] = await Promise.all([
      listWorktrees(),
      getBranches(true).catch(() => ({ branches: [] as BranchItem[] })),
      listTasks().catch(() => ({ tasks: [] as WorktreeTask[], total: 0 })),
    ])
    stats.value = s
    branches.value = b.branches ?? []
    tasks.value = t.tasks ?? []
  } catch (e) {
    console.error("加载 worktree 失败:", e)
  } finally {
    loading.value = false
  }
}

// ── Worktree 操作 ──
async function doCreate() {
  if (!createForm.value.branch.trim()) return
  try {
    const res = await createWorktree({
      branch: createForm.value.branch.trim(),
      base_branch: createForm.value.base_branch.trim() || undefined,
      create_new_branch: createForm.value.create_new,
      description: createForm.value.description.trim() || undefined,
    })
    toastMsg.value = res.message
    showCreate.value = false
    createForm.value = { branch: "", base_branch: "", description: "", create_new: true }
    loadAll()
  } catch (e: any) { toastMsg.value = e?.response?.data?.detail ?? "创建失败" }
}

async function doDelete(path: string) {
  if (!confirm(`确认删除 worktree "${path}"？`)) return
  try {
    const res = await deleteWorktree(path)
    toastMsg.value = res.message
    loadAll()
  } catch (e: any) { toastMsg.value = e?.response?.data?.detail ?? "删除失败" }
}

async function doCleanup() {
  if (!confirm("确认清理孤立的 worktree？")) return
  try {
    const res = await cleanupWorktrees()
    toastMsg.value = res.message
    loadAll()
  } catch (e: any) { toastMsg.value = e?.response?.data?.detail ?? "清理失败" }
}

async function doCheckout() {
  try {
    const res = await checkoutBranch(branchOp.value.branch, branchOp.value.worktree_path)
    toastMsg.value = res.message
    showCheckout.value = false
    loadAll()
  } catch (e: any) { toastMsg.value = e?.response?.data?.detail ?? "检出失败" }
}

async function doMerge() {
  try {
    const res = await mergeBranch(branchOp.value.source_branch, branchOp.value.worktree_path, branchOp.value.message)
    toastMsg.value = res.message + (res.conflict ? " (有冲突!)" : "")
    showMerge.value = false
    loadAll()
  } catch (e: any) { toastMsg.value = e?.response?.data?.detail ?? "合并失败" }
}

async function doDiff(path: string) {
  try {
    const res = await getWorktreeDiff(path)
    diffContent.value = res.diff
    diffPath.value = res.path
    showDiff.value = true
  } catch (e: any) { toastMsg.value = e?.response?.data?.detail ?? "获取 diff 失败" }
}

// ── 任务操作 ──
async function doRegisterTask() {
  try {
    await registerTask({
      worktree_path: taskForm.value.worktree_path.trim(),
      branch: taskForm.value.branch.trim() || undefined,
      description: taskForm.value.description.trim() || undefined,
    })
    toastMsg.value = "任务已注册"
    showTaskCreate.value = false
    taskForm.value = { worktree_path: "", branch: "", description: "" }
    loadAll()
  } catch (e: any) { toastMsg.value = e?.response?.data?.detail ?? "注册失败" }
}

async function doCompleteTask(taskId: string, success: boolean) {
  try {
    await completeTask(taskId, { success })
    toastMsg.value = `任务 ${success ? "已完成" : "标记失败"}`
    loadAll()
  } catch (e: any) { toastMsg.value = e?.response?.data?.detail ?? "操作失败" }
}

// ── 格式化 ──
const statusLabel = (s: string) => ({ pending: "待处理", running: "运行中", completed: "已完成", failed: "失败" }[s] ?? s)

onMounted(loadAll)
</script>

<template>
  <div class="worktree-page">
    <!-- Toast -->
    <transition name="fade">
      <div v-if="toastMsg" class="toast" @click="toastMsg = ''">{{ toastMsg }}</div>
    </transition>

    <!-- 页头 -->
    <header class="page-header">
      <div class="header-left">
        <h1 class="page-title">Git Worktree</h1>
        <span class="page-subtitle">并行开发工作环境，隔离分支操作</span>
      </div>
      <div class="header-actions">
        <button class="btn btn-ghost" @click="doCleanup" title="清理孤立 branch">
          <AlertTriangle :size="14" /> 清理
        </button>
        <button class="btn btn-primary" @click="showCreate = true">
          <Plus :size="14" /> 新建 Worktree
        </button>
        <button class="btn btn-ghost" @click="loadAll" title="刷新">
          <RefreshCw :size="14" />
        </button>
      </div>
    </header>

    <!-- 统计 -->
    <section class="info-bar">
      <span v-if="stats?.is_git_repo === false" class="warn">⚠ 当前目录不是 Git 仓库</span>
      <template v-else>
        <span class="info-item"><GitBranch :size="14" /> Worktree: {{ stats?.total ?? 0 }}</span>
        <span class="info-item"><ClipboardList :size="14" /> 任务: {{ tasks.length }}</span>
        <span class="info-item"><Home :size="14" /> {{ stats?.worktrees?.[0]?.branch || "—" }}</span>
      </template>
    </section>

    <!-- Tab -->
    <nav class="tab-nav">
      <button :class="['tab-btn', { active: activeTab === 'worktrees' }]" @click="activeTab = 'worktrees'">
        <FolderTree :size="14" /> Worktree ({{ stats?.total ?? 0 }})
      </button>
      <button :class="['tab-btn', { active: activeTab === 'tasks' }]" @click="activeTab = 'tasks'">
        <ClipboardList :size="14" /> 任务 ({{ tasks.length }})
      </button>
    </nav>

    <!-- Worktree 列表 -->
    <section v-if="activeTab === 'worktrees'">
      <div v-if="loading" class="empty">加载中...</div>
      <div v-else-if="!stats?.worktrees?.length" class="empty">暂无 Worktree</div>
      <div v-for="wt in stats?.worktrees ?? []" v-else :key="wt.path" class="wt-card">
        <div class="wt-main">
          <div class="wt-branch">
            <GitBranch :size="14" />
            <span class="wt-branch-name">{{ wt.branch }}</span>
            <span v-if="wt.locked" class="badge badge-warn">Locked</span>
            <span v-if="wt.prunable" class="badge badge-warn">Prunable</span>
          </div>
          <div class="wt-path">{{ wt.path }}</div>
          <div class="wt-head">{{ wt.head?.slice(0, 8) || "—" }}</div>
        </div>
        <div class="wt-actions">
          <button class="btn-icon" title="检出分支" @click="branchOp.worktree_path = wt.path; showCheckout = true">
            <ArrowRightLeft :size="14" />
          </button>
          <button class="btn-icon" title="合并分支" @click="branchOp.worktree_path = wt.path; showMerge = true">
            <GitMerge :size="14" />
          </button>
          <button class="btn-icon" title="查看 Diff" @click="doDiff(wt.path)">
            <FileDiff :size="14" />
          </button>
          <button class="btn-icon" title="注册任务" @click="taskForm.worktree_path = wt.path; showTaskCreate = true">
            <ClipboardList :size="14" />
          </button>
          <button class="btn-icon danger" title="删除" @click="doDelete(wt.path)">
            <Trash2 :size="14" />
          </button>
        </div>
      </div>
    </section>

    <!-- 任务列表 -->
    <section v-if="activeTab === 'tasks'">
      <div v-if="!tasks.length" class="empty">暂无任务</div>
      <div v-for="t in tasks" v-else :key="t.task_id" class="task-row">
        <div class="task-left">
          <span :class="['badge', `badge-${t.status}`]">{{ statusLabel(t.status) }}</span>
          <code class="task-id">{{ t.task_id }}</code>
          <span class="task-desc">{{ t.description || "—" }}</span>
        </div>
        <div class="task-right">
          <span class="task-path">{{ t.worktree_path }}</span>
          <button
            v-if="t.status === 'pending' || t.status === 'running'"
            class="btn-icon" title="完成" @click="doCompleteTask(t.task_id, true)"
          >
            <CheckCircle :size="14" class="text-green" />
          </button>
          <button
            v-if="t.status === 'pending' || t.status === 'running'"
            class="btn-icon danger" title="失败" @click="doCompleteTask(t.task_id, false)"
          >
            <XCircle :size="14" />
          </button>
        </div>
      </div>
    </section>

    <!-- ── 模态: 新建 Worktree ── -->
    <div v-if="showCreate" class="modal-overlay" @click.self="showCreate = false">
      <div class="modal">
        <h3 class="modal-title"><Plus :size="16" /> 新建 Worktree</h3>
        <div class="form-field">
          <label>分支名称</label><input v-model="createForm.branch" placeholder="feature/xxx" class="input" />
        </div>
        <div class="form-field">
          <label>基础分支</label><input v-model="createForm.base_branch" placeholder="main" class="input" />
        </div>
        <div class="form-field">
          <label>描述</label><input v-model="createForm.description" placeholder="任务描述..." class="input" />
        </div>
        <label class="checkbox-label">
          <input type="checkbox" v-model="createForm.create_new" /> 创建新分支
        </label>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showCreate = false">取消</button>
          <button class="btn btn-primary" @click="doCreate">创建</button>
        </div>
      </div>
    </div>

    <!-- ── 模态: Checkout ── -->
    <div v-if="showCheckout" class="modal-overlay" @click.self="showCheckout = false">
      <div class="modal">
        <h3 class="modal-title"><ArrowRightLeft :size="16" /> 检出分支</h3>
        <div class="form-field">
          <label>路径</label><input :value="branchOp.worktree_path" disabled class="input" />
        </div>
        <div class="form-field">
          <label>目标分支</label>
          <select v-model="branchOp.branch" class="input">
            <option value="">-- 选择分支 --</option>
            <option v-for="b in branches" :key="b.name" :value="b.name">{{ b.name }}{{ b.current ? ' (当前)' : '' }}</option>
          </select>
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showCheckout = false">取消</button>
          <button class="btn btn-primary" @click="doCheckout">检出</button>
        </div>
      </div>
    </div>

    <!-- ── 模态: Merge ── -->
    <div v-if="showMerge" class="modal-overlay" @click.self="showMerge = false">
      <div class="modal">
        <h3 class="modal-title"><GitMerge :size="16" /> 合并分支</h3>
        <div class="form-field">
          <label>路径</label><input :value="branchOp.worktree_path" disabled class="input" />
        </div>
        <div class="form-field">
          <label>源分支</label>
          <select v-model="branchOp.source_branch" class="input">
            <option value="">-- 选择分支 --</option>
            <option v-for="b in branches" :key="b.name" :value="b.name">{{ b.name }}</option>
          </select>
        </div>
        <div class="form-field">
          <label>Commit Message</label><input v-model="branchOp.message" placeholder="Merge..." class="input" />
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showMerge = false">取消</button>
          <button class="btn btn-primary" @click="doMerge">合并</button>
        </div>
      </div>
    </div>

    <!-- ── 模态: Diff ── -->
    <div v-if="showDiff" class="modal-overlay" @click.self="showDiff = false">
      <div class="modal modal-lg">
        <h3 class="modal-title"><FileDiff :size="16" /> Diff: {{ diffPath }}</h3>
        <pre class="diff-pre">{{ diffContent || "(无变更)" }}</pre>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showDiff = false">关闭</button>
        </div>
      </div>
    </div>

    <!-- ── 模态: 新建任务 ── -->
    <div v-if="showTaskCreate" class="modal-overlay" @click.self="showTaskCreate = false">
      <div class="modal">
        <h3 class="modal-title"><ClipboardList :size="16" /> 注册任务</h3>
        <div class="form-field">
          <label>Worktree 路径</label><input v-model="taskForm.worktree_path" placeholder="/path/to/worktree" class="input" />
        </div>
        <div class="form-field">
          <label>分支</label><input v-model="taskForm.branch" placeholder="feature/xxx" class="input" />
        </div>
        <div class="form-field">
          <label>描述</label><input v-model="taskForm.description" placeholder="任务描述..." class="input" />
        </div>
        <div class="modal-actions">
          <button class="btn btn-ghost" @click="showTaskCreate = false">取消</button>
          <button class="btn btn-primary" @click="doRegisterTask">注册</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ── 页面 ── */
.worktree-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
  height: 100%;
  overflow: auto;
  background: var(--color-ide-bg, #0d1117);
  color: var(--color-ide-fg, #c9d1d9);
}

/* ── Toast ── */
.toast {
  position: fixed;
  top: 16px; right: 24px;
  padding: 10px 18px;
  background: var(--color-ide-panel-bg, #161b22);
  border: 1px solid var(--color-ide-accent, #58a6ff);
  border-radius: 8px;
  font-size: 13px;
  z-index: 1000;
  cursor: pointer;
}
.fade-enter-active, .fade-leave-active { transition: opacity .2s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* ── 页头 ── */
.page-header { display: flex; justify-content: space-between; align-items: flex-start; }
.header-left { display: flex; flex-direction: column; gap: 2px; }
.page-title { font-size: 20px; font-weight: 700; margin: 0; }
.page-subtitle { font-size: 13px; color: var(--color-ide-fg-muted, #8b949e); }
.header-actions { display: flex; gap: 8px; }

/* ── 信息栏 ── */
.info-bar { display: flex; gap: 16px; align-items: center; padding: 10px 14px; background: var(--color-ide-panel-bg, #161b22); border: 1px solid var(--color-ide-border, #30363d); border-radius: 8px; font-size: 13px; }
.info-item { display: flex; align-items: center; gap: 4px; }
.warn { color: #d29922; }

/* ── Tab ── */
.tab-nav { display: flex; gap: 4px; border-bottom: 1px solid var(--color-ide-border, #30363d); }
.tab-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; border: none; background: transparent; color: var(--color-ide-fg-muted, #8b949e); font-size: 13px; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px; }
.tab-btn:hover { color: var(--color-ide-fg, #c9d1d9); }
.tab-btn.active { color: var(--color-ide-accent, #58a6ff); border-bottom-color: var(--color-ide-accent, #58a6ff); }

/* ── Worktree 卡片 ── */
.wt-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--color-ide-panel-bg, #161b22);
  border: 1px solid var(--color-ide-border, #30363d);
  border-radius: 8px;
  margin-bottom: 8px;
}
.wt-main { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.wt-branch { display: flex; align-items: center; gap: 6px; font-weight: 600; }
.wt-branch-name { font-family: monospace; }
.wt-path { font-size: 12px; color: var(--color-ide-fg-muted, #8b949e); font-family: monospace; }
.wt-head { font-size: 11px; color: var(--color-ide-fg-muted, #8b949e); font-family: monospace; }
.wt-actions { display: flex; gap: 4px; flex-shrink: 0; }

/* ── 任务行 ── */
.task-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  background: var(--color-ide-panel-bg, #161b22);
  border: 1px solid var(--color-ide-border, #30363d);
  border-radius: 8px;
  margin-bottom: 6px;
  font-size: 13px;
}
.task-left { display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0; }
.task-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.task-id { font-size: 11px; color: var(--color-ide-fg-muted, #8b949e); }
.task-desc { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.task-path { font-size: 11px; color: var(--color-ide-fg-muted, #8b949e); font-family: monospace; }

/* ── 模态 ── */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 500;
}
.modal {
  background: var(--color-ide-panel-bg, #161b22);
  border: 1px solid var(--color-ide-border, #30363d);
  border-radius: 12px;
  padding: 24px;
  min-width: 420px;
  max-width: 90vw;
}
.modal-lg { min-width: 600px; max-height: 80vh; overflow: auto; }
.modal-title { font-size: 16px; font-weight: 600; margin: 0 0 16px 0; display: flex; align-items: center; gap: 8px; }
.form-field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 12px; }
.form-field label { font-size: 13px; font-weight: 500; color: var(--color-ide-fg-muted, #8b949e); }
.input {
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--color-ide-border, #30363d);
  background: var(--color-ide-input-bg, #0d1117);
  color: var(--color-ide-fg, #c9d1d9);
  font-size: 13px;
  outline: none;
}
.checkbox-label { display: flex; align-items: center; gap: 6px; font-size: 13px; margin-bottom: 12px; cursor: pointer; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.diff-pre {
  background: var(--color-ide-input-bg, #0d1117);
  border-radius: 6px;
  padding: 14px;
  font-family: monospace;
  font-size: 12px;
  white-space: pre-wrap;
  max-height: 50vh;
  overflow: auto;
}

/* ── 按钮 / 徽章 ── */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: 6px;
  border: 1px solid transparent;
  font-size: 13px;
  cursor: pointer;
  background: transparent;
  color: var(--color-ide-fg, #c9d1d9);
}
.btn-primary { background: var(--color-ide-accent, #238636); border-color: var(--color-ide-accent, #238636); color: #fff; }
.btn-ghost { border-color: var(--color-ide-border, #30363d); }
.btn-ghost:hover { background: var(--color-ide-hover, #21262d); }
.btn-icon { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 4px; border: none; background: transparent; color: var(--color-ide-fg-muted, #8b949e); cursor: pointer; }
.btn-icon:hover { background: var(--color-ide-hover, #21262d); color: var(--color-ide-fg, #c9d1d9); }
.btn-icon.danger:hover { color: #f85149; }

.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.badge-pending { background: #d2992220; color: #d29922; }
.badge-running { background: #58a6ff20; color: #58a6ff; }
.badge-completed { background: #3fb95020; color: #3fb950; }
.badge-failed { background: #f8514920; color: #f85149; }
.badge-warn { background: #d2992220; color: #d29922; margin-left: 4px; }
.text-green { color: #3fb950; }

.empty { text-align: center; padding: 60px 20px; color: var(--color-ide-fg-muted, #8b949e); font-size: 14px; }
</style>
