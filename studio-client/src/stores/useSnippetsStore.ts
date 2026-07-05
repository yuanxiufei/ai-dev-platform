/**
 * Snippets Store — VSCode 对标自定义代码片段管理
 *
 * Session 51: 后端 API 持久化 + localStorage 回退
 *   - localStorage 始终保留作为本地缓存
 *   - 后端 API 提供跨设备同步
 */
import { ref, computed, watch } from "vue"
import { defineStore } from "pinia"

export interface Snippet {
  id: string
  prefix: string
  name: string
  description: string
  body: string
  language?: string
  createdAt: number
  tags?: string[]
}

function getApiBase(): string { return (window as any).__apiBaseUrl || '/api/v1' }

const STORAGE_KEY = "codebuddy_snippets"

function load(): Snippet[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return []
}

function persist(snippets: Snippet[]): void {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(snippets)) } catch { /* ignore */ }
}

// 默认内置 snippets
const DEFAULT_SNIPPETS: Snippet[] = [
  {
    id: "builtin-vue3-comp",
    prefix: "vcomp",
    name: "Vue 3 Component",
    description: "新建 Vue 3 单文件组件",
    body: `<script setup lang="ts">
\n
</script>
\n
<template>
  <div class="$1">
    $2
  </div>
</template>
\n
<style scoped>
.$1 {
  $3
}
</style>`,
    language: "vue",
    createdAt: Date.now(),
  },
  {
    id: "builtin-ts-func",
    prefix: "tfunc",
    name: "TypeScript Function",
    description: "TypeScript 函数定义",
    body: `function $1($2): $3 {
  $4
}`,
    language: "typescript",
    createdAt: Date.now(),
  },
  {
    id: "builtin-ts-class",
    prefix: "tclass",
    name: "TypeScript Class",
    description: "TypeScript 类定义",
    body: `class $1 {
  constructor($2) {
    $3
  }
}`,
    language: "typescript",
    createdAt: Date.now(),
  },
  {
    id: "builtin-log",
    prefix: "clog",
    name: "Console Log",
    description: "控制台打印",
    body: `console.log("$1:", $1)`,
    language: undefined,
    createdAt: Date.now(),
  },
  {
    id: "builtin-if",
    prefix: "if",
    name: "If Statement",
    description: "条件语句",
    body: `if ($1) {
  $2
}`,
    language: undefined,
    createdAt: Date.now(),
  },
  {
    id: "builtin-py-func",
    prefix: "pfunc",
    name: "Python Function",
    description: "Python 函数定义",
    body: `def $1($2):
    """$3"""
    $4`,
    language: "python",
    createdAt: Date.now(),
  },
]

export const useSnippetsStore = defineStore("snippets", () => {
  const snippets = ref<Snippet[]>(load())

  // 首次初始化时加载默认 snippets
  if (snippets.value.length === 0) {
    snippets.value = [...DEFAULT_SNIPPETS]
    persist(snippets.value)
  }

  // 自动持久化
  watch(snippets, (v) => persist(v), { deep: true })

  /** 按语言分组 */
  const byLanguage = computed(() => {
    const map = new Map<string, Snippet[]>()
    for (const s of snippets.value) {
      const lang = s.language ?? "global"
      if (!map.has(lang)) map.set(lang, [])
      map.get(lang)!.push(s)
    }
    return map
  })

  /** 所有可用语言 */
  const languages = computed(() => Array.from(byLanguage.value.keys()).sort())

  /** 获取某语言的 snippets（含 global） */
  function getForLanguage(lang: string | undefined): Snippet[] {
    const result: Snippet[] = []
    for (const s of snippets.value) {
      if (!s.language || s.language === lang) {
        result.push(s)
      }
    }
    return result
  }

  /** Session 51: 创建 snippet → 同时写入后端 */
  async function create(snippet: Omit<Snippet, "id" | "createdAt">): Promise<Snippet> {
    const id = `snippet-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
    const s: Snippet = { ...snippet, id, createdAt: Date.now() }
    snippets.value.push(s)
    _syncCreateApi(snippet).catch(() => {})
    return s
  }

  /** Session 51: 更新 snippet → 同时更新后端 */
  async function update(id: string, partial: Partial<Omit<Snippet, "id" | "createdAt">>): Promise<void> {
    const s = snippets.value.find(s => s.id === id)
    if (s) {
      Object.assign(s, partial)
      _syncUpdateApi(id, partial).catch(() => {})
    }
  }

  /** Session 51: 删除 snippet → 同时删除后端 */
  async function remove(id: string): Promise<void> {
    const idx = snippets.value.findIndex(s => s.id === id)
    if (idx !== -1) {
      snippets.value.splice(idx, 1)
      _syncDeleteApi(id).catch(() => {})
    }
  }

  /** Session 51: 导入 snippets → 批量写后端 */
  async function importSnippets(json: string): Promise<number> {
    try {
      const imported: Omit<Snippet, "id" | "createdAt">[] = JSON.parse(json)
      let count = 0
      for (const item of imported) {
        await create(item); count++
      }
      _syncImportApi(imported).catch(() => {})
      return count
    } catch { throw new Error("无效的 JSON 格式") }
  }

  /** Session 51: 从后端 API 同步 snippets */
  async function syncFromApi(): Promise<void> {
    try {
      const resp = await fetch(`${getApiBase()}/system/snippets`)
      if (resp.ok) {
        const data = await resp.json()
        if (Array.isArray(data) && data.length > 0) {
          const apiSnippets: Snippet[] = data.map((s: any) => ({
            id: s.id, prefix: s.prefix, name: s.name,
            description: s.description, body: s.body,
            language: s.language || undefined,
            createdAt: Date.now(), tags: s.tags || [],
          }))
          // 合并：后端优先，保留本地新建但未同步的
          const localIds = new Set(snippets.value.map(s => s.id))
          for (const as of apiSnippets) {
            if (!localIds.has(as.id)) snippets.value.push(as)
          }
        }
      }
    } catch { /* API unavailable, use localStorage only */ }
  }

  // ── 后端 API 同步 ──

  async function _syncCreateApi(s: Omit<Snippet, "id" | "createdAt">): Promise<void> {
    await fetch(`${getApiBase()}/system/snippets`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prefix: s.prefix, name: s.name, description: s.description, body: s.body, language: s.language }),
    })
  }

  async function _syncUpdateApi(id: string, p: Record<string, any>): Promise<void> {
    const body: Record<string, any> = {}
    if (p.prefix !== undefined) body.prefix = p.prefix
    if (p.name !== undefined) body.name = p.name
    if (p.description !== undefined) body.description = p.description
    if (p.body !== undefined) body.body = p.body
    if (p.language !== undefined) body.language = p.language
    await fetch(`${getApiBase()}/system/snippets/${id}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  }

  async function _syncDeleteApi(id: string): Promise<void> {
    await fetch(`${getApiBase()}/system/snippets/${id}`, { method: 'DELETE' })
  }

  async function _syncImportApi(items: Omit<Snippet, "id" | "createdAt">[]): Promise<void> {
    await fetch(`${getApiBase()}/system/snippets/import`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(items.map(s => ({ prefix: s.prefix, name: s.name, description: s.description, body: s.body, language: s.language }))),
    })
  }

  /** 导出 snippets JSON */
  function exportSnippets(): string {
    return JSON.stringify(snippets.value.map(s => ({
      prefix: s.prefix,
      name: s.name,
      description: s.description,
      body: s.body,
      language: s.language ?? undefined,
    })), null, 2)
  }

  /** 生成 Monaco CompletionItemProvider 的 completion items */
  function getCompletionItems(lang?: string) {
    const items = getForLanguage(lang)
    return items.map(s => ({
      label: s.prefix,
      kind: 15, // monaco.languages.CompletionItemKind.Snippet
      insertText: s.body,
      insertTextRules: 4, // InsertAsSnippet
      detail: s.name,
      documentation: s.description,
      range: undefined as any,
    }))
  }

  return {
    snippets, byLanguage, languages,
    getForLanguage, getCompletionItems,
    create, update, remove, importSnippets, exportSnippets,
    syncFromApi,
  }
})
