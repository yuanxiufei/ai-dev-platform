<script setup lang="ts">
/**
 * KeybindingsPage — VS Code Keyboard Shortcuts Editor (像素级对齐)
 *
 * 对标 VS Code Keyboard Shortcuts 页面:
 *   - 搜索/过滤快捷键 (按命令名或按键)
 *   - 按来源分组 (默认/用户自定义)
 *   - 快捷键冲突检测 (红色高亮冲突项)
 *   - 双击编辑快捷键 (录制模式)
 *   - when 条件列
 *   - 复制/重置快捷键
 *   - JSON 配置模式切换
 */
import { ref, computed, onMounted, onUnmounted } from "vue"
import {
  Search, X, Keyboard, RotateCw, AlertTriangle, Pencil, Copy,
  Undo2, FileJson, SplitSquareVertical
} from "lucide-vue-next"
import { useIDEStore } from "@/stores/useIDEStore"
import { useKeybindingStore } from "@/stores/useKeybindingStore"

const store = useIDEStore()
const kb = useKeybindingStore()

// ── 预定义完整快捷键列表 (对标 VS Code Default Keybindings) ──
interface KeybindingEntry {
  id: string
  command: string
  key: string
  when?: string
  source: "default" | "user"
  category: string
  description?: string
}

const defaultBindings: KeybindingEntry[] = [
  // 全局
  { id: "kb-1", command: "workbench.action.showCommands", key: "Ctrl+Shift+P", when: "global", source: "default", category: "工作台", description: "显示所有命令" },
  { id: "kb-2", command: "workbench.action.quickOpen", key: "Ctrl+P", when: "global", source: "default", category: "工作台", description: "快速打开文件" },
  { id: "kb-3", command: "workbench.action.showAllSymbols", key: "Ctrl+T", when: "global", source: "default", category: "工作台", description: "转到工作区中的符号" },
  { id: "kb-4", command: "workbench.action.focusSideBar", key: "Ctrl+0", when: "global", source: "default", category: "工作台", description: "聚焦侧边栏" },
  // 文件
  { id: "kb-5", command: "workbench.action.files.save", key: "Ctrl+S", when: "editor", source: "default", category: "文件", description: "保存当前文件" },
  { id: "kb-6", command: "workbench.action.files.saveAll", key: "Ctrl+K S", when: "global", source: "default", category: "文件", description: "保存所有文件" },
  { id: "kb-7", command: "workbench.action.files.newUntitled", key: "Ctrl+N", when: "global", source: "default", category: "文件", description: "新建未命名文件" },
  { id: "kb-8", command: "workbench.action.closeActiveEditor", key: "Ctrl+W", when: "editor", source: "default", category: "文件", description: "关闭编辑器" },
  { id: "kb-9", command: "workbench.action.closeAllEditors", key: "Ctrl+K Ctrl+W", when: "editor", source: "default", category: "文件", description: "关闭所有编辑器" },
  // 编辑
  { id: "kb-10", command: "editor.action.clipboardCutAction", key: "Ctrl+X", when: "editor", source: "default", category: "编辑", description: "剪切" },
  { id: "kb-11", command: "editor.action.clipboardCopyAction", key: "Ctrl+C", when: "editor", source: "default", category: "编辑", description: "复制" },
  { id: "kb-12", command: "editor.action.clipboardPasteAction", key: "Ctrl+V", when: "editor", source: "default", category: "编辑", description: "粘贴" },
  { id: "kb-13", command: "editor.action.undo", key: "Ctrl+Z", when: "editor", source: "default", category: "编辑", description: "撤销" },
  { id: "kb-14", command: "editor.action.redo", key: "Ctrl+Y", when: "editor", source: "default", category: "编辑", description: "恢复" },
  { id: "kb-15", command: "editor.action.selectAll", key: "Ctrl+A", when: "editor", source: "default", category: "编辑", description: "全选" },
  { id: "kb-16", command: "editor.action.commentLine", key: "Ctrl+/", when: "editor", source: "default", category: "编辑", description: "切换行注释" },
  { id: "kb-17", command: "editor.action.blockComment", key: "Shift+Alt+A", when: "editor", source: "default", category: "编辑", description: "切换块注释" },
  { id: "kb-18", command: "editor.action.formatDocument", key: "Shift+Alt+F", when: "editor", source: "default", category: "编辑", description: "格式化文档" },
  { id: "kb-19", command: "editor.action.rename", key: "F2", when: "editor", source: "default", category: "编辑", description: "重命名符号" },
  // 导航
  { id: "kb-20", command: "editor.action.goToDefinition", key: "F12", when: "editor", source: "default", category: "导航", description: "转到定义" },
  { id: "kb-21", command: "editor.action.peekDefinition", key: "Alt+F12", when: "editor", source: "default", category: "导航", description: "速览定义" },
  { id: "kb-22", command: "editor.action.referenceSearch.trigger", key: "Shift+F12", when: "editor", source: "default", category: "导航", description: "查找所有引用" },
  { id: "kb-23", command: "editor.action.gotoLine", key: "Ctrl+G", when: "editor", source: "default", category: "导航", description: "转到行" },
  { id: "kb-24", command: "workbench.action.gotoSymbol", key: "Ctrl+Shift+O", when: "editor", source: "default", category: "导航", description: "转到文件中的符号" },
  // 搜索
  { id: "kb-25", command: "actions.find", key: "Ctrl+F", when: "editor", source: "default", category: "搜索", description: "查找" },
  { id: "kb-26", command: "editor.action.startFindReplaceAction", key: "Ctrl+H", when: "editor", source: "default", category: "搜索", description: "替换" },
  { id: "kb-27", command: "workbench.action.findInFiles", key: "Ctrl+Shift+F", when: "global", source: "default", category: "搜索", description: "在文件中查找" },
  // 视图
  { id: "kb-28", command: "workbench.action.toggleSidebarVisibility", key: "Ctrl+B", when: "global", source: "default", category: "视图", description: "切换侧边栏可见性" },
  { id: "kb-29", command: "workbench.action.togglePanel", key: "Ctrl+J", when: "global", source: "default", category: "视图", description: "切换面板" },
  { id: "kb-30", command: "workbench.action.terminal.toggleTerminal", key: "Ctrl+`", when: "global", source: "default", category: "视图", description: "切换终端" },
  { id: "kb-31", command: "workbench.view.explorer", key: "Ctrl+Shift+E", when: "global", source: "default", category: "视图", description: "显示资源管理器" },
  { id: "kb-32", command: "workbench.view.search", key: "Ctrl+Shift+F", when: "global", source: "default", category: "视图", description: "显示搜索" },
  { id: "kb-33", command: "workbench.view.scm", key: "Ctrl+Shift+G", when: "global", source: "default", category: "视图", description: "显示源代码管理" },
  { id: "kb-34", command: "workbench.view.debug", key: "Ctrl+Shift+D", when: "global", source: "default", category: "视图", description: "显示运行" },
  { id: "kb-35", command: "workbench.view.extensions", key: "Ctrl+Shift+X", when: "global", source: "default", category: "视图", description: "显示扩展" },
  { id: "kb-36", command: "workbench.action.zoomIn", key: "Ctrl+=", when: "global", source: "default", category: "视图", description: "放大" },
  { id: "kb-37", command: "workbench.action.zoomOut", key: "Ctrl+-", when: "global", source: "default", category: "视图", description: "缩小" },
  { id: "kb-38", command: "workbench.action.toggleZenMode", key: "Ctrl+K Z", when: "global", source: "default", category: "视图", description: "切换禅模式" },
  // 编辑器组
  { id: "kb-39", command: "workbench.action.splitEditor", key: "Ctrl+\\", when: "editor", source: "default", category: "编辑器组", description: "拆分编辑器" },
  { id: "kb-40", command: "workbench.action.splitEditorDown", key: "Ctrl+K Ctrl+\\", when: "editor", source: "default", category: "编辑器组", description: "向下拆分编辑器" },
  { id: "kb-41", command: "workbench.action.focusFirstEditorGroup", key: "Ctrl+1", when: "editor", source: "default", category: "编辑器组", description: "聚焦第一个编辑器组" },
  { id: "kb-42", command: "workbench.action.focusSecondEditorGroup", key: "Ctrl+2", when: "editor", source: "default", category: "编辑器组", description: "聚焦第二个编辑器组" },
  { id: "kb-43", command: "workbench.action.toggleMaximizedPanel", key: "Ctrl+Shift+M", when: "global", source: "default", category: "编辑器组", description: "切换最大化面板" },
  // 折叠
  { id: "kb-44", command: "editor.fold", key: "Ctrl+Shift+[", when: "editor", source: "default", category: "折叠", description: "折叠" },
  { id: "kb-45", command: "editor.unfold", key: "Ctrl+Shift+]", when: "editor", source: "default", category: "折叠", description: "展开" },
  { id: "kb-46", command: "editor.foldAll", key: "Ctrl+K Ctrl+0", when: "editor", source: "default", category: "折叠", description: "全部折叠" },
  { id: "kb-47", command: "editor.unfoldAll", key: "Ctrl+K Ctrl+J", when: "editor", source: "default", category: "折叠", description: "全部展开" },
  // 终端
  { id: "kb-48", command: "workbench.action.terminal.new", key: "Ctrl+Shift+`", when: "terminal", source: "default", category: "终端", description: "新建终端" },
  { id: "kb-49", command: "workbench.action.terminal.kill", key: "Ctrl+Shift+W", when: "terminal", source: "default", category: "终端", description: "关闭终端" },
  { id: "kb-50", command: "workbench.action.terminal.split", key: "Ctrl+Shift+5", when: "terminal", source: "default", category: "终端", description: "拆分终端" },
  { id: "kb-51", command: "workbench.action.terminal.clear", key: "Ctrl+K", when: "terminal", source: "default", category: "终端", description: "清屏" },
  // Debug
  { id: "kb-52", command: "workbench.action.debug.start", key: "F5", when: "global", source: "default", category: "调试", description: "开始调试" },
  { id: "kb-53", command: "workbench.action.debug.stop", key: "Shift+F5", when: "global", source: "default", category: "调试", description: "停止调试" },
  { id: "kb-54", command: "workbench.action.debug.continue", key: "F5", when: "debug", source: "default", category: "调试", description: "继续" },
  { id: "kb-55", command: "workbench.action.debug.stepOver", key: "F10", when: "debug", source: "default", category: "调试", description: "逐过程" },
  { id: "kb-56", command: "workbench.action.debug.stepInto", key: "F11", when: "debug", source: "default", category: "调试", description: "逐语句" },
  { id: "kb-57", command: "workbench.action.debug.stepOut", key: "Shift+F11", when: "debug", source: "default", category: "调试", description: "跳出" },
  { id: "kb-58", command: "workbench.action.debug.toggleBreakpoint", key: "F9", when: "editor", source: "default", category: "调试", description: "切换断点" },
  // 测试 (新增)
  { id: "kb-59", command: "workbench.action.testing.runAll", key: "Ctrl+Shift+T", when: "global", source: "default", category: "测试", description: "运行所有测试" },
  // 搜索替换
  { id: "kb-60", command: "editor.action.nextMatchFindAction", key: "F3", when: "editor", source: "default", category: "搜索", description: "查找下一个" },
  { id: "kb-61", command: "editor.action.previousMatchFindAction", key: "Shift+F3", when: "editor", source: "default", category: "搜索", description: "查找上一个" },
  { id: "kb-62", command: "editor.action.selectAllMatches", key: "Ctrl+Shift+L", when: "editor", source: "default", category: "搜索", description: "选择所有匹配项" },
  // 其他
  { id: "kb-63", command: "workbench.action.openSettings", key: "Ctrl+,", when: "global", source: "default", category: "首选项", description: "打开设置" },
  { id: "kb-64", command: "workbench.action.openKeyboardShortcuts", key: "Ctrl+K Ctrl+S", when: "global", source: "default", category: "首选项", description: "打开键盘快捷方式" },
]

// ── 状态 ──
const searchQuery = ref("")
const editingKey = ref<string | null>(null)
const recordingKey = ref("")
const selectedCategory = ref<string | null>(null)
const viewMode = ref<"table" | "json">("table")
const showConflicts = ref(false)

// ── 用户自定义快捷键 (持久化到 localStorage) ──
const userBindings = ref<KeybindingEntry[]>([])
try {
  const saved = localStorage.getItem("keybindings_user")
  if (saved) userBindings.value = JSON.parse(saved)
} catch { /* ignore */ }

function saveUserBindings(): void {
  try { localStorage.setItem("keybindings_user", JSON.stringify(userBindings.value)) } catch { /* ignore */ }
}

// ── 合并所有快捷键 ──
const allBindings = computed(() => {
  const merged = [...defaultBindings]
  // 用户自定义覆盖默认
  for (const ub of userBindings.value) {
    const idx = merged.findIndex(b => b.id === ub.id)
    if (idx !== -1) merged[idx] = ub
    else merged.push(ub)
  }
  return merged
})

// ── 分类列表 ──
const categories = computed(() => {
  const cats = new Set(allBindings.value.map(b => b.category))
  return Array.from(cats).sort()
})

// ── 过滤后的快捷键 ──
const filteredBindings = computed(() => {
  let list = allBindings.value

  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(b =>
      b.command.toLowerCase().includes(q) ||
      b.key.toLowerCase().includes(q) ||
      (b.description && b.description.toLowerCase().includes(q)) ||
      b.category.toLowerCase().includes(q)
    )
  }

  if (selectedCategory.value) {
    list = list.filter(b => b.category === selectedCategory.value)
  }

  return list
})

// ── 检测冲突 ──
const conflictMap = computed(() => {
  const keyToBindings = new Map<string, KeybindingEntry[]>()
  for (const b of filteredBindings.value) {
    if (!keyToBindings.has(b.key)) keyToBindings.set(b.key, [])
    keyToBindings.get(b.key)!.push(b)
  }
  const conflicts = new Map<string, boolean>()
  for (const [key, bindings] of keyToBindings) {
    if (bindings.length > 1) {
      for (const b of bindings) conflicts.set(b.id, true)
    }
  }
  return conflicts
})

// ── 分组展示 ──
const groupedByCategory = computed(() => {
  const groups = new Map<string, KeybindingEntry[]>()
  for (const b of filteredBindings.value) {
    if (!groups.has(b.category)) groups.set(b.category, [])
    groups.get(b.category)!.push(b)
  }
  return groups
})

// ── 开始录制快捷键 ──
function startRecording(id: string): void {
  editingKey.value = id
  recordingKey.value = ""
}

function onKeyRecord(e: KeyboardEvent): void {
  if (!editingKey.value) return
  e.preventDefault()
  e.stopPropagation()

  const parts: string[] = []
  if (e.ctrlKey || e.metaKey) parts.push("Ctrl")
  if (e.shiftKey) parts.push("Shift")
  if (e.altKey) parts.push("Alt")

  const key = e.key
  if (key === "Control" || key === "Shift" || key === "Alt" || key === "Meta") return

  if (key === "Escape") {
    editingKey.value = null
    recordingKey.value = ""
    return
  }

  let keyStr = key
  if (key === " ") keyStr = "Space"
  else if (key === "ArrowUp") keyStr = "Up"
  else if (key === "ArrowDown") keyStr = "Down"
  else if (key === "ArrowLeft") keyStr = "Left"
  else if (key === "ArrowRight") keyStr = "Right"
  else if (key === "Backspace") keyStr = "Backspace"
  else if (key === "Delete") keyStr = "Delete"
  else if (key === "Enter") keyStr = "Enter"
  else if (key === "Tab") keyStr = "Tab"
  else if (key.length === 1) keyStr = key.toUpperCase()

  if (parts.length > 0) parts.push(keyStr)
  else parts.push(keyStr)

  const newKey = parts.join("+")

  // 更新快捷键
  const binding = allBindings.value.find(b => b.id === editingKey.value)
  if (binding) {
    binding.key = newKey
    // 如果原来是默认项，创建用户自定义覆盖
    const existing = userBindings.value.find(b => b.id === editingKey.value)
    if (existing) {
      existing.key = newKey
    } else {
      userBindings.value.push({ ...binding, source: "user" })
    }
    saveUserBindings()
  }

  editingKey.value = null
  recordingKey.value = ""
}

function resetKey(id: string): void {
  // 移除用户自定义，恢复默认
  userBindings.value = userBindings.value.filter(b => b.id !== id)
  saveUserBindings()
}

function editKey(id: string): void {
  editingKey.value = id
  const binding = allBindings.value.find(b => b.id === id)
  if (binding) recordingKey.value = binding.key
}

onMounted(() => {
  document.addEventListener("keydown", onKeyRecord, true)
})

onUnmounted(() => {
  document.removeEventListener("keydown", onKeyRecord, true)
})

function keyDisplay(k: string): string {
  return k.replace(/Ctrl\+/g, "⌃").replace(/Shift\+/g, "⇧").replace(/Alt\+/g, "⌥").replace(/Cmd\+/g, "⌘")
}

// ── JSON 导出 ──
const jsonOutput = computed(() => {
  return JSON.stringify(allBindings.value.map(b => ({
    key: b.key,
    command: b.command,
    when: b.when || "global",
  })), null, 2)
})
</script>

<template>
  <div class="keybindings-page h-full flex flex-col" style="background: var(--color-ide-bg); color: var(--color-ide-text);">
    <!-- ═══ Header ═══ -->
    <div class="flex items-center gap-3 px-4 h-12 shrink-0" style="border-bottom: 1px solid var(--color-ide-border);">
      <Keyboard :size="16" style="color: var(--color-ide-accent);" />
      <span class="text-[14px] font-semibold">键盘快捷方式</span>

      <div class="flex-1" />

      <!-- 搜索框 -->
      <div class="flex items-center gap-1 border rounded-[3px] overflow-hidden"
        :style="{ background: 'var(--color-chat-input-bg)', borderColor: searchQuery.trim() ? 'var(--color-ide-border-focus)' : 'transparent' }">
        <Search :size="13" class="ml-2" style="color: var(--color-ide-text-dim);" />
        <input
          v-model="searchQuery"
          type="text"
          class="flex-1 h-7 bg-transparent text-[12px] outline-none px-1.5 w-48"
          placeholder="搜索快捷键或命令..."
        />
        <button v-if="searchQuery" class="shrink-0 w-6 h-7 flex items-center justify-center"
          @click="searchQuery = ''">
          <X :size="11" style="color: var(--color-ide-text-dim);" />
        </button>
      </div>

      <!-- 视图切换 -->
      <button
        class="flex items-center gap-1 px-2 h-7 rounded-[3px] text-[11px] font-medium transition-colors hover:bg-[var(--color-ide-surface-hover)]"
        :style="{ color: viewMode === 'table' ? 'var(--color-ide-accent)' : 'var(--color-ide-text-dim)' }"
        @click="viewMode = 'table'"
      >
        <SplitSquareVertical :size="12" /> 表格
      </button>
      <button
        class="flex items-center gap-1 px-2 h-7 rounded-[3px] text-[11px] font-medium transition-colors hover:bg-[var(--color-ide-surface-hover)]"
        :style="{ color: viewMode === 'json' ? 'var(--color-ide-accent)' : 'var(--color-ide-text-dim)' }"
        @click="viewMode = 'json'"
      >
        <FileJson :size="12" /> JSON
      </button>

      <!-- 冲突筛选 -->
      <button
        class="flex items-center gap-1 px-2 h-7 rounded-[3px] text-[11px] font-medium transition-colors hover:bg-[var(--color-ide-surface-hover)]"
        :style="{ color: showConflicts ? 'var(--color-ide-error)' : 'var(--color-ide-text-dim)' }"
        @click="showConflicts = !showConflicts"
      >
        <AlertTriangle :size="12" /> 冲突
      </button>
    </div>

    <!-- ═══ 分类筛选 ═══ -->
    <div class="flex items-center gap-1 px-4 h-8 shrink-0 overflow-x-auto" style="border-bottom: 1px solid var(--color-ide-border);">
      <button
        class="shrink-0 px-2.5 h-6 rounded-[3px] text-[11px] font-medium transition-colors"
        :class="!selectedCategory ? 'text-[var(--color-ide-text)] bg-[var(--color-ide-surface-active)]' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)]'"
        @click="selectedCategory = null"
      >
        全部
      </button>
      <button
        v-for="cat in categories"
        :key="cat"
        class="shrink-0 px-2.5 h-6 rounded-[3px] text-[11px] font-medium transition-colors"
        :class="selectedCategory === cat ? 'text-[var(--color-ide-text)] bg-[var(--color-ide-surface-active)]' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)]'"
        @click="selectedCategory = cat"
      >
        {{ cat }}
      </button>
    </div>

    <!-- ═══ 内容区 ═══ -->
    <div class="flex-1 overflow-hidden min-h-0">
      <!-- 表格视图 -->
      <div v-if="viewMode === 'table'" class="h-full overflow-y-auto">
        <template v-if="filteredBindings.length === 0">
          <div class="flex flex-col items-center justify-center py-20 gap-2">
            <Keyboard :size="28" style="color: var(--color-ide-text-dim); opacity: 0.2;" />
            <span class="text-[12px]" style="color: var(--color-ide-text-dim);">没有匹配的快捷键</span>
          </div>
        </template>

        <template v-else>
          <div v-for="[cat, bindings] in groupedByCategory" :key="cat">
            <!-- 分类标题 -->
            <div class="sticky top-0 z-10 flex items-center gap-2 px-4 h-7 text-[11px] font-semibold uppercase tracking-wider"
              style="background: var(--color-ide-bg-secondary); border-bottom: 1px solid var(--color-ide-border); color: var(--color-ide-text-dim);">
              {{ cat }}
              <span class="font-normal opacity-50">({{ bindings.length }})</span>
            </div>

            <!-- 快捷键行 -->
            <div
              v-for="b in bindings"
              :key="b.id"
              class="keybinding-row flex items-center gap-3 px-4 h-8 text-[12px] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
              :class="{
                'border-l-2 border-green-500': b.source === 'user' && !conflictMap.get(b.id),
                'border-l-2 border-[var(--color-ide-error)] bg-[var(--color-ide-error)]/5': conflictMap.get(b.id) && showConflicts,
              }"
            >
              <!-- 命令名 -->
              <span class="flex-1 truncate font-medium" style="color: var(--color-ide-text);">
                {{ b.description || b.command }}
              </span>
              <span class="w-32 truncate text-[11px] font-mono" style="color: var(--color-ide-text-dim);">
                {{ b.command.split(".").slice(-2).join(".") }}
              </span>
              <!-- 快捷键 -->
              <div class="w-36 shrink-0 relative">
                <div
                  v-if="editingKey === b.id"
                  class="flex items-center gap-1 px-2 h-6 rounded-[3px] border"
                  :style="{
                    background: 'var(--color-ide-surface-active)',
                    borderColor: 'var(--color-ide-border-focus)',
                    color: 'var(--color-ide-accent)',
                  }"
                >
                  <span v-if="!recordingKey" class="text-[10px] animate-pulse">按下快捷键...</span>
                  <span v-else class="text-[11px] font-mono font-bold">{{ recordingKey }}</span>
                </div>
                <!-- 普通显示 -->
                <div
                  v-else
                  class="group flex items-center justify-between px-2 h-6 rounded-[3px] cursor-pointer hover:bg-[var(--color-ide-surface-active)] transition-colors"
                  :class="{
                    'text-[var(--color-ide-error)]': conflictMap.get(b.id),
                    'text-[var(--color-ide-text-dim)]': !conflictMap.get(b.id),
                  }"
                  @click="editKey(b.id)"
                >
                  <span class="text-[11px] font-mono font-bold">{{ b.key }}</span>
                  <!-- hover 操作 -->
                  <div class="hidden group-hover:flex items-center gap-0.5">
                    <button
                      class="w-5 h-5 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-surface-hover)]"
                      title="编辑"
                      @click.stop="startRecording(b.id)"
                    >
                      <Pencil :size="10" />
                    </button>
                    <button
                      v-if="b.source === 'user'"
                      class="w-5 h-5 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-surface-hover)]"
                      title="重置为默认"
                      @click.stop="resetKey(b.id)"
                    >
                      <Undo2 :size="10" />
                    </button>
                    <button
                      class="w-5 h-5 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-surface-hover)]"
                      title="复制命令ID"
                      @click.stop="navigator.clipboard.writeText(b.command)"
                    >
                      <Copy :size="10" />
                    </button>
                  </div>
                </div>
              </div>
              <!-- when 条件 -->
              <span class="w-20 shrink-0 text-[10px] px-1.5 py-0.5 rounded-full text-center font-medium"
                :style="{
                  background: 'var(--color-ide-surface-active)',
                  color: 'var(--color-ide-text-dim)',
                }"
              >{{ b.when || 'global' }}</span>
              <!-- 来源 -->
              <span class="w-16 shrink-0 text-right text-[10px]"
                :class="b.source === 'user' ? 'text-[var(--color-ide-success)]' : 'text-[var(--color-ide-text-dim)]'"
              >{{ b.source === 'user' ? '用户' : '默认' }}</span>
            </div>
          </div>
        </template>
      </div>

      <!-- JSON 视图 -->
      <div v-else class="h-full p-4 overflow-y-auto">
        <pre class="text-[11px] font-mono leading-relaxed whitespace-pre"
          style="color: var(--color-ide-text);">{{ jsonOutput }}</pre>
      </div>
    </div>

    <!-- ═══ 底部状态栏 ═══ -->
    <div class="flex items-center justify-between px-4 h-7 shrink-0 text-[11px]"
      style="border-top: 1px solid var(--color-ide-border); background: var(--color-ide-bg-secondary); color: var(--color-ide-text-dim);">
      <span>{{ filteredBindings.length }} / {{ allBindings.length }} 个快捷键</span>
      <span class="text-[10px] opacity-50">双击快捷键可编辑 · Esc 取消录制 · keybindings.json</span>
    </div>

    <!-- 录制覆盖层提示 -->
    <div
      v-if="editingKey"
      class="fixed inset-0 z-[500] bg-black/60 flex items-center justify-center"
      @click="editingKey = null"
    >
      <div class="rounded-lg p-8 shadow-2xl text-center"
        style="background: var(--color-ide-surface); border: 1px solid var(--color-ide-border);">
        <Keyboard :size="32" class="mx-auto mb-3" style="color: var(--color-ide-accent);" />
        <p class="text-[14px] font-bold mb-1" style="color: var(--color-ide-text);">按下所需的组合键</p>
        <p class="text-[11px] mb-3" style="color: var(--color-ide-text-dim);">然后按 Enter 确认</p>
        <div class="inline-flex items-center gap-1 px-4 py-2 rounded-md border text-lg font-mono font-bold"
          :class="recordingKey ? 'text-[var(--color-ide-accent)]' : 'text-[var(--color-ide-text-dim)] animate-pulse'"
          :style="{
            background: 'var(--color-ide-bg)',
            borderColor: recordingKey ? 'var(--color-ide-border-focus)' : 'var(--color-ide-border)',
          }">
          {{ recordingKey || "等待按键..." }}
        </div>
        <p class="mt-3 text-[10px] opacity-40" style="color: var(--color-ide-text-dim);">Esc 取消</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.keybinding-row {
  border-bottom: 1px solid transparent;
}
.keybinding-row:hover {
  border-bottom-color: var(--color-ide-border);
}
</style>
