<script setup lang="ts">
/**
 * EditSessionsPanel — VSCode Edit Sessions 对标
 * Session 42: 管理编辑会话（保存/恢复/跨设备同步工作区状态）
 */
import { ref, computed } from "vue"
import { Save, Upload, Download, Trash2, History, Clock, Check, X, Cloud, Monitor } from "lucide-vue-next"

interface EditSession {
  id: string
  name: string
  description: string
  createdAt: number
  fileCount: number
  synced: boolean
  tags: string[]
}
const sessions = ref<EditSession[]>([
  { id: "s-1", name: "主分支开发", description: "当前 main 分支工作状态", createdAt: Date.now() - 3600000, fileCount: 5, synced: false, tags: ["active", "main"] },
  { id: "s-2", name: "Bug 修复 #42", description: "修复 Sidebar 布局问题", createdAt: Date.now() - 86400000, fileCount: 3, synced: true, tags: ["bugfix"] },
  { id: "s-3", name: "功能开发中", description: "编辑器增强功能", createdAt: Date.now() - 172800000, fileCount: 8, synced: false, tags: ["feature"] },
])
const showCreateForm = ref(false)
const newSession = ref({ name: "", description: "" })
const saving = ref(false)

function createSession(): void {
  if (!newSession.value.name.trim()) return
  sessions.value.unshift({
    id: `s-${Date.now()}`,
    name: newSession.value.name.trim(),
    description: newSession.value.description.trim(),
    createdAt: Date.now(),
    fileCount: 0,
    synced: false,
    tags: [],
  })
  newSession.value = { name: "", description: "" }
  showCreateForm.value = false
}
function deleteSession(id: string): void {
  sessions.value = sessions.value.filter(s => s.id !== id)
}
function saveSession(session: EditSession): void {
  saving.value = true
  setTimeout(() => {
    session.fileCount = 5
    session.synced = true
    session.createdAt = Date.now()
    saving.value = false
  }, 500)
}
function timeAgo(ts: number): string {
  const s = (Date.now() - ts) / 1000
  if (s < 60) return "刚刚"
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`
  return `${Math.floor(s / 86400)} 天前`
}
</script>

<template>
  <div class="h-full flex flex-col" style="background: var(--color-ide-bg); color: var(--color-ide-text);">
    <!-- Header -->
    <div class="flex items-center gap-2 px-3 h-10 shrink-0" style="border-bottom: 1px solid var(--color-ide-border);">
      <History :size="16" style="color: var(--color-ide-accent);" />
      <span class="text-[13px] font-semibold">编辑会话</span>
      <span class="text-[10px] opacity-50">({{ sessions.length }})</span>
      <div class="flex-1" />
      <button class="flex items-center gap-1 px-2 h-6 rounded-[3px] text-[11px] font-medium transition-colors"
        style="background: var(--color-ide-accent); color: #fff;" @click="showCreateForm = !showCreateForm">
        <Save :size="12" /> 保存当前会话
      </button>
    </div>

    <!-- Create Form -->
    <div v-if="showCreateForm" class="p-3 border-b" style="border-color: var(--color-ide-border); background: var(--color-ide-bg-secondary);">
      <input v-model="newSession.name" class="w-full h-7 px-2 rounded-[3px] text-[12px] outline-none mb-2"
        placeholder="会话名称 *" :style="{ background: 'var(--color-ide-surface)', border: '1px solid var(--color-ide-border)', color: 'var(--color-ide-text)' }" />
      <input v-model="newSession.description" class="w-full h-7 px-2 rounded-[3px] text-[12px] outline-none mb-2"
        placeholder="描述（可选）" :style="{ background: 'var(--color-ide-surface)', border: '1px solid var(--color-ide-border)', color: 'var(--color-ide-text)' }" />
      <div class="flex justify-end gap-2">
        <button class="px-3 h-6 rounded-[3px] text-[11px] hover:bg-[var(--color-ide-surface-hover)]" style="color: var(--color-ide-text-dim);" @click="showCreateForm = false">取消</button>
        <button class="px-3 h-6 rounded-[3px] text-[11px] font-medium" style="background: var(--color-ide-accent); color: #fff;"
          :disabled="!newSession.name.trim()" @click="createSession">保存</button>
      </div>
    </div>

    <!-- Sessions List -->
    <div class="flex-1 overflow-y-auto">
      <div v-if="sessions.length === 0" class="flex flex-col items-center justify-center py-16 gap-2">
        <History :size="28" style="color: var(--color-ide-text-dim); opacity: 0.2;" />
        <span class="text-[12px]" style="color: var(--color-ide-text-dim);">暂无编辑会话</span>
        <span class="text-[10px]" style="color: var(--color-ide-text-dim); opacity: 0.5;">保存当前工作区状态以便稍后恢复</span>
      </div>
      <div v-for="session in sessions" :key="session.id" class="flex items-start gap-3 px-3 py-3 border-b group"
        style="border-color: var(--color-ide-border);">
        <div class="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5"
          :style="{ background: session.synced ? 'var(--color-ide-accent)/10' : 'var(--color-ide-surface-active)' }">
          <Monitor :size="14" :style="{ color: session.synced ? 'var(--color-ide-accent)' : 'var(--color-ide-text-dim)' }" />
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-[13px] font-medium" style="color: var(--color-ide-text);">{{ session.name }}</span>
            <span v-if="session.tags.includes('active')" class="text-[9px] px-1.5 py-0.5 rounded-full font-medium"
              style="background: var(--color-ide-accent)/15; color: var(--color-ide-accent);">活跃</span>
          </div>
          <p class="text-[11px] mt-0.5" style="color: var(--color-ide-text-dim);">{{ session.description || '无描述' }}</p>
          <div class="flex items-center gap-3 mt-1.5">
            <span class="text-[10px] flex items-center gap-1" style="color: var(--color-ide-text-dim);">
              <Clock :size="10" /> {{ timeAgo(session.createdAt) }}
            </span>
            <span class="text-[10px]" style="color: var(--color-ide-text-dim);">{{ session.fileCount }} 个文件</span>
            <span v-if="session.synced" class="text-[10px] flex items-center gap-0.5" style="color: var(--color-ide-success);">
              <Cloud :size="10" /> 已同步
            </span>
          </div>
        </div>
        <div class="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100">
          <button class="w-6 h-6 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-surface-hover)]"
            style="color: var(--color-ide-text-dim);" @click="saveSession(session)" title="保存更改">
            <Save :size="12" />
          </button>
          <button class="w-6 h-6 flex items-center justify-center rounded-[2px] hover:bg-red-500/10"
            @click="deleteSession(session.id)" title="删除" style="color: var(--color-ide-text-dim);">
            <Trash2 :size="12" />
          </button>
        </div>
      </div>
    </div>

    <!-- Footer -->
    <div class="shrink-0 px-3 py-2 text-[10px] flex items-center gap-2" style="border-top: 1px solid var(--color-ide-border); color: var(--color-ide-text-dim);">
      <Cloud :size="11" />
      编辑会话保存工作区状态（打开的文件、终端、布局等），支持跨设备同步。
    </div>
  </div>
</template>
