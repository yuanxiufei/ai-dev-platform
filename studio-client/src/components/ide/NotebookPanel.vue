<script setup lang="ts">
/**
 * NotebookPanel.vue — Jupyter Notebook 风格交互式编程面板
 *
 * 借鉴: VSCode workbench/contrib/notebook/ (轻量版)
 *
 * 能力:
 *   - Code/Markdown Cell 切换
 *   - 逐 Cell 或全部执行
 *   - 输出区域 (可折叠)
 *   - 增/删/移动 Cell
 *   - 键盘快捷键 (Shift+Enter 执行)
 */
import { Play, Plus, Trash2, ChevronUp, ChevronDown, Code, FileText, Save, RefreshCw, Terminal, Copy, X } from 'lucide-vue-next'
import { computed, nextTick, ref, watch } from 'vue'
import { useNotebookStore, type NotebookCell } from '@/stores/useNotebookStore'
import { useIDEStore } from '@/stores/useIDEStore'

const nbStore = useNotebookStore()
const ideStore = useIDEStore()

const newNotebookName = ref('')
const showCreateDialog = ref(false)

const nb = computed(() => nbStore.activeNotebook)

function handleCreate(): void {
  if (!newNotebookName.value.trim()) return
  nbStore.createNotebook(newNotebookName.value.trim(), 'python3')
  newNotebookName.value = ''
  showCreateDialog.value = false
}

function onCellKeydown(e: KeyboardEvent, cell: NotebookCell): void {
  if (e.key === 'Enter' && e.shiftKey) {
    e.preventDefault()
    nbStore.executeCell(cell.id)
  } else if (e.key === 'Enter' && e.ctrlKey) {
    e.preventDefault()
    const newCell = nbStore.addCell('code', cell.id)
    nbStore.activeCellId = newCell.id
    nextTick(() => {
      const el = document.querySelector(`[data-cell-id="${newCell.id}"] textarea`)
      if (el) (el as HTMLElement).focus()
    })
  }
}

function getCellStatusColor(status: string): string {
  return { idle: 'transparent', running: '#f0ad4e', done: '#5cb85c', error: '#d9534f' }[status] || 'transparent'
}
</script>

<template>
  <div class="notebook-panel flex flex-col h-full" style="background:var(--color-ide-surface); color:var(--color-ide-text)">
    <!-- Header -->
    <div class="shrink-0 flex items-center px-3 h-9 gap-2" style="border-bottom:1px solid var(--color-ide-border)">
      <Terminal :size="14" style="color:var(--color-ide-accent)" />
      <span class="text-[12px] font-semibold uppercase tracking-wider">Notebook</span>
      <span v-if="nb" class="text-[11px] truncate" style="color:var(--color-ide-text-dim)">{{ nb.name }}</span>
      <div class="flex-1" />
      <button v-if="nb" class="nb-toolbar-btn" title="执行全部" @click="nbStore.executeAll()" :disabled="nbStore.isRunning">
        <Play :size="11" /> 全部
      </button>
      <button v-if="nb" class="nb-toolbar-btn" title="清除输出" @click="nbStore.clearOutputs()">
        <RefreshCw :size="11" />
      </button>
      <button v-if="nb" class="nb-toolbar-btn" title="添加代码Cell" @click="nbStore.addCell('code')">
        <Plus :size="12" /> 代码
      </button>
      <button v-if="nb" class="nb-toolbar-btn" title="添加Markdown Cell" @click="nbStore.addCell('markdown')">
        <FileText :size="12" /> MD
      </button>
      <button class="nb-toolbar-btn" title="新建Notebook" @click="showCreateDialog = !showCreateDialog">
        <Plus :size="12" /> 新建
      </button>
    </div>

    <!-- Create dialog -->
    <div v-if="showCreateDialog" class="shrink-0 flex items-center gap-2 px-3 py-2" style="border-bottom:1px solid var(--color-ide-border); background:var(--color-ide-bg-secondary)">
      <input v-model="newNotebookName" type="text"
        class="flex-1 h-7 px-2 rounded text-[12px] outline-none"
        :style="{background:'var(--color-editor-bg)', color:'var(--color-ide-text)', border:'1px solid var(--color-ide-border)'}"
        placeholder="Notebook 名称 (如: analysis.ipynb)"
        @keydown.enter="handleCreate" />
      <button class="nb-btn primary" @click="handleCreate">创建</button>
      <button class="nb-btn" @click="showCreateDialog=false">取消</button>
    </div>

    <!-- Notebook list (when no active notebook) -->
    <div v-if="!nb" class="flex-1 overflow-y-auto py-2">
      <div v-if="nbStore.notebooks.length === 0 && !showCreateDialog" class="flex flex-col items-center justify-center py-16" style="color:var(--color-ide-text-dim)">
        <Terminal :size="32" class="mb-3 opacity-20" />
        <p class="text-[13px]">没有打开的 Notebook</p>
        <p class="text-[11px] opacity-50 mt-1 mb-3">创建交互式计算文档</p>
        <button class="nb-btn primary" @click="showCreateDialog = true">创建 Notebook</button>
      </div>
      <div v-for="notebook in nbStore.notebooks" :key="notebook.id"
        class="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-[var(--color-ide-surface-hover)] transition-colors"
        @click="nbStore.openNotebook(notebook.id)">
        <Terminal :size="12" style="color:var(--color-ide-accent)" />
        <span class="flex-1 text-[12px]">{{ notebook.name }}</span>
        <span class="text-[10px] opacity-50" style="color:var(--color-ide-text-dim)">{{ notebook.cells.length }} cells</span>
        <button class="nb-toolbar-btn" @click.stop="nbStore.closeNotebook(notebook.id)"><X :size="11" /></button>
      </div>
    </div>

    <!-- Cell list -->
    <div v-else class="flex-1 overflow-y-auto">
      <div v-for="(cell, idx) in nb.cells" :key="cell.id" :data-cell-id="cell.id"
        class="nb-cell" :class="{ 'nb-cell-active': nbStore.activeCellId === cell.id }"
        @click="nbStore.activeCellId = cell.id">
        <!-- Cell toolbar -->
        <div class="flex items-center gap-1 px-3 py-1" style="border-bottom:1px solid var(--color-ide-border); min-height:24px">
          <div class="w-2 h-2 rounded-full shrink-0" :style="{ background: getCellStatusColor(cell.status) }" />
          <span class="text-[10px] uppercase tracking-wider font-semibold" style="color:var(--color-ide-text-dim)">
            {{ cell.type === 'code' ? `[${idx + 1}]` : 'MD' }}
          </span>
          <span v-if="cell.type==='code' && cell.language" class="text-[9px] opacity-40" style="color:var(--color-ide-text-dim)">{{ cell.language }}</span>
          <div class="flex-1" />
          <button class="nb-cell-btn" title="执行 (Shift+Enter)" @click="nbStore.executeCell(cell.id)" :disabled="cell.status==='running'">
            <Play :size="10" />
          </button>
          <button class="nb-cell-btn" title="切换类型" @click="nbStore.toggleCellType(cell.id)">
            {{ cell.type === 'code' ? 'MD' : '&lt;/&gt;' }}
          </button>
          <button class="nb-cell-btn" title="上移" @click="nbStore.moveCell(cell.id, 'up')"><ChevronUp :size="10" /></button>
          <button class="nb-cell-btn" title="下移" @click="nbStore.moveCell(cell.id, 'down')"><ChevronDown :size="10" /></button>
          <button class="nb-cell-btn" title="删除" @click="nbStore.removeCell(cell.id)"><Trash2 :size="10" /></button>
        </div>
        <!-- Cell content -->
        <div class="px-3 py-2">
          <textarea v-if="cell.type === 'code'"
            :value="cell.content"
            @input="nbStore.updateCellContent(cell.id, ($event.target as HTMLTextAreaElement).value)"
            @keydown="onCellKeydown($event, cell)"
            class="nb-cell-input w-full font-mono text-[13px] outline-none resize-none rounded p-2"
            :style="{background:'var(--color-editor-bg)', color:'var(--color-ide-text)', border:'1px solid var(--color-ide-border)', minHeight:'36px'}"
            :placeholder="cell.type==='code' ? '输入代码... (Shift+Enter 执行)' : '输入 Markdown...'"
            rows="3" spellcheck="false" />
          <textarea v-else
            :value="cell.content"
            @input="nbStore.updateCellContent(cell.id, ($event.target as HTMLTextAreaElement).value)"
            class="nb-cell-input w-full text-[13px] outline-none resize-none rounded p-2"
            :style="{background:'var(--color-editor-bg)', color:'var(--color-ide-text)', border:'1px solid var(--color-ide-border)', minHeight:'24px'}"
            placeholder="输入 Markdown..."
            rows="2" spellcheck="false" />
        </div>
        <!-- Cell output -->
        <div v-if="cell.output" class="px-3 pb-2">
          <div class="nb-cell-output rounded p-2 font-mono text-[12px] whitespace-pre-wrap" style="background:var(--color-ide-bg-secondary); max-height:200px; overflow:auto">
            {{ cell.output }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.nb-toolbar-btn {
  display: flex; align-items: center; gap: 3px;
  font-size: 11px; padding: 2px 6px; border-radius: 3px;
  color: var(--color-ide-text-dim);
  transition: all 0.1s;
}
.nb-toolbar-btn:hover { background: var(--color-ide-surface-hover); color: var(--color-ide-text); }
.nb-cell { border-bottom: 1px solid var(--color-ide-border); }
.nb-cell-active { background: color-mix(in srgb, var(--color-ide-accent) 3%, transparent); }
.nb-cell-btn {
  display: flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; border-radius: 2px;
  color: var(--color-ide-text-dim); font-size: 9px;
  transition: all 0.1s;
}
.nb-cell-btn:hover { background: var(--color-ide-surface-hover); color: var(--color-ide-text); }
.nb-btn {
  font-size: 11px; padding: 3px 10px; border-radius: 3px;
  color: var(--color-ide-text); background: var(--color-ide-surface-hover);
}
.nb-btn.primary { background: var(--color-ide-accent); color: #fff; }
.nb-cell-input:focus { border-color: var(--color-ide-accent) !important; }
</style>
