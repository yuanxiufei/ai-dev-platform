<script setup lang="ts">
/**
 * MultiDiffPanel — VSCode multiDiffEditor 对标
 *
 * Session 42: SCM 所有变更一览视图（非逐文件 MergeEditor）
 * 借鉴: VSCode contrib/multiDiffEditor (ScmMultiDiffSourceResolver)
 */
import { ref, computed } from "vue"
import { useIDEStore } from "@/stores/useIDEStore"
import { useGitStore, type GitFileChange } from "@/stores/useGitStore"
import {
  FileDiff, GitBranch, ChevronDown, ChevronRight, ExternalLink,
  ArrowUp, ArrowDown, X, Eye, CheckCircle2, RotateCcw,
} from "lucide-vue-next"

const store = useIDEStore()
const git = useGitStore()

const expandedFiles = ref<Set<string>>(new Set())

function toggleFile(file: string): void {
  if (expandedFiles.value.has(file)) {
    expandedFiles.value.delete(file)
  } else {
    expandedFiles.value.add(file)
  }
  expandedFiles.value = new Set(expandedFiles.value)
}

/** 获取文件变更的统计 */
const diffStats = computed(() => {
  const stats = { additions: 0, deletions: 0, modified: 0, added: 0, deleted: 0, untracked: 0 }
  for (const f of git.gitChanges) {
    switch (f.status) {
      case "M": stats.modified++; break
      case "A": stats.added++; break
      case "D": stats.deleted++; break
      case "?": stats.untracked++; break
      case "R": stats.modified++; break
    }
    stats.additions += f.additions || 0
    stats.deletions += f.deletions || 0
  }
  return stats
})

/** 变更类型中文映射 */
const statusLabel = (s: string) => ({ M: "修改", A: "新增", D: "删除", "?": "未跟踪", R: "重命名" }[s] ?? s)

/** 变更类型颜色 */
const statusColor = (s: string) => {
  const map: Record<string, string> = {
    M: "var(--color-ide-warning, #dcdcaa)",
    A: "var(--color-ide-success, #4ec9b0)",
    D: "var(--color-ide-error, #f44747)",
    "?": "var(--color-ide-info, #569cd6)",
    R: "var(--color-ide-warning, #dcdcaa)",
  }
  return map[s] ?? "var(--color-ide-text-dim)"
}

/** 查看文件差异（打开到编辑器/对比视图） */
function openDiff(file: GitFileChange): void {
  if (file.status === "A" || file.status === "?") {
    store.openFile(file.file)
  } else {
    // 使用 Split Editor + Compare
    store.splitEditor("right")
    store.openFile(file.file)
  }
}

/** 暂存文件 */
function stageFile(file: string): void {
  if (store.workspaceRoot) {
    git.stageFile(store.workspaceRoot, file)
  }
}

/** 取消暂存 */
function unstageFile(file: string): void {
  if (store.workspaceRoot) {
    git.unstageFile(store.workspaceRoot, file)
  }
}

/** 折叠全部 */
function collapseAll(): void {
  expandedFiles.value = new Set()
}

/** 展开全部 */
function expandAll(): void {
  expandedFiles.value = new Set(git.gitChanges.map(f => f.file))
}
</script>

<template>
  <div class="flex flex-col h-full" style="background: var(--color-ide-bg);">
    <!-- 头部统计 -->
    <div class="flex items-center justify-between px-3 py-2 border-b" style="border-color: var(--color-ide-border);">
      <div class="flex items-center gap-3">
        <GitBranch :size="14" style="color: var(--color-ide-accent);" />
        <span class="text-[12px] font-semibold" style="color: var(--color-ide-text);">多文件差异</span>
        <span class="text-[11px]" style="color: var(--color-ide-text-dim);">{{ git.gitChanges.length }} 个文件</span>
      </div>
      <div class="flex items-center gap-2 text-[11px]" style="color: var(--color-ide-text-dim);">
        <span style="color: var(--color-ide-success, #4ec9b0);">+{{ diffStats.additions }}</span>
        <span style="color: var(--color-ide-error, #f44747);">-{{ diffStats.deletions }}</span>
        <button @click="expandAll" class="px-2 py-0.5 rounded text-[10px] hover:bg-white/5">展开全部</button>
        <button @click="collapseAll" class="px-2 py-0.5 rounded text-[10px] hover:bg-white/5">折叠全部</button>
      </div>
    </div>

    <!-- 文件列表 -->
    <div class="flex-1 overflow-y-auto scrollbar-thin">
      <!-- 暂存区 -->
      <div v-if="git.stagedChanges.length > 0" class="border-b" style="border-color: var(--color-ide-border);">
        <div class="flex items-center gap-2 px-3 py-1.5" style="background: var(--color-ide-bg-secondary);">
          <span class="text-[11px] font-semibold uppercase" style="color: var(--color-ide-text-dim);">已暂存的更改</span>
          <span class="text-[10px]" style="color: var(--color-ide-text-dim); opacity: 0.5;">{{ git.stagedChanges.length }} 个文件</span>
        </div>
        <div
          v-for="file in git.stagedChanges" :key="'staged-' + file.file"
          class="flex items-center gap-2 px-3 py-1.5 hover:bg-white/5 cursor-pointer transition-colors"
          @click="openDiff(file)">
          <Eye :size="13" style="color: var(--color-ide-success, #4ec9b0);" />
          <span class="text-[12px] flex-1 truncate" style="color: var(--color-ide-text);">{{ file.file.split("/").pop() }}</span>
          <span class="text-[10px] opacity-50" style="color: var(--color-ide-text-dim);">{{ file.file.split("/").slice(0, -1).join("/") }}</span>
          <button @click.stop="unstageFile(file.file)" class="p-0.5 rounded hover:bg-white/10">
            <RotateCcw :size="12" style="color: var(--color-ide-text-dim);" />
          </button>
        </div>
      </div>

      <!-- 未暂存的更改 -->
      <div>
        <div class="flex items-center gap-2 px-3 py-1.5" style="background: var(--color-ide-bg-secondary);">
          <span class="text-[11px] font-semibold uppercase" style="color: var(--color-ide-text-dim);">更改</span>
          <span class="text-[10px]" style="color: var(--color-ide-text-dim); opacity: 0.5;">{{ git.gitChanges.length }} 个文件</span>
        </div>

        <div
          v-for="file in git.gitChanges" :key="file.file"
          class="border-b border-transparent hover:border-current"
          style="border-color: var(--color-ide-border); border-opacity: 0.3;">
          <!-- 文件头部 -->
          <div
            class="flex items-center gap-2 px-3 py-1.5 cursor-pointer hover:bg-white/5 transition-colors"
            @click="toggleFile(file.file)">
            <button class="p-0.5">
              <ChevronRight v-if="!expandedFiles.has(file.file)" :size="12" style="color: var(--color-ide-text-dim);" />
              <ChevronDown v-else :size="12" style="color: var(--color-ide-text-dim);" />
            </button>
            <span class="text-[11px] font-mono px-1.5 py-0.5 rounded" :style="{ background: statusColor(file.status) + '20', color: statusColor(file.status) }">
              {{ statusLabel(file.status) }}
            </span>
            <span class="text-[12px] flex-1 truncate" style="color: var(--color-ide-text);">{{ file.file.split("/").pop() }}</span>
            <span class="text-[10px] opacity-50 hidden lg:inline" style="color: var(--color-ide-text-dim);">{{ file.file.split("/").slice(0, -1).join("/") }}</span>
            <!-- 增减行数 -->
            <span v-if="file.additions" class="text-[10px]" style="color: var(--color-ide-success, #4ec9b0);">+{{ file.additions }}</span>
            <span v-if="file.deletions" class="text-[10px]" style="color: var(--color-ide-error, #f44747);">-{{ file.deletions }}</span>
            <!-- 操作按钮 -->
            <button @click.stop="openDiff(file)" class="p-0.5 rounded hover:bg-white/10" title="查看差异">
              <Eye :size="12" style="color: var(--color-ide-text-dim);" />
            </button>
            <button @click.stop="stageFile(file.file)" class="p-0.5 rounded hover:bg-white/10" title="暂存更改">
              <CheckCircle2 :size="12" style="color: var(--color-ide-text-dim);" />
            </button>
          </div>

          <!-- 展开的 diff 预览 -->
          <div v-if="expandedFiles.has(file.file)" class="border-t" style="border-color: var(--color-ide-border); border-opacity: 0.2; max-height: 300px; overflow-y: auto;">
            <div class="font-mono text-[11px] leading-[18px] p-2" style="background: var(--color-ide-bg);">
              <div v-for="(line, li) in (file.diffPreview || []).slice(0, 50)" :key="li"
                :style="{
                  whiteSpace: 'pre',
                  background: line.startsWith('+') ? '#2ea04320' : line.startsWith('-') ? '#f8514920' : line.startsWith('@@') ? '#61afef10' : 'transparent',
                  color: line.startsWith('+') ? '#4ec9b0' : line.startsWith('-') ? '#f44747' : line.startsWith('@@') ? '#569cd6' : 'var(--color-ide-text-dim)',
                  paddingLeft: '8px',
                }">
                {{ line || ' ' }}
              </div>
              <div v-if="(file.diffPreview || []).length > 50" class="text-center py-1" style="color: var(--color-ide-text-dim);">... 更多行未显示</div>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-if="git.gitChanges.length === 0 && git.stagedChanges.length === 0" class="flex flex-col items-center justify-center py-16 gap-2">
          <CheckCircle2 :size="32" style="color: var(--color-ide-text-dim); opacity: 0.2;" />
          <span class="text-[12px]" style="color: var(--color-ide-text-dim);">没有待提交的更改</span>
          <span class="text-[10px] opacity-50" style="color: var(--color-ide-text-dim);">工作目录干净</span>
        </div>
      </div>
    </div>
  </div>
</template>
