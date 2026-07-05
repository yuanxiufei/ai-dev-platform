/**
 * useCallHierarchyStore.ts — 调用层次结构 Store
 *
 * 借鉴: VSCode workbench/contrib/callHierarchy/
 * Session 50: 对接 /system/hierarchy/call/* 后端 API，
 * 替换 JS 正则 hack 为 CodebaseMemory 图查询 + AST 分析
 */
import { ref, computed } from 'vue'

export interface CallHierarchyItem {
  name: string
  kind: 'function' | 'method' | 'constructor' | 'arrow' | 'class' | 'variable'
  file: string
  line: number
  column: number
  detail?: string
  children?: CallHierarchyItem[]
  parentCount?: number
}

function getApiBase(): string {
  return (window as any).__apiBaseUrl || '/api/v1'
}

function apiItemToStore(item: any): CallHierarchyItem {
  return {
    name: item.name || item.from_item?.name || item.to_item?.name || '',
    kind: (item.kind || 'function') as CallHierarchyItem['kind'],
    file: item.uri || item.from_item?.uri || item.to_item?.uri || '',
    line: item.range?.start_line || item.from_item?.range?.start_line || item.to_item?.range?.start_line || item.from_ranges?.[0]?.start_line || 0,
    column: item.range?.start_column || item.from_item?.range?.start_column || item.to_item?.range?.start_column || 1,
    detail: item.detail || item.from_item?.detail || item.to_item?.detail || '',
    children: [],
    parentCount: 0,
  }
}

export const useCallHierarchyStore = () => {
  const incomingCalls = ref<CallHierarchyItem[]>([])
  const outgoingCalls = ref<CallHierarchyItem[]>([])
  const currentSymbol = ref<string>('')
  const isLoading = ref(false)
  const provider = ref<string>('none')  // codebase-memory / regex-fallback / none

  const callTree = computed(() => ({
    incoming: incomingCalls.value,
    outgoing: outgoingCalls.value,
  }))

  function setCurrentSymbol(name: string): void {
    currentSymbol.value = name
  }

  /** Session 50: 使用后端 API 替代 JS 正则 hack */
  async function fetchCallHierarchy(symbolName: string, content: string, language: string, projectPath: string = '.'): Promise<void> {
    isLoading.value = true
    currentSymbol.value = symbolName

    try {
      const baseUrl = getApiBase()
      const [incResp, outResp] = await Promise.all([
        fetch(`${baseUrl}/system/hierarchy/call/incoming`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ symbol_name: symbolName, content, language, project_path: projectPath }),
        }),
        fetch(`${baseUrl}/system/hierarchy/call/outgoing`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ symbol_name: symbolName, content, language, project_path: projectPath }),
        }),
      ])
      const incData = await incResp.json()
      const outData = await outResp.json()

      provider.value = incData.provider || outData.provider || 'none'
      incomingCalls.value = (incData.incoming_calls || []).map((c: any) => apiItemToStore(c))
      outgoingCalls.value = (outData.outgoing_calls || []).map((c: any) => apiItemToStore(c))
    } catch {
      incomingCalls.value = []
      outgoingCalls.value = []
    } finally {
      isLoading.value = false
    }
  }

  /** 兼容旧调用：纯文本解析作为回退 */
  function parseCallHierarchy(code: string, symbolName: string, language: string): void {
    fetchCallHierarchy(symbolName, code, language)
  }

  function clear(): void {
    incomingCalls.value = []
    outgoingCalls.value = []
    currentSymbol.value = ''
  }

  return {
    incomingCalls, outgoingCalls, currentSymbol, isLoading, callTree, provider,
    setCurrentSymbol, parseCallHierarchy, fetchCallHierarchy, clear,
  }
}
