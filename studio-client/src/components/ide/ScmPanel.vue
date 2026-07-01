<script setup lang="ts">
/**
 * CodeBuddy IDE — SCM Panel (VSCode Source Control viewlet)
 * Changes · Staged · Commit · Push/Pull · Diff Preview
 */
import { computed, ref, watch } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { useGitStore, type GitFileChange } from '@/stores/useGitStore'
import {
  GitBranch, GitCommit, RefreshCw, Plus, Minus, Check, X,
  ArrowUp, ArrowDown, Trash2, FileDiff, FileCode,
  ChevronRight, Disc, Upload, Download
} from 'lucide-vue-next'

const store = useIDEStore()
const git = useGitStore()

const expandedSections = ref<Record<string, boolean>>({
  staged: true,
  changes: true,
})

const selectedFile = ref<string | null>(null)
const diffContent = ref('')
const showDiff = ref(false)

function toggleSection(key: string) { expandedSections.value[key] = !expandedSections.value[key] }

function statusLabel(s: string): string {
  const m: Record<string, string> = {
    modified: 'M', added: 'A', deleted: 'D', untracked: 'U', renamed: 'R', staged: 'S',
  }
  return m[s] || s[0]?.toUpperCase() || '?'
}

function statusColor(s: string): string {
  return {
    modified: '#E2B714', added: '#4EC9B0', deleted: '#F48771',
    untracked: '#75BEFF', renamed: '#75BEFF', staged: '#4EC9B0',
  }[s] || '#CCA700'
}

function fileName(p: string): string { return p.split(/[\\/]/).pop() || p }
function fileDir(p: string): string {
  const parts = p.split(/[\\/]/)
  return parts.length > 1 ? parts.slice(0, -1).join('/') : ''
}

async function handleStage(file: GitFileChange) {
  if (file.status === 'staged') await git.unstageFile(file.path)
  else await git.stageFile(file.path)
}

async function handleCommit() {
  if (!git.commitMessage.trim()) return
  const ok = await git.commit()
  if (ok && store.workspaceRoot) await git.refreshGitStatus(store.workspaceRoot)
}

async function handlePushPull(action: 'push' | 'pull') {
  if (action === 'push') await git.push()
  else await git.pull()
  if (store.workspaceRoot) await git.refreshGitStatus(store.workspaceRoot)
}

function openFileInDiff(filePath: string) {
  selectedFile.value = filePath
  showDiff.value = true
  // Try to load diff content
  const tab = store.tabs.find(t => t.filePath === filePath)
  if (tab && tab.originalContent) {
    diffContent.value = tab.originalContent
  }
}

function openFile(path: string) {
  store.openFile(path)
}

watch(() => store.activeActivityItem, (v) => {
  if (v === 'git' && store.workspaceRoot) git.refreshGitStatus(store.workspaceRoot)
})
</script>

<template>
  <div class="h-full flex flex-col text-[13px]" style="background: var(--color-ide-surface)">
    <!-- Header -->
    <div class="flex items-center justify-between shrink-0 px-3"
      style="height: 38px; border-bottom: 1px solid var(--color-ide-border);">
      <span class="text-[12px] font-semibold uppercase tracking-wider text-[var(--color-ide-text)]">
        源代码管理
      </span>
      <div class="flex items-center gap-0.5">
        <button class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]" title="刷新"
          :disabled="git.isRefreshing"
          @click="store.workspaceRoot && git.refreshGitStatus(store.workspaceRoot)">
          <RefreshCw :size="13" :class="{ 'animate-spin': git.isRefreshing }" />
        </button>
        <button class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]" title="更多操作">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
            <circle cx="3" cy="8" r="1.2"/><circle cx="8" cy="8" r="1.2"/><circle cx="13" cy="8" r="1.2"/>
          </svg>
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto">
      <!-- No changes -->
      <div v-if="git.gitChanges.length === 0 && !git.isRefreshing" class="flex flex-col items-center justify-center py-12 text-[var(--color-ide-text-dim)]">
        <Check :size="24" class="mb-2 opacity-30" />
        <p class="text-[12px]">没有更改</p>
        <p class="text-[11px] opacity-50 mt-1">工作区是干净的</p>
      </div>

      <!-- Loading spinner -->
      <div v-else-if="git.isRefreshing" class="flex items-center justify-center py-6">
        <div class="flex gap-1.5">
          <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:0ms"/>
          <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:150ms"/>
          <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:300ms"/>
        </div>
        <span class="text-[12px] ml-2 text-[var(--color-ide-text-dim)]">加载中...</span>
      </div>

      <template v-else>
        <!-- ── Staged Changes ── -->
        <div v-if="git.stagedFiles.length > 0" class="sidebar-section">
          <button class="sidebar-section-header" @click="toggleSection('staged')">
            <ChevronRight :size="12" class="transition-transform duration-150 shrink-0"
              :class="{ 'rotate-90': expandedSections.staged }" />
            <span>暂存的更改</span>
            <span class="text-[11px] opacity-50 ml-auto mr-1">{{ git.stagedFiles.length }}</span>
            <span class="text-[10px] px-1.5 rounded hover:bg-[var(--color-ide-surface-hover)] cursor-pointer inline-flex items-center"
              @click.stop="git.unstageAll()" title="全部取消暂存" role="button" tabindex="0">
              <Minus :size="11" />
            </span>
          </button>
          <div v-if="expandedSections.staged" class="py-0.5">
            <div v-for="change in git.stagedFiles" :key="'s-'+change.path"
              class="scm-file-row flex items-center h-8 px-5 cursor-pointer"
              @click="openFileInDiff(change.path)" @dblclick="openFile(change.path)">
              <span class="text-[11px] font-bold w-4 shrink-0" :style="{ color: statusColor(change.status) }">{{ statusLabel(change.status) }}</span>
              <span class="flex-1 truncate text-[13px] text-[var(--color-ide-text)]">{{ fileName(change.path) }}</span>
              <span class="text-[10px] text-[var(--color-ide-text-dim)] opacity-40 ml-1 truncate max-w-[80px]">{{ fileDir(change.path) }}</span>
              <button class="opacity-0 group-hover:opacity-100 hover:text-[var(--color-ide-text)] transition-opacity text-[var(--color-ide-text-dim)]"
                @click.stop="handleStage(change)" title="取消暂存">
                <Minus :size="13" />
              </button>
            </div>
          </div>
        </div>

        <!-- ── Changes (Unstaged) ── -->
        <div v-if="git.unstagedFiles.length > 0" class="sidebar-section">
          <button class="sidebar-section-header" @click="toggleSection('changes')">
            <ChevronRight :size="12" class="transition-transform duration-150 shrink-0"
              :class="{ 'rotate-90': expandedSections.changes }" />
            <span>更改</span>
            <span class="text-[11px] opacity-50 ml-auto mr-1">{{ git.unstagedFiles.length }}</span>
            <span class="text-[10px] px-1.5 rounded hover:bg-[var(--color-ide-surface-hover)] cursor-pointer inline-flex items-center"
              @click.stop="git.stageAll()" title="全部暂存" role="button" tabindex="0">
              <Plus :size="11" />
            </span>
          </button>
          <div v-if="expandedSections.changes" class="py-0.5">
            <div v-for="change in git.unstagedFiles" :key="'u-'+change.path"
              class="scm-file-row flex items-center h-8 px-5 cursor-pointer group"
              @click="openFileInDiff(change.path)" @dblclick="openFile(change.path)">
              <span class="text-[11px] font-bold w-4 shrink-0" :style="{ color: statusColor(change.status) }">{{ statusLabel(change.status) }}</span>
              <span class="flex-1 truncate text-[13px] text-[var(--color-ide-text)]">{{ fileName(change.path) }}</span>
              <span class="text-[10px] text-[var(--color-ide-text-dim)] opacity-40 ml-1 truncate max-w-[80px]">{{ fileDir(change.path) }}</span>
              <div class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity shrink-0 ml-1">
                <button class="hover:text-green-400 transition-colors text-[var(--color-ide-text-dim)]"
                  @click.stop="handleStage(change)" title="暂存">
                  <Plus :size="13" />
                </button>
                <button class="hover:text-red-400 transition-colors text-[var(--color-ide-text-dim)]"
                  @click.stop="git.discardChanges(change.path)" title="放弃更改">
                  <Trash2 :size="13" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </template>

      <!-- Diff Preview Panel -->
      <div v-if="showDiff && selectedFile" class="border-t border-[var(--color-ide-border)] mt-2">
        <div class="flex items-center justify-between px-3 py-1.5 bg-[var(--color-ide-bg-secondary)] border-b border-[var(--color-ide-border)]">
          <div class="flex items-center gap-1.5 min-w-0">
            <FileDiff :size="12" class="text-[var(--color-ide-accent)]" />
            <span class="text-[12px] font-medium text-[var(--color-ide-text)] truncate">{{ fileName(selectedFile) }}</span>
          </div>
          <button class="text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]" @click="showDiff=false">
            <X :size="12" />
          </button>
        </div>
        <div class="p-2 max-h-[200px] overflow-auto font-mono text-[11px] text-[var(--color-ide-text-dim)]">
          <pre class="whitespace-pre-wrap">{{ diffContent || '无法加载差异视图' }}</pre>
        </div>
      </div>
    </div>

    <!-- ── Commit Area (VSCode style: always visible input) ── -->
    <div class="shrink-0 border-t border-[var(--color-ide-border)] p-2 space-y-2 bg-[var(--color-ide-bg-secondary)]">
      <!-- Branch + Push/Pull bar -->
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-1.5 text-[12px] text-[var(--color-ide-text)]">
          <GitBranch :size="13" class="text-[var(--color-ide-accent)]" />
          <span class="font-medium">{{ git.gitBranch || 'main' }}</span>
          <span v-if="git.gitAhead > 0" class="text-[11px] text-blue-400 ml-1">{{ '↑' + git.gitAhead }}</span>
          <span v-if="git.gitBehind > 0" class="text-[11px] text-yellow-400">{{ '↓' + git.gitBehind }}</span>
        </div>
        <div class="flex items-center gap-0.5">
          <button class="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] transition-colors" title="拉取" @click="handlePushPull('pull')">
            <Download :size="11" /> Pull
          </button>
          <button class="flex items-center gap-1 px-2 py-0.5 rounded text-[10px] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] transition-colors" title="推送" @click="handlePushPull('push')">
            <Upload :size="11" /> Push
          </button>
        </div>
      </div>

      <!-- Commit Message -->
      <div class="flex flex-col gap-1.5">
        <textarea v-model="git.commitMessage" rows="2"
          class="w-full bg-[var(--color-editor-bg)] border border-[var(--color-ide-border)] rounded-md px-2.5 py-1.5 text-[12px] text-[var(--color-ide-text)] placeholder:text-[var(--color-ide-text-dim)]/50 resize-none outline-none focus:border-[var(--color-ide-accent)]/50 font-mono"
          placeholder="提交信息 (Ctrl+Enter 提交)"
          @keydown.ctrl.enter.prevent="handleCommit" />
        <button class="flex items-center justify-center gap-1.5 w-full py-1.5 rounded-md text-[12px] font-semibold transition-all duration-150"
          :class="git.commitMessage.trim()
            ? 'bg-[var(--color-ide-accent)] text-white hover:brightness-110 active:scale-[0.98]'
            : 'bg-[var(--color-ide-bg-tertiary)] text-[var(--color-ide-text-dim)] cursor-not-allowed'"
          :disabled="!git.commitMessage.trim() || git.isCommitting"
          @click="handleCommit">
          <GitCommit :size="12" />
          {{ git.isCommitting ? '提交中...' : '提交' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.sidebar-section-header {
  display: flex;
  align-items: center;
  gap: 4px;
  width: 100%;
  height: 24px;                       /* was 22px */
  padding: 0 8px;
  font-size: 12px;                    /* was 11px */
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--color-ide-text-dim);
  cursor: pointer;
  border: none;
  background: transparent;
  transition: color 0.1s;
}
.sidebar-section-header:hover { color: var(--color-ide-text); }
.sidebar-section { border-bottom: 1px solid var(--color-ide-border); }
.sidebar-section:last-child { border-bottom: none; }

.scm-file-row:hover {
  background: var(--color-ide-surface-hover);
}
</style>
