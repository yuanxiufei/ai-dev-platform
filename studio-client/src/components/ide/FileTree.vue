<script setup lang="ts">/**
 * CodeBuddy IDE — File Tree Component (VSCode Explorer)
 *
 * Session 28 重构: VSCode Material Icon 风格
 *  - 紧凑行高 22px
 *  - hover 显操作按钮 (新建文件 / 新建文件夹 / 刷新)
 *  - Git 状态标记 (M / A / D / U)
 *  - 缩进树状引导线
 *  - 单击打开 / 双击预览 / 右键菜单
 *  - F2 重命名 / Delete 删除 / 拖拽移动
 */
import { ref, computed, nextTick } from 'vue'
import { useIDEStore } from '@/stores/useIDEStore'
import { inputDialog } from '@/composables/useInputDialog'
import type { FileEntry } from '@/types/ide'
import {
  ChevronDown, ChevronRight, FolderOpen, FolderClosed, FileCode, FileJson,
  FileText, Image as ImgIcon, Archive, File, FileSymlink, FilePlus, FolderPlus,
  Pencil, Trash2, Copy, AtSign, RefreshCw, MoreHorizontal,
} from 'lucide-vue-next'

const store = useIDEStore()
const props = defineProps<{ entries?: FileEntry[]; depth?: number }>()
const entries = computed(() => props.entries ?? store.fileTree)

const emit = defineEmits<{
  (e: "mentionFile", path: string, name: string): void
}>()

/** Right-click context menu */
const contextMenu = ref<{ x: number; y: number; entry: FileEntry } | null>(null)

/** Inline rename (F2) */
const renamingPath = ref<string | null>(null)
const renameValue = ref('')
const renameInputRef = ref<HTMLInputElement | null>(null)

/** VSCode 对标：Git 状态标记 — 从 useIDEStore.gitChanges 真实获取 */
const gitStatus = computed<Record<string, 'M' | 'A' | 'D' | 'U' | '?'>>(() => {
  const map: Record<string, 'M' | 'A' | 'D' | 'U' | '?'> = {}
  for (const change of store.gitChanges) {
    const label: 'M' | 'A' | 'D' | 'U' | '?' =
      change.status === 'added' || change.status === 'staged' ? 'A'
      : change.status === 'modified' ? 'M'
      : change.status === 'deleted' ? 'D'
      : change.status === 'untracked' ? 'U'
      : '?'
    map[change.path] = label
  }
  return map
})

/** 文件图标映射 (VSCode Material Icon 风格 — 淡色调) */
function getIcon(e: FileEntry) {
  if (e.isDir) return e.expanded ? FolderOpen : FolderClosed
  const ext = e.name.split('.').pop()?.toLowerCase() ?? ''
  if (['ts','tsx','js','jsx','py','rs','go','java','c','cpp','vue','html','htm'].includes(ext)) return FileCode
  if (['json','toml'].includes(ext)) return FileJson
  if (ext === 'md') return FileText
  if (['png','jpg','jpeg','gif','svg','ico','webp'].includes(ext)) return ImgIcon
  if (['zip','tar','gz','rar','7z'].includes(ext)) return Archive
  if (e.name.startsWith('.') || ['lock','gitignore','env','dockerfile','mod'].includes(e.name.toLowerCase())) return FileSymlink
  return File
}

/** 文件图标颜色 (VSCode Material Icon 淡色调) */
function getColor(e: FileEntry): string {
  if (e.isDir) return 'var(--ft-folder-color)'
  if (e.name === 'package.json') return 'var(--ft-npm-red)'
  if (e.name === 'README.md') return 'var(--ft-readme-blue)'
  if (e.name === '.gitignore') return 'var(--ft-gitignore-pink)'
  if (e.name === 'Dockerfile') return 'var(--ft-docker-blue)'
  const c: Record<string,string> = {
    ts:'var(--ft-icon-ts)',tsx:'var(--ft-icon-tsx)',
    js:'var(--ft-icon-js)',jsx:'var(--ft-icon-jsx)',
    py:'var(--ft-icon-py)',rs:'var(--ft-icon-rs)',go:'var(--ft-icon-go)',java:'var(--ft-icon-java)',
    json:'var(--ft-icon-json)',md:'var(--ft-icon-md)',html:'var(--ft-icon-html)',css:'var(--ft-icon-css)',
    vue:'var(--ft-icon-vue)',sh:'var(--ft-icon-sh)',yaml:'var(--ft-icon-yaml)',toml:'var(--ft-icon-toml)',
  }
  return c[e.name.split('.').pop()?.toLowerCase() ?? ''] ?? 'var(--ft-icon-default)'
}

/** 单击行为: 文件→打开, 文件夹→展开/折叠 */
function handleClick(e: FileEntry): void {
  if (e.isDir) {
    store.toggleExpand(e)
  } else if (e.path) {
    store.openFile(e.path)
  }
}

/** 双击文件: 重命名 (在 VSCode 中 F2 才重命名, 双击仅打开; 我们保留 F2) */
function handleKeydown(ev: KeyboardEvent, entry: FileEntry): void {
  if (ev.key === 'F2' && !entry.isDir) {
    ev.preventDefault(); ev.stopPropagation()
    startRename(entry)
  }
  if (ev.key === 'Delete' && !entry.isDir) {
    ev.preventDefault(); ev.stopPropagation()
    handleDelete()
  }
}

function startRename(entry: FileEntry): void {
  renamingPath.value = entry.path
  renameValue.value = entry.name
  nextTick(() => {
    renameInputRef.value?.focus()
    renameInputRef.value?.select()
  })
}

async function commitRename(entry: FileEntry): Promise<void> {
  const newName = renameValue.value.trim()
  if (!newName || newName === entry.name || !entry.path) {
    renamingPath.value = null
    return
  }
  const renamed = await store.renameFileEntry(entry.path, newName)
  if (renamed) {
    const parent = findParent(store.fileTree, entry.path)
    if (parent?.children) await store.refreshEntry(parent)
  }
  renamingPath.value = null
}

function cancelRename(): void {
  renamingPath.value = null
}

/** 拖拽 — 暂未实现实际移动, 仅视觉提示 */
function onFileDragStart(e: DragEvent, entry: FileEntry): void {
  e.dataTransfer!.setData("text/plain", entry.path)
  e.dataTransfer!.effectAllowed = "move"
}
function onFileDragOver(e: DragEvent): void {
  e.preventDefault(); e.dataTransfer!.dropEffect = "move"
}
function onFileDrop(_e: DragEvent, targetDir: FileEntry): void {
  // Placeholder — 实际文件移动需要 Tauri 后端支持
}

function handleContextMenu(ev: MouseEvent, entry: FileEntry): void {
  ev.preventDefault()
  contextMenu.value = { x: ev.clientX, y: ev.clientY, entry }
}
function closeContextMenu(): void { contextMenu.value = null }

async function handleCopyPath(): Promise<void> {
  const entry = contextMenu.value?.entry
  if (!entry?.path) return
  try { await navigator.clipboard.writeText(entry.path) } catch { /* ignore */ }
  closeContextMenu()
}

function handleMentionInChat(): void {
  const entry = contextMenu.value?.entry
  if (!entry?.path) return
  emit("mentionFile", entry.path, entry.name)
  closeContextMenu()
}

async function handleNewFile(): Promise<void> {
  const target = contextMenu.value!.entry
  const parentDir = target?.isDir
    ? target.path
    : target?.path?.replace(/[/\\][^/\\]+$/, '') ?? store.workspaceRoot
  if (!parentDir) return
  closeContextMenu()
  const name = await inputDialog({
    title: '新建文件',
    placeholder: '请输入文件名 (含扩展名, 如 main.ts)',
    confirmText: '创建',
    validator: (n) => /[\\/:*?"<>|]/.test(n) ? '名称不能包含以下字符: \\ / : * ? " < > |' : null,
  })
  if (!name) return
  const created = await store.createFileEntry(parentDir, name.trim())
  if (created) {
    const parent = store.findEntryByPath(store.fileTree, parentDir)
    if (parent?.children) {
      parent.children.push(created)
      parent.children.sort((a, b) => {
        if (a.isDir !== b.isDir) return a.isDir ? -1 : 1
        return a.name.toLowerCase().localeCompare(b.name.toLowerCase())
      })
    }
    store.openFile(created.path)
  }
}

async function handleNewFolder(): Promise<void> {
  const target = contextMenu.value!.entry
  const parentDir = target?.isDir
    ? target.path
    : target?.path?.replace(/[/\\][^/\\]+$/, '') ?? store.workspaceRoot
  if (!parentDir) return
  closeContextMenu()
  const name = await inputDialog({
    title: '新建文件夹',
    placeholder: '请输入文件夹名',
    confirmText: '创建',
    validator: (n) => /[\\/:*?"<>|]/.test(n) ? '名称不能包含以下字符: \\ / : * ? " < > |' : null,
  })
  if (!name) return
  const created = await store.createFolderEntry(parentDir, name.trim())
  if (created) {
    const parent = store.findEntryByPath(store.fileTree, parentDir)
    if (parent?.children) {
      parent.children.push(created)
      parent.children.sort((a, b) => {
        if (a.isDir !== b.isDir) return a.isDir ? -1 : 1
        return a.name.toLowerCase().localeCompare(b.name.toLowerCase())
      })
    }
  }
}

async function handleRename(): Promise<void> {
  const entry = contextMenu.value!.entry
  if (!entry?.path) return
  closeContextMenu()
  startRename(entry)
}

async function handleDelete(): Promise<void> {
  const entry = contextMenu.value?.entry
  if (!entry?.path) return
  if (contextMenu.value) closeContextMenu()
  const confirm = window.confirm(`删除 "${entry.name}"?`)
  if (!confirm) return
  const ok = await store.deleteFileEntry(entry.path)
  if (ok) {
    const parent = findParent(store.fileTree, entry.path)
    if (parent?.children) await store.refreshEntry(parent)
  }
}

function findParent(entries: FileEntry[], childPath: string): FileEntry | null {
  for (const e of entries) {
    if (e.isDir && e.children) {
      if (e.children.some(c => c.path === childPath)) return e
      const f = findParent(e.children, childPath)
      if (f) return f
    }
  }
  return null
}

/** Hover 操作按钮 — 新建文件 / 新建文件夹 / 刷新 */
function onHeaderNewFile() {
  const root = store.workspaceRoot
  if (!root) return
  inputDialog({
    title: '新建文件',
    placeholder: '请输入文件名 (含扩展名)',
    confirmText: '创建',
    validator: (n) => /[\\/:*?"<>|]/.test(n) ? '名称不能包含特殊字符' : null,
  }).then((name) => {
    if (!name) return
    store.createFileEntry(root, name.trim()).then((created) => {
      if (created) {
        store.fileTree.push(created)
        store.openFile(created.path)
      }
    })
  })
}
function onHeaderNewFolder() {
  const root = store.workspaceRoot
  if (!root) return
  inputDialog({
    title: '新建文件夹',
    placeholder: '请输入文件夹名',
    confirmText: '创建',
    validator: (n) => /[\\/:*?"<>|]/.test(n) ? '名称不能包含特殊字符' : null,
  }).then((name) => {
    if (!name) return
    store.createFolderEntry(root, name.trim()).then((created) => {
      if (created) {
        store.fileTree.push(created)
      }
    })
  })
}
function onHeaderRefresh() {
  store.initFileTree()
}
</script>

<template>
  <div class="file-tree text-[13px] select-none">
    <!-- ✅ 第一次 v-for 渲染所有 entry 行 + 紧跟递归子树 — 必须在同一 v-for 才能保证 children 紧跟父级位置 -->
    <template v-for="entry in entries" :key="entry.path || entry.name">
      <div
        class="tree-item group relative flex items-center pr-1.5 cursor-pointer transition-colors"
        :class="{
          'is-selected': store.selectedFilePath === entry.path && renamingPath !== entry.path,
          'is-renaming': renamingPath === entry.path,
        }"
        :style="{
          height: '22px',
          paddingLeft: `${(depth ?? 0) * 18 + 18}px`,
        }"
        @click.stop="handleClick(entry)"
        @contextmenu.stop="handleContextMenu($event, entry)"
        @keydown="handleKeydown($event, entry)"
        tabindex="0"
        @dragover="onFileDragOver"
        @drop="onFileDrop($event, entry)">

        <!-- Active left bar (VSCode 风格: 选中时 2px 高亮条) -->
        <div v-if="store.selectedFilePath === entry.path && renamingPath !== entry.path"
          class="absolute left-0 top-0 bottom-0 w-[2px] shrink-0"
          style="background: var(--color-ide-accent);" />

        <!-- 缩进引导线 (VSCode 风格) — 每条线在该层缩进的中线位置 -->
        <div v-for="i in (depth ?? 0)" :key="'g-' + i" class="absolute top-0 bottom-0 w-px pointer-events-none"
          :style="{ left: `${(i - 1) * 18 + 27}px`, background: 'var(--ft-guide-line)' }" />

        <!-- 展开箭头 -->
        <span class="w-3.5 h-4 flex items-center justify-center shrink-0">
          <component v-if="entry.isDir" :is="entry.expanded ? ChevronDown : ChevronRight" :size="11" style="color: var(--color-ide-text-dim);" />
        </span>

        <!-- 文件/文件夹图标 -->
        <span class="w-4 h-4 flex items-center justify-center mr-1 shrink-0">
          <component :is="getIcon(entry)" :size="14" :style="{ color: getColor(entry) }" />
        </span>

        <!-- Inline rename input -->
        <input
          v-if="renamingPath === entry.path"
          ref="renameInputRef"
          v-model="renameValue"
          class="flex-1 min-w-0 rounded px-1 py-0 text-[13px] outline-none text-[var(--color-ide-text)] h-[18px]"
          :style="{ background: 'var(--ft-rename-bg)', border: '1px solid var(--color-ide-accent)' }"
          @blur="commitRename(entry)"
          @keydown.enter="commitRename(entry)"
          @keydown.escape="cancelRename()"
          @click.stop
        />
        <!-- File/Folder name -->
        <span v-else class="truncate flex-1"
          :class="{
            'font-medium': store.selectedFilePath === entry.path,
          }"
          :style="{
            color: store.selectedFilePath === entry.path ? 'var(--color-ide-text)' : 'var(--color-ide-text)',
          }"
          draggable="true"
          @dragstart="onFileDragStart($event, entry)">
          {{ entry.name }}
        </span>

        <!-- Git 状态标记 (M/A/D/U/?) — 紧贴文件名右侧 -->
        <span v-if="!entry.isDir && gitStatus[entry.path]" class="ml-1 text-[10px] font-bold shrink-0 font-mono"
          :style="{
            color: gitStatus[entry.path] === 'M' ? 'var(--color-ide-info)'
                : gitStatus[entry.path] === 'A' ? 'var(--color-ide-success)'
                : gitStatus[entry.path] === 'D' ? 'var(--color-ide-error)'
                : gitStatus[entry.path] === 'U' ? 'var(--color-ide-warning)'
                : 'var(--color-ide-text-dim)'
          }">
          {{ gitStatus[entry.path] }}
        </span>

        <!-- 文件夹 hover 操作按钮 (VSCode 风格) -->
        <div v-if="entry.isDir" class="hidden group-hover:flex items-center gap-0.5 shrink-0 ml-1">
          <button
            class="w-4 h-4 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-surface-active)] transition-colors"
            title="新建文件"
            @click.stop="handleContextMenu($event, entry); contextMenu && (handleNewFile())"
          >
            <FilePlus :size="11" style="color: var(--color-ide-text-dim);" />
          </button>
          <button
            class="w-4 h-4 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-surface-active)] transition-colors"
            title="新建文件夹"
            @click.stop="handleContextMenu($event, entry); contextMenu && (handleNewFolder())"
          >
            <FolderPlus :size="11" style="color: var(--color-ide-text-dim);" />
          </button>
        </div>
      </div>

      <!-- ✅ 递归渲染子目录 — 必须在同一 v-for 内, 才能紧跟父级 entry 渲染位置 -->
      <FileTree v-if="entry.isDir && entry.expanded && entry.children?.length" :entries="entry.children" :depth="(depth ?? 0) + 1" />
    </template>

    <!-- Context Menu -->
    <Teleport to="body">
      <div v-if="contextMenu" class="fixed z-[300]" :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }" @click.stop>
        <div class="w-48 bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded-[3px] shadow-[0_2px_8px_rgba(0,0,0,0.36)] py-1 text-[13px]">
          <button v-if="!contextMenu.entry?.isDir" class="context-menu-item w-full text-left flex items-center justify-between gap-6"
            @click="contextMenu.entry?.path && store.openFile(contextMenu.entry.path); closeContextMenu()">
            <span>打开</span><kbd>Enter</kbd>
          </button>
          <button v-if="!contextMenu.entry?.isDir" class="context-menu-item w-full text-left flex items-center gap-2"
            @click="handleCopyPath()">
            <Copy :size="13" /> 复制路径
          </button>
          <button v-if="!contextMenu.entry?.isDir" class="context-menu-item w-full text-left flex items-center gap-2"
            @click="handleMentionInChat()">
            <AtSign :size="13" /> @-引用到对话
          </button>
          <hr class="my-1 border-[var(--color-ide-border)]" />
          <button v-if="contextMenu.entry?.isDir" class="context-menu-item w-full text-left flex items-center gap-2" @click="handleNewFile()">
            <FilePlus :size="13" /> 新建文件
          </button>
          <button v-if="contextMenu.entry?.isDir" class="context-menu-item w-full text-left flex items-center gap-2" @click="handleNewFolder()">
            <FolderPlus :size="13" /> 新建文件夹
          </button>
          <button class="context-menu-item w-full text-left flex items-center justify-between gap-6" @click="handleRename()">
            <span><Pencil :size="13" class="inline mr-2"/>重命名</span><kbd>F2</kbd>
          </button>
          <hr class="my-1 border-[var(--color-ide-border)]" />
          <button class="context-menu-item w-full text-left flex items-center justify-between gap-6 text-red-400 hover:text-red-300" @click="handleDelete()">
            <span><Trash2 :size="13" class="inline mr-2"/>删除</span><kbd>Del</kbd>
          </button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* ═══ FileTree 图标颜色 + 语义变量（组件级 CSS 变量） ═══ */
.file-tree {
  font-size: 13px;
  --ft-folder-color: #90A4AE;
  --ft-npm-red: #CB3837;      --ft-readme-blue: #42A5F5;
  --ft-gitignore-pink: #F06292; --ft-docker-blue: #2496ED;
  --ft-icon-ts: #42A5F5;      --ft-icon-tsx: #42A5F5;
  --ft-icon-js: #F7DF1E;      --ft-icon-jsx: #61DAFB;
  --ft-icon-py: #3776AB;      --ft-icon-rs: #DEA584;
  --ft-icon-go: #00ADD8;      --ft-icon-java: #B07219;
  --ft-icon-json: #90A4AE;    --ft-icon-md: #42A5F5;
  --ft-icon-html: #E44D26;    --ft-icon-css: #264DE4;
  --ft-icon-vue: #42A5F5;     --ft-icon-sh: #4CAF50;
  --ft-icon-yaml: #CB171E;    --ft-icon-toml: #9C4221;
  --ft-icon-default: #90A4AE;
  --ft-guide-line: rgba(150, 150, 150, 0.55);
  --ft-rename-bg: #3C3C3C;
  --ft-selection-bg: rgba(0, 122, 204, 0.18);
}
.tree-item {
  user-select: none;
  color: var(--color-ide-text);
}
.tree-item:hover {
  background: var(--color-ide-surface-hover);
}
.tree-item.is-selected {
  /* ✅ Tauri WebView2 兼容：rgba 替代 color-mix */
  background: var(--ft-selection-bg);
}
.tree-item:focus {
  outline: none;
}
.tree-item:focus-visible {
  outline: 1px solid var(--color-ide-accent);
  outline-offset: -1px;
}
</style>
