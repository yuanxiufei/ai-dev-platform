<script setup lang="ts">
/**
 * SnippetsPanel — VSCode 对标代码片段管理器
 *
 * Session 35: 用户自定义 Snippets 管理 + Monaco 补全集成
 */
import { ref, computed } from "vue"
import { useSnippetsStore, type Snippet } from "@/stores/useSnippetsStore"
import {
  Plus, Trash2, Pencil, FileJson, Upload, Download,
  Search, X, Code2, Copy, Check, Sparkles, Insert,
} from "lucide-vue-next"

const store = useSnippetsStore()

const searchQuery = ref("")
const selectedLanguage = ref<string>("all")
const editingId = ref<string | null>(null)
const jsonImport = ref("")
const showJsonDialog = ref(false)
const copiedId = ref<string | null>(null)
/** Session 42: InsertSnippet 命令面板 */
const showInsertDialog = ref(false)
const insertQuery = ref("")

// 编辑表单
const editForm = ref({
  prefix: "",
  name: "",
  description: "",
  body: "",
  language: "" as string | undefined,
})

/** 过滤后的 snippets */
const filteredSnippets = computed(() => {
  let list = store.snippets
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(s =>
      s.prefix.toLowerCase().includes(q) ||
      s.name.toLowerCase().includes(q) ||
      s.description.toLowerCase().includes(q)
    )
  }
  if (selectedLanguage.value !== "all") {
    if (selectedLanguage.value === "global") {
      list = list.filter(s => !s.language)
    } else {
      list = list.filter(s => s.language === selectedLanguage.value)
    }
  }
  return list.sort((a, b) => b.createdAt - a.createdAt)
})

/** 所有可以筛选的语言 */
const allLanguages = computed(() => {
  const langs = new Set(store.languages)
  return [
    { id: "all", label: "全部" },
    { id: "global", label: "全局" },
    ...Array.from(langs).filter(l => l !== "global").map(l => ({ id: l, label: l })),
  ]
})

function startEdit(snippet?: Snippet): void {
  if (snippet) {
    editingId.value = snippet.id
    editForm.value = {
      prefix: snippet.prefix,
      name: snippet.name,
      description: snippet.description,
      body: snippet.body,
      language: snippet.language,
    }
  } else {
    editingId.value = "new"
    editForm.value = {
      prefix: "",
      name: "",
      description: "",
      body: "",
      language: undefined,
    }
  }
}

function cancelEdit(): void {
  editingId.value = null
}

function saveEdit(): void {
  if (!editForm.value.prefix || !editForm.value.name || !editForm.value.body) return
  if (editingId.value === "new") {
    store.create({
      prefix: editForm.value.prefix,
      name: editForm.value.name,
      description: editForm.value.description,
      body: editForm.value.body,
      language: editForm.value.language || undefined,
    })
  } else if (editingId.value) {
    store.update(editingId.value, {
      prefix: editForm.value.prefix,
      name: editForm.value.name,
      description: editForm.value.description,
      body: editForm.value.body,
      language: editForm.value.language || undefined,
    })
  }
  editingId.value = null
}

function deleteSnippet(id: string): void {
  store.remove(id)
}

function copyBody(body: string, id: string): void {
  navigator.clipboard.writeText(body)
  copiedId.value = id
  setTimeout(() => { copiedId.value = null }, 2000)
}

function importJson(): void {
  try {
    const count = store.importSnippets(jsonImport.value)
    jsonImport.value = ""
    showJsonDialog.value = false
    alert(`成功导入 ${count} 个代码片段`)
  } catch {
    alert("JSON 格式无效，请检查后重试")
  }
}

function exportJson(): void {
  const json = store.exportSnippets()
  navigator.clipboard.writeText(json)
  alert("已复制到剪贴板")
}

/** Session 42: 插入片段到编辑器 */
function insertSnippet(snippet: Snippet): void {
  showInsertDialog.value = false
  // 通过全局事件将片段内容发送到编辑器
  const editorContent = snippet.body
  window.dispatchEvent(new CustomEvent('ide:insert-snippet', {
    detail: { body: editorContent, name: snippet.name, prefix: snippet.prefix }
  }))
}

/** 可插入的片段列表（过滤后） */
const insertableSnippets = computed(() => {
  if (!insertQuery.value.trim()) return store.snippets.slice(0, 8)
  const q = insertQuery.value.toLowerCase()
  return store.snippets.filter(s =>
    s.prefix.toLowerCase().includes(q) || s.name.toLowerCase().includes(q)
  ).slice(0, 8)
})
</script>

<template>
  <div class="snippets-panel h-full flex flex-col" 
    style="background: var(--color-ide-bg); color: var(--color-ide-text);">
    <!-- Header -->
    <div class="flex items-center gap-2 px-3 h-10 shrink-0" 
      style="border-bottom: 1px solid var(--color-ide-border);">
      <Code2 :size="16" style="color: var(--color-ide-accent);" />
      <span class="text-[13px] font-semibold">用户代码片段</span>
      <span class="text-[10px] opacity-50">({{ store.snippets.length }})</span>
      <div class="flex-1" />
      <!-- Session 42: 插入片段按钮 -->
      <button
        class="flex items-center gap-1 px-2 h-6 rounded-[3px] text-[11px] font-medium transition-colors"
        style="background: var(--color-ide-bg-secondary); color: var(--color-ide-accent);"
        @click="showInsertDialog = true"
        title="插入片段到编辑器 (Ctrl+Shift+J)"
      >
        <Insert :size="12" /> 插入
      </button>
      <button
        class="flex items-center gap-1 px-2 h-6 rounded-[3px] text-[11px] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
        style="color: var(--color-ide-text-dim);"
        @click="showJsonDialog = true"
        title="导入 JSON"
      >
        <Upload :size="12" /> 导入
      </button>
      <button
        class="flex items-center gap-1 px-2 h-6 rounded-[3px] text-[11px] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
        style="color: var(--color-ide-text-dim);"
        @click="exportJson"
        title="导出 JSON"
      >
        <Download :size="12" /> 导出
      </button>
      <button
        class="flex items-center gap-1 px-2 h-6 rounded-[3px] text-[11px] font-medium transition-colors"
        style="background: var(--color-ide-accent); color: #fff;"
        @click="startEdit()"
        title="新建片段"
      >
        <Plus :size="12" /> 新建
      </button>
    </div>

    <!-- Search & Filter -->
    <div class="flex items-center gap-1 px-3 h-8 shrink-0 overflow-x-auto"
      style="border-bottom: 1px solid var(--color-ide-border);">
      <div class="flex items-center border rounded-[3px] overflow-hidden flex-1 min-w-0"
        :style="{ background: 'var(--color-ide-surface-active)', borderColor: 'transparent' }">
        <Search :size="12" class="ml-2 shrink-0" style="color: var(--color-ide-text-dim);" />
        <input v-model="searchQuery" type="text" class="flex-1 h-6 bg-transparent text-[11px] outline-none px-1.5"
          placeholder="搜索代码片段..." />
        <button v-if="searchQuery" class="w-5 h-6 flex items-center justify-center shrink-0" @click="searchQuery = ''">
          <X :size="10" style="color: var(--color-ide-text-dim);" />
        </button>
      </div>
      <select v-model="selectedLanguage" class="h-6 rounded-[3px] text-[11px] px-1.5 outline-none shrink-0"
        style="background: var(--color-ide-surface-active); color: var(--color-ide-text-dim); border: none;">
        <option v-for="l in allLanguages" :key="l.id" :value="l.id">{{ l.label }}</option>
      </select>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto min-h-0">
      <!-- Edit Form -->
      <div v-if="editingId" class="p-3 space-y-2"
        style="border-bottom: 1px solid var(--color-ide-border); background: var(--color-ide-bg-secondary);">
        <div class="flex items-center gap-2">
          <input v-model="editForm.name" type="text" class="flex-1 h-7 px-2 rounded-[3px] text-[12px] outline-none"
            placeholder="名称 *" 
            :style="{ background: 'var(--color-ide-surface)', border: '1px solid var(--color-ide-border)', color: 'var(--color-ide-text)' }" />
          <input v-model="editForm.prefix" type="text" class="w-32 h-7 px-2 rounded-[3px] text-[12px] font-mono outline-none"
            placeholder="前缀 *" 
            :style="{ background: 'var(--color-ide-surface)', border: '1px solid var(--color-ide-border)', color: 'var(--color-ide-text)' }" />
          <input v-model="editForm.language" type="text" class="w-24 h-7 px-2 rounded-[3px] text-[12px] outline-none"
            placeholder="语言（可选）" 
            :style="{ background: 'var(--color-ide-surface)', border: '1px solid var(--color-ide-border)', color: 'var(--color-ide-text)' }" />
        </div>
        <input v-model="editForm.description" type="text" class="w-full h-7 px-2 rounded-[3px] text-[12px] outline-none"
          placeholder="描述（可选）"
          :style="{ background: 'var(--color-ide-surface)', border: '1px solid var(--color-ide-border)', color: 'var(--color-ide-text)' }" />
        <textarea v-model="editForm.body" 
          class="w-full rounded-[3px] p-2 text-[12px] font-mono outline-none resize-y"
          rows="5"
          placeholder="代码内容，支持 $1, $2... 作为制表位&#10;${1:name} — 具名占位符&#10;$0 — 最终光标位置"
          :style="{ background: 'var(--color-ide-surface)', border: '1px solid var(--color-ide-border)', color: 'var(--color-ide-text)', minHeight: '80px' }" />
        <!-- Session 42: TabStop 提示 -->
        <div class="flex items-center gap-2 text-[10px]" style="color: var(--color-ide-text-dim);">
          <Sparkles :size="10" style="color: var(--color-ide-accent);" />
          <span>使用 <code style="color: var(--color-ide-accent);">$1</code>, <code style="color: var(--color-ide-accent);">$2</code> 定义制表位，<code style="color: var(--color-ide-accent);">$0</code> 为最终位置</span>
        </div>
        <div class="flex items-center gap-2 justify-end">
          <button class="px-3 h-6 rounded-[3px] text-[11px] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
            style="color: var(--color-ide-text-dim);"
            @click="cancelEdit">取消</button>
          <button class="px-3 h-6 rounded-[3px] text-[11px] font-medium transition-colors"
            style="background: var(--color-ide-accent); color: #fff;"
            :disabled="!editForm.prefix || !editForm.name || !editForm.body"
            @click="saveEdit">保存</button>
        </div>
      </div>

      <!-- Snippet List -->
      <template v-if="filteredSnippets.length === 0">
        <div class="flex flex-col items-center justify-center py-16 gap-2">
          <Sparkles :size="28" style="color: var(--color-ide-text-dim); opacity: 0.2;" />
          <span class="text-[12px]" style="color: var(--color-ide-text-dim);">
            {{ searchQuery ? "没有匹配的代码片段" : "暂无代码片段，点击右上角「新建」" }}
          </span>
        </div>
      </template>

      <div v-for="s in filteredSnippets" :key="s.id" class="snippet-item flex items-start gap-2 px-3 py-2 group"
        style="border-bottom: 1px solid var(--color-ide-border);">
        <!-- Icon -->
        <div class="w-7 h-7 rounded-[3px] flex items-center justify-center shrink-0 mt-0.5"
          style="background: var(--color-ide-surface-active); color: var(--color-ide-accent);">
          <Code2 :size="13" />
        </div>
        <!-- Info -->
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-[12px] font-medium truncate" style="color: var(--color-ide-text);">{{ s.name }}</span>
            <span class="text-[10px] font-mono px-1.5 py-0.5 rounded-[2px]" 
              style="background: var(--color-ide-surface-active); color: var(--color-ide-accent);">{{ s.prefix }}</span>
            <span v-if="s.language" class="text-[10px] px-1 py-0.5 rounded-[2px]"
              style="background: var(--color-ide-bg-secondary); color: var(--color-ide-text-dim);">{{ s.language }}</span>
          </div>
          <p v-if="s.description" class="text-[11px] mt-0.5 truncate" style="color: var(--color-ide-text-dim);">
            {{ s.description }}
          </p>
          <pre class="text-[10px] font-mono mt-1 p-1.5 rounded-[3px] overflow-x-auto line-clamp-2"
            style="background: var(--color-ide-surface-active); color: var(--color-ide-text-dim); white-space: pre-wrap; word-break: break-all;">{{ s.body }}</pre>
        </div>
        <!-- Actions -->
        <div class="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
          <button class="w-6 h-6 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-surface-hover)]"
            :style="{ color: copiedId === s.id ? 'var(--color-ide-success)' : 'var(--color-ide-text-dim)' }"
            :title="copiedId === s.id ? '已复制' : '复制片段'"
            @click="copyBody(s.body, s.id)">
            <Check v-if="copiedId === s.id" :size="12" />
            <Copy v-else :size="12" />
          </button>
          <button class="w-6 h-6 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-surface-hover)]"
            style="color: var(--color-ide-text-dim);"
            title="编辑"
            @click="startEdit(s)">
            <Pencil :size="12" />
          </button>
          <button class="w-6 h-6 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-error)]/10"
            style="color: var(--color-ide-text-dim);"
            title="删除"
            @click="deleteSnippet(s.id)">
            <Trash2 :size="12" />
          </button>
        </div>
      </div>
    </div>

    <!-- JSON Import Dialog -->
    <div v-if="showJsonDialog" class="fixed inset-0 z-[500] bg-black/60 flex items-center justify-center"
      @click.self="showJsonDialog = false">
      <div class="rounded-lg p-6 w-[500px] shadow-2xl"
        style="background: var(--color-ide-surface); border: 1px solid var(--color-ide-border);">
        <div class="flex items-center gap-2 mb-3">
          <FileJson :size="16" style="color: var(--color-ide-accent);" />
          <span class="text-[14px] font-semibold" style="color: var(--color-ide-text);">导入代码片段 JSON</span>
        </div>
        <textarea v-model="jsonImport" class="w-full h-48 rounded-[3px] p-3 text-[11px] font-mono outline-none resize-none"
          placeholder='[{"prefix": "my", "name": "My Snippet", "description": "...", "body": "...", "language": "typescript"}]'
          :style="{ background: 'var(--color-ide-bg)', border: '1px solid var(--color-ide-border)', color: 'var(--color-ide-text)' }" />
        <div class="flex items-center justify-end gap-2 mt-3">
          <button class="px-3 h-7 rounded-[3px] text-[12px] transition-colors hover:bg-[var(--color-ide-surface-hover)]"
            style="color: var(--color-ide-text-dim);"
            @click="showJsonDialog = false">取消</button>
          <button class="px-3 h-7 rounded-[3px] text-[12px] font-medium transition-colors"
            style="background: var(--color-ide-accent); color: #fff;"
            @click="importJson">导入</button>
        </div>
      </div>
    </div>

    <!-- Session 42: 插入片段命令面板 -->
    <div v-if="showInsertDialog" class="fixed inset-0 z-[500] bg-black/60 flex items-center justify-center"
      @click.self="showInsertDialog = false">
      <div class="rounded-lg p-4 w-[480px] shadow-2xl"
        style="background: var(--color-ide-surface); border: 1px solid var(--color-ide-border);">
        <div class="flex items-center gap-2 mb-3 border-b pb-2" style="border-color: var(--color-ide-border);">
          <Search :size="14" style="color: var(--color-ide-text-dim);" />
          <input v-model="insertQuery" type="text" class="flex-1 bg-transparent text-[13px] outline-none"
            placeholder="搜索片段..." style="color: var(--color-ide-text);"
            @keydown.escape="showInsertDialog = false" />
          <span class="text-[10px]" style="color: var(--color-ide-text-dim);">Ctrl+Shift+J</span>
        </div>
        <div class="max-h-[320px] overflow-y-auto space-y-0.5">
          <div v-if="insertableSnippets.length === 0" class="text-center py-8 text-[12px]" style="color: var(--color-ide-text-dim);">
            无匹配片段
          </div>
          <button
            v-for="s in insertableSnippets"
            :key="s.id"
            class="w-full flex items-center gap-2 px-2 py-1.5 rounded-[3px] text-left transition-colors hover:bg-[var(--color-ide-surface-hover)]"
            @click="insertSnippet(s)"
          >
            <Code2 :size="12" style="color: var(--color-ide-accent);" class="shrink-0" />
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-1.5">
                <span class="text-[12px] font-medium truncate" style="color: var(--color-ide-text);">{{ s.name }}</span>
                <span class="text-[10px] font-mono px-1 rounded-[2px]" style="background: var(--color-ide-surface-active); color: var(--color-ide-accent);">{{ s.prefix }}</span>
              </div>
              <div class="text-[10px] truncate mt-0.5" style="color: var(--color-ide-text-dim);">{{ s.description || s.body.slice(0, 60) }}</div>
            </div>
            <Insert :size="12" class="shrink-0" style="color: var(--color-ide-text-dim);" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
