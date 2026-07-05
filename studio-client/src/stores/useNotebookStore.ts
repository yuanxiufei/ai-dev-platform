/**
 * useNotebookStore.ts — Notebook 支持 Store
 *
 * 借鉴: VSCode workbench/contrib/notebook/
 *
 * 能力:
 *   - Cell 的增删改查
 *   - Code/Markdown 双模式
 *   - Cell 执行状态
 *   - 输出缓存
 */
import { ref, computed } from 'vue'

export interface NotebookCell {
  id: string
  type: 'code' | 'markdown'
  content: string
  output?: string
  language?: string
  status: 'idle' | 'running' | 'done' | 'error'
  collapsed?: boolean
}

export interface Notebook {
  id: string
  name: string
  cells: NotebookCell[]
  filePath?: string
  kernel?: string
}

export const useNotebookStore = () => {
  const notebooks = ref<Notebook[]>([])
  const activeNotebookId = ref<string | null>(null)
  const activeCellId = ref<string | null>(null)
  const isRunning = ref(false)

  const activeNotebook = computed(() =>
    notebooks.value.find(n => n.id === activeNotebookId.value) ?? null
  )

  const cellCount = computed(() => activeNotebook.value?.cells.length ?? 0)

  function createNotebook(name: string, kernel?: string): Notebook {
    const nb: Notebook = {
      id: `nb-${Date.now()}`, name, kernel: kernel || 'python3',
      cells: [{ id: `cell-${Date.now()}`, type: 'code', content: '', status: 'idle' }],
    }
    notebooks.value.push(nb)
    activeNotebookId.value = nb.id
    return nb
  }

  function openNotebook(id: string): void {
    activeNotebookId.value = id
  }

  function addCell(type: 'code' | 'markdown' = 'code', afterId?: string): NotebookCell {
    const nb = activeNotebook.value
    if (!nb) throw new Error('No active notebook')
    const cell: NotebookCell = {
      id: `cell-${Date.now()}-${Math.random().toString(36).slice(2,6)}`,
      type, content: '', status: 'idle', language: nb.kernel?.startsWith('python') ? 'python' : 'javascript',
    }
    if (afterId) {
      const idx = nb.cells.findIndex(c => c.id === afterId)
      if (idx >= 0) nb.cells.splice(idx + 1, 0, cell)
      else nb.cells.push(cell)
    } else {
      nb.cells.push(cell)
    }
    return cell
  }

  function removeCell(cellId: string): void {
    const nb = activeNotebook.value
    if (!nb) return
    nb.cells = nb.cells.filter(c => c.id !== cellId)
  }

  function moveCell(cellId: string, direction: 'up' | 'down'): void {
    const nb = activeNotebook.value
    if (!nb) return
    const idx = nb.cells.findIndex(c => c.id === cellId)
    if (idx < 0) return
    const newIdx = direction === 'up' ? idx - 1 : idx + 1
    if (newIdx < 0 || newIdx >= nb.cells.length) return
    const [cell] = nb.cells.splice(idx, 1)
    nb.cells.splice(newIdx, 0, cell)
  }

  function updateCellContent(cellId: string, content: string): void {
    const nb = activeNotebook.value
    if (!nb) return
    const cell = nb.cells.find(c => c.id === cellId)
    if (cell) cell.content = content
  }

  function toggleCellType(cellId: string): void {
    const nb = activeNotebook.value
    if (!nb) return
    const cell = nb.cells.find(c => c.id === cellId)
    if (cell) cell.type = cell.type === 'code' ? 'markdown' : 'code'
  }

  async function executeCell(cellId: string): Promise<void> {
    const nb = activeNotebook.value
    if (!nb) return
    const cell = nb.cells.find(c => c.id === cellId)
    if (!cell || cell.type !== 'code') return
    cell.status = 'running'
    isRunning.value = true

    try {
      const baseUrl = (window as any).__apiBaseUrl || '/api/v1'
      const resp = await fetch(`${baseUrl}/system/notebook/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code: cell.content,
          kernel: nb.kernel || 'python3',
          cell_id: cellId,
          timeout: 30,
        }),
      })
      const data = await resp.json()
      if (data.success) {
        cell.output = data.output || '(无输出)'
        cell.status = 'done'
      } else {
        cell.output = data.error || data.output || '执行失败'
        cell.status = 'error'
      }
    } catch (e: any) {
      cell.output = `执行错误: ${e.message || e}`
      cell.status = 'error'
    } finally {
      isRunning.value = false
    }
  }

  async function executeAll(): Promise<void> {
    const nb = activeNotebook.value
    if (!nb) return
    for (const cell of nb.cells) {
      if (cell.type === 'code' && cell.content.trim()) {
        await executeCell(cell.id)
      }
    }
  }

  function clearOutputs(): void {
    const nb = activeNotebook.value
    if (!nb) return
    for (const cell of nb.cells) {
      cell.output = undefined
      cell.status = 'idle'
    }
  }

  function closeNotebook(id: string): void {
    notebooks.value = notebooks.value.filter(n => n.id !== id)
    if (activeNotebookId.value === id) {
      activeNotebookId.value = notebooks.value[0]?.id ?? null
    }
  }

  return {
    notebooks, activeNotebookId, activeCellId, isRunning,
    activeNotebook, cellCount,
    createNotebook, openNotebook, addCell, removeCell, moveCell,
    updateCellContent, toggleCellType, executeCell, executeAll,
    clearOutputs, closeNotebook,
  }
}
