<script setup lang="ts">
import { ref, onMounted, computed } from "vue"
import { GitBranch, GitFork, Save, RotateCcw, ChevronRight, Info, Trash2, X } from "lucide-vue-next"
import { getTreeOverview, getNodeDetail, listAllCheckpoints, saveCheckpoint, deleteCheckpoint, restoreFromCheckpoint, forkBranch } from "@/api/sessionTree"
import type { TreeNode, Checkpoint } from "@/api/sessionTree"

const overview = ref<any>(null)
const checkpoints = ref<Checkpoint[]>([])
const loading = ref(false)
const errorMsg = ref("")
const selectedNode = ref<any>(null)
const selectedCheckpoint = ref<any>(null)

/* 保存检查点表单 */
const showSaveDlg = ref(false)
const saveForm = ref({ session_id: "", label: "", description: "" })

/* 恢复确认 */
const showRestoreDlg = ref(false)
const restoreTarget = ref<Checkpoint | null>(null)

async function loadOverview() {
  loading.value = true; errorMsg.value = ""
  try { const [ov, cp] = await Promise.all([getTreeOverview(), listAllCheckpoints()]); overview.value = ov.data; checkpoints.value = cp.data.checkpoints || [] } catch (e: any) { errorMsg.value = e.response?.data?.detail || e.message || "加载失败" } finally { loading.value = false }
}

async function loadNodeDetail(nodeId: string) {
  try { const res = await getNodeDetail(nodeId); selectedNode.value = res.data } catch (e: any) { errorMsg.value = e.response?.data?.detail || e.message || "加载失败" }
}

function openNode(node: TreeNode) { selectedNode.value = null; loadNodeDetail(node.node_id) }

async function handleFork(node: TreeNode) {
  const branchName = prompt("新分支名称：", `${node.branch_name}-fork`)
  if (!branchName) return
  try { await forkBranch({ node_id: node.node_id, branch_name: branchName }); await loadOverview() } catch (e: any) { errorMsg.value = e.response?.data?.detail || e.message || "Fork 失败" }
}

async function handleSaveCheckpoint() {
  try {
    await saveCheckpoint({ session_id: saveForm.value.session_id, label: saveForm.value.label, description: saveForm.value.description })
    showSaveDlg.value = false; await loadOverview()
  } catch (e: any) { errorMsg.value = e.response?.data?.detail || e.message || "保存失败" }
}

async function handleDeleteCheckpoint(id: string) {
  if (!confirm("确定删除此检查点？")) return
  try { await deleteCheckpoint(id); await loadOverview() } catch (e: any) { errorMsg.value = e.response?.data?.detail || e.message || "删除失败" }
}

async function handleRestore(cp: Checkpoint) {
  try { await restoreFromCheckpoint({ checkpoint_id: cp.checkpoint_id }); showRestoreDlg.value = false; await loadOverview() } catch (e: any) { errorMsg.value = e.response?.data?.detail || e.message || "恢复失败" }
}

function formatTime(t: string) { return new Date(t).toLocaleString() }

onMounted(loadOverview)
</script>

<template>
  <div class="g-container">
    <div class="g-header">
      <div class="g-header-left"><GitBranch :size="22" class="g-header-icon" /><h1 class="g-header-title">会话树</h1><span class="g-header-sub">分支/检查点管理</span></div>
      <button class="g-btn g-btn-primary" @click="showSaveDlg = true"><Save :size="15" />保存检查点</button>
    </div>

    <div v-if="errorMsg" class="g-error-msg">{{ errorMsg }}<button class="g-error-close" @click="errorMsg = ''"><X :size="14" /></button></div>
    <div v-if="loading" class="g-loading">加载中...</div>

    <div v-else class="g-layout">
      <!-- 左侧：树总览 -->
      <div class="g-panel g-tree-panel">
        <h3 class="g-panel-title">会话树</h3>
        <div v-if="overview" class="g-summary">
          <span class="g-summary-item">节点: {{ overview.summary?.total_nodes }}</span>
          <span class="g-summary-item">分支: {{ overview.summary?.total_branches }}</span>
          <span class="g-summary-item">会话: {{ overview.summary?.total_sessions }}</span>
        </div>
        <div class="g-tree-list">
          <div v-for="node in overview?.roots" :key="node.node_id" class="g-tree-node" @click="openNode(node)">
            <ChevronRight :size="14" class="g-node-arrow" />
            <div class="g-node-info">
              <span class="g-node-branch">{{ node.branch_name || "main" }}</span>
              <span class="g-node-meta">{{ node.total_turns }} 轮 · {{ formatTime(node.created_at) }}</span>
            </div>
            <div class="g-node-actions" @click.stop>
              <button class="g-icon-btn" title="Fork 分支" @click="handleFork(node)"><GitFork :size="13" /></button>
            </div>
          </div>
          <div v-if="!overview?.roots?.length" class="g-empty-page">暂无会话树数据</div>
        </div>
      </div>

      <!-- 中间：节点详情 -->
      <div class="g-panel g-detail-panel">
        <h3 class="g-panel-title">节点详情</h3>
        <div v-if="selectedNode" class="g-detail-content">
          <div class="g-detail-header">
            <span class="g-detail-id">{{ selectedNode.node?.node_id?.slice(0, 12) }}...</span>
            <span class="g-detail-branch">{{ selectedNode.node?.branch_name }}</span>
          </div>
          <div class="g-detail-grid">
            <div class="g-detail-item"><span class="g-dl">轮数</span><span>{{ selectedNode.node?.total_turns }}</span></div>
            <div class="g-detail-item"><span class="g-dl">Token</span><span>{{ selectedNode.node?.total_tokens }}</span></div>
            <div class="g-detail-item"><span class="g-dl">创建</span><span>{{ formatTime(selectedNode.node?.created_at) }}</span></div>
          </div>
          <!-- 子节点列表 -->
          <div v-if="selectedNode.children?.length" class="g-sub-section">
            <h4 class="g-sub-title">子节点 ({{ selectedNode.children.length }})</h4>
            <div v-for="ch in selectedNode.children" :key="ch.node_id" class="g-sub-node" @click="openNode(ch)">
              <ChevronRight :size="12" /><span class="g-sub-branch">{{ ch.branch_name }}</span><span class="g-sub-meta">{{ ch.total_turns }} 轮</span>
            </div>
          </div>
          <!-- 检查点 -->
          <div v-if="selectedNode.checkpoints?.length" class="g-sub-section">
            <h4 class="g-sub-title">检查点 ({{ selectedNode.checkpoints.length }})</h4>
            <div v-for="cp in selectedNode.checkpoints" :key="cp.checkpoint_id" class="g-checkpoint-row">
              <span class="g-cp-label">{{ cp.label || cp.checkpoint_id?.slice(0, 8) }}</span>
              <span class="g-cp-meta">{{ cp.turn }} 轮</span>
              <div class="g-cp-actions">
                <button class="g-icon-btn" title="恢复" @click="restoreTarget = cp; showRestoreDlg = true"><RotateCcw :size="12" /></button>
                <button class="g-icon-btn g-icon-danger" title="删除" @click="handleDeleteCheckpoint(cp.checkpoint_id)"><Trash2 :size="12" /></button>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="g-empty-panel">选择左侧节点查看详情</div>
      </div>

      <!-- 右侧：检查点列表 -->
      <div class="g-panel g-cp-panel">
        <h3 class="g-panel-title">所有检查点 ({{ checkpoints.length }})</h3>
        <div class="g-cp-list">
          <div v-for="cp in checkpoints" :key="cp.checkpoint_id" class="g-checkpoint-row" @click="selectedCheckpoint = cp">
            <Info :size="12" class="g-cp-icon" />
            <div class="g-cp-content">
              <span class="g-cp-label">{{ cp.label || "未命名" }}</span>
              <span class="g-cp-meta">{{ formatTime(cp.created_at) }}</span>
            </div>
            <div class="g-cp-actions">
              <button class="g-icon-btn" title="恢复" @click.stop="restoreTarget = cp; showRestoreDlg = true"><RotateCcw :size="12" /></button>
              <button class="g-icon-btn g-icon-danger" title="删除" @click.stop="handleDeleteCheckpoint(cp.checkpoint_id)"><Trash2 :size="12" /></button>
            </div>
          </div>
          <div v-if="!checkpoints.length" class="g-empty-panel">暂无检查点</div>
        </div>
      </div>
    </div>

    <!-- 保存检查点弹窗 -->
    <Teleport to="body">
      <div v-if="showSaveDlg" class="g-overlay" @click.self="showSaveDlg = false">
        <div class="g-modal">
          <div class="g-modal-header"><h3>保存检查点</h3><button class="g-modal-close" @click="showSaveDlg = false"><X :size="18" /></button></div>
          <div class="g-modal-body">
            <label class="g-form-field"><span>会话 ID</span><input v-model="saveForm.session_id" class="g-input" placeholder="session_id" /></label>
            <label class="g-form-field"><span>标签</span><input v-model="saveForm.label" class="g-input" placeholder="检查点标签" /></label>
            <label class="g-form-field"><span>描述</span><textarea v-model="saveForm.description" class="g-input g-textarea" rows="2" placeholder="可选描述" /></label>
          </div>
          <div class="g-modal-footer">
            <button class="g-btn g-btn-ghost" @click="showSaveDlg = false">取消</button>
            <button class="g-btn g-btn-primary" @click="handleSaveCheckpoint">保存</button>
          </div>
        </div>
      </div>

      <!-- 恢复确认 -->
      <div v-if="showRestoreDlg" class="g-overlay" @click.self="showRestoreDlg = false">
        <div class="g-modal g-modal-sm">
          <div class="g-modal-header"><h3>恢复确认</h3><button class="g-modal-close" @click="showRestoreDlg = false"><X :size="18" /></button></div>
          <div class="g-modal-body">
            <p>确定从检查点 "{{ restoreTarget?.label || restoreTarget?.checkpoint_id?.slice(0, 8) }}" 恢复？</p>
            <p class="g-hint">将恢复该检查点的会话状态</p>
          </div>
          <div class="g-modal-footer">
            <button class="g-btn g-btn-ghost" @click="showRestoreDlg = false">取消</button>
            <button class="g-btn g-btn-primary" @click="handleRestore(restoreTarget!)">确认恢复</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.g-container { padding: 24px; max-width: 1400px; margin: 0 auto; }
.g-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }
.g-header-left { display: flex; align-items: center; gap: 10px; }
.g-header-icon { color: var(--color-ide-accent, #a855f7); }
.g-header-title { font-size: 20px; font-weight: 600; color: var(--color-ide-fg, #e2e8f0); margin: 0; }
.g-header-sub { font-size: 13px; color: var(--color-ide-fg-secondary, #94a3b8); }
.g-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; border: none; border-radius: 7px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all 0.15s; }
.g-btn-primary { background: var(--color-ide-accent, #a855f7); color: #fff; }
.g-btn-ghost { background: transparent; color: var(--color-ide-fg-secondary, #94a3b8); border: 1px solid var(--color-ide-border, #334155); }
.g-error-msg { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; margin-bottom: 16px; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 7px; color: #ef4444; font-size: 13px; }
.g-error-close { background: none; border: none; color: #ef4444; cursor: pointer; }
.g-loading { color: var(--color-ide-fg-secondary, #94a3b8); font-size: 13px; padding: 40px 0; }

.g-layout { display: grid; grid-template-columns: 300px 1fr 260px; gap: 16px; }
@media (max-width: 1000px) { .g-layout { grid-template-columns: 1fr; } }
.g-panel { background: var(--color-ide-bg-secondary, #1e293b); border: 1px solid var(--color-ide-border, #334155); border-radius: 10px; padding: 14px; max-height: 600px; overflow-y: auto; }
.g-panel-title { font-size: 13px; font-weight: 600; color: var(--color-ide-fg, #e2e8f0); margin: 0 0 12px 0; }
.g-summary { display: flex; gap: 12px; margin-bottom: 12px; }
.g-summary-item { font-size: 12px; color: var(--color-ide-fg-secondary, #94a3b8); padding: 3px 8px; background: var(--color-ide-bg-primary, #0f172a); border-radius: 4px; }

.g-tree-node { display: flex; align-items: center; gap: 8px; padding: 8px 10px; border-radius: 6px; cursor: pointer; transition: background 0.1s; margin-bottom: 2px; }
.g-tree-node:hover { background: var(--color-ide-bg-primary, #0f172a); }
.g-node-arrow { color: var(--color-ide-fg-secondary, #94a3b8); flex-shrink: 0; }
.g-node-info { flex: 1; min-width: 0; }
.g-node-branch { display: block; font-size: 13px; color: var(--color-ide-fg, #e2e8f0); font-family: monospace; }
.g-node-meta { font-size: 11px; color: var(--color-ide-fg-secondary, #94a3b8); }
.g-node-actions { display: flex; gap: 4px; }
.g-icon-btn { display: inline-flex; align-items: center; justify-content: center; padding: 4px; border: 1px solid var(--color-ide-border, #334155); border-radius: 4px; background: var(--color-ide-bg-primary, #0f172a); color: var(--color-ide-fg-secondary, #94a3b8); cursor: pointer; transition: all 0.1s; }
.g-icon-btn:hover { color: var(--color-ide-fg, #e2e8f0); }
.g-icon-danger:hover { color: #ef4444; border-color: #ef4444; }

.g-detail-header { margin-bottom: 12px; }
.g-detail-id { font-size: 11px; color: var(--color-ide-fg-secondary, #94a3b8); font-family: monospace; }
.g-detail-branch { display: inline-block; margin-left: 8px; padding: 2px 8px; background: var(--color-ide-bg-primary, #0f172a); border-radius: 4px; font-size: 12px; font-family: monospace; color: var(--color-ide-fg, #e2e8f0); }
.g-detail-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; }
.g-detail-item { font-size: 12px; color: var(--color-ide-fg, #e2e8f0); }
.g-dl { color: var(--color-ide-fg-secondary, #94a3b8); margin-right: 6px; font-size: 11px; }
.g-sub-section { margin-top: 14px; }
.g-sub-title { font-size: 12px; font-weight: 600; color: var(--color-ide-fg-secondary, #94a3b8); margin: 0 0 8px 0; }
.g-sub-node { display: flex; align-items: center; gap: 6px; padding: 5px 8px; border-radius: 4px; cursor: pointer; font-size: 12px; }
.g-sub-node:hover { background: var(--color-ide-bg-primary, #0f172a); }
.g-sub-branch { color: var(--color-ide-fg, #e2e8f0); font-family: monospace; }
.g-sub-meta { color: var(--color-ide-fg-secondary, #94a3b8); margin-left: auto; font-size: 11px; }

.g-checkpoint-row { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px; cursor: pointer; transition: background 0.1s; }
.g-checkpoint-row:hover { background: var(--color-ide-bg-primary, #0f172a); }
.g-cp-icon { color: var(--color-ide-accent, #a855f7); flex-shrink: 0; }
.g-cp-content { flex: 1; min-width: 0; }
.g-cp-label { display: block; font-size: 12px; color: var(--color-ide-fg, #e2e8f0); }
.g-cp-meta { font-size: 10px; color: var(--color-ide-fg-secondary, #94a3b8); }
.g-cp-actions { display: flex; gap: 3px; }
.g-empty-panel { text-align: center; padding: 40px 0; color: var(--color-ide-fg-secondary, #94a3b8); font-size: 13px; }
.g-empty-page { text-align: center; padding: 40px 0; color: var(--color-ide-fg-secondary, #94a3b8); font-size: 13px; }

/* 弹窗 */
.g-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.g-modal { background: var(--color-ide-bg-secondary, #1e293b); border: 1px solid var(--color-ide-border, #334155); border-radius: 12px; width: 500px; max-width: 90vw; }
.g-modal-sm { width: 400px; }
.g-modal-header { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid var(--color-ide-border, #334155); }
.g-modal-header h3 { margin: 0; font-size: 16px; color: var(--color-ide-fg, #e2e8f0); }
.g-modal-close { background: none; border: none; color: var(--color-ide-fg-secondary, #94a3b8); cursor: pointer; }
.g-modal-body { padding: 20px; display: flex; flex-direction: column; gap: 12px; }
.g-modal-body p { margin: 0; font-size: 13px; color: var(--color-ide-fg, #e2e8f0); }
.g-hint { font-size: 12px; color: var(--color-ide-fg-secondary, #94a3b8); }
.g-modal-footer { display: flex; justify-content: flex-end; gap: 8px; padding: 14px 20px; border-top: 1px solid var(--color-ide-border, #334155); }
.g-form-field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--color-ide-fg-secondary, #94a3b8); }
.g-input { padding: 8px 10px; border: 1px solid var(--color-ide-border, #334155); border-radius: 6px; background: var(--color-ide-bg-primary, #0f172a); color: var(--color-ide-fg, #e2e8f0); font-size: 13px; outline: none; box-sizing: border-box; width: 100%; }
.g-input:focus { border-color: var(--color-ide-accent, #a855f7); }
.g-textarea { resize: vertical; min-height: 50px; font-family: inherit; }
</style>
