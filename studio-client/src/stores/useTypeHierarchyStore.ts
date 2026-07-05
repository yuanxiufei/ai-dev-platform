/**
 * useTypeHierarchyStore.ts — 类型层次结构 Store
 *
 * 借鉴: VSCode workbench/contrib/typeHierarchy/
 * Session 50: 对接 /system/hierarchy/type/* 后端 API，
 * 替换 JS 正则 hack 为 CodebaseMemory INHERITS 边查询 + AST 分析
 */
import { ref, computed } from 'vue'

export interface TypeHierarchyItem {
  name: string
  kind: 'class' | 'interface' | 'enum' | 'type'
  file: string
  line: number
  detail?: string
  children: TypeHierarchyItem[]
}

function getApiBase(): string {
  return (window as any).__apiBaseUrl || '/api/v1'
}

function apiItemToStore(item: any): TypeHierarchyItem {
  return {
    name: item.name || '',
    kind: (item.kind === 'interface' ? 'interface' : item.kind === 'enum' ? 'enum' : 'class') as TypeHierarchyItem['kind'],
    file: item.uri || '',
    line: item.range?.start_line || 0,
    detail: item.detail || '',
    children: [],
  }
}

export const useTypeHierarchyStore = () => {
  const superTypes = ref<TypeHierarchyItem[]>([])
  const subTypes = ref<TypeHierarchyItem[]>([])
  const currentType = ref<string>('')
  const isLoading = ref(false)
  const provider = ref<string>('none')

  const typeTree = computed(() => ({ superTypes: superTypes.value, subTypes: subTypes.value }))

  function setCurrentType(name: string): void {
    currentType.value = name
  }

  /** Session 50: 使用后端 API 替代 JS 正则 hack */
  async function fetchTypeHierarchy(typeName: string, content: string, language: string, projectPath: string = '.'): Promise<void> {
    isLoading.value = true
    currentType.value = typeName

    try {
      const baseUrl = getApiBase()
      const [supResp, subResp] = await Promise.all([
        fetch(`${baseUrl}/system/hierarchy/type/supertypes`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ symbol_name: typeName, content, language, project_path: projectPath }),
        }),
        fetch(`${baseUrl}/system/hierarchy/type/subtypes`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ symbol_name: typeName, content, language, project_path: projectPath }),
        }),
      ])
      const supData = await supResp.json()
      const subData = await subResp.json()

      provider.value = supData.provider || subData.provider || 'none'
      superTypes.value = (supData.supertypes || []).map((s: any) => apiItemToStore(s))
      subTypes.value = (subData.subtypes || []).map((s: any) => apiItemToStore(s))
    } catch {
      superTypes.value = []
      subTypes.value = []
    } finally {
      isLoading.value = false
    }
  }

  /** 兼容旧调用 */
  function parseTypeHierarchy(code: string, typeName: string, language: string): void {
    fetchTypeHierarchy(typeName, code, language)
  }

  function clear(): void {
    superTypes.value = []
    subTypes.value = []
    currentType.value = ''
  }

  return {
    superTypes, subTypes, currentType, isLoading, typeTree, provider,
    setCurrentType, parseTypeHierarchy, fetchTypeHierarchy, clear,
  }
}
