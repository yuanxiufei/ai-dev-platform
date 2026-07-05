/**
 * useInlineDebugValues — VSCode 风格内联调试变量显示
 *
 * Session 37: VSCode 功能对齐
 * 借鉴 VSCode inlineValuesProvider + debugHover
 * 调试暂停时在各变量定义行尾显示当前值。
 *
 * 用法：
 *   const inlineDebug = useInlineDebugValues(editorRef, monacoRef)
 *   // 调试暂停时
 *   inlineDebug.show(variables)   // 显示内联值
 *   // 恢复执行时
 *   inlineDebug.hide()            // 隐藏
 */

import { type Ref, type ShallowRef, watch } from 'vue'
import type { DebugVariable } from '@/stores/useDebugStore'
import { useDebugStore } from '@/stores/useDebugStore'

export interface InlineValue {
  line: number
  variable: string
  value: string
  type?: string
}

/**
 * useInlineDebugValues composable
 */
export function useInlineDebugValues(
  editorRef: Readonly<ShallowRef<any | null>>,
  monacoRef: Readonly<ShallowRef<any | null>>,
) {
  const debugStore = useDebugStore()
  let inlineDecoIds: string[] = []

  /** 清除所有内联值装饰 */
  function hide(): void {
    const editor = editorRef.value
    if (!editor) return
    if (inlineDecoIds.length > 0) {
      editor.deltaDecorations(inlineDecoIds, [])
      inlineDecoIds = []
    }
  }

  /**
   * 显示内联调试值
   * 在每个变量的来源行尾显示 `// name = value`
   */
  function show(variables: DebugVariable[]): void {
    const editor = editorRef.value
    if (!editor || !monacoRef.value) return
    const monaco = monacoRef.value

    const model = editor.getModel()
    if (!model) return

    // 清除旧装饰
    hide()

    const fullContent = model.getValue()
    const lines = fullContent.split('\n')

    const inlineValues: InlineValue[] = []

    // 为每个变量搜索在源码中的位置
    for (const v of variables) {
      // 在当前文件中搜索变量名
      const searchLine = findVariableLine(lines, v.name)
      if (searchLine > 0) {
        inlineValues.push({
          line: searchLine,
          variable: v.name,
          value: formatValue(v.value, v.type),
          type: v.type,
        })
      }
    }

    if (inlineValues.length === 0) return

    // 按行号去重（同行的多个变量合并）
    const merged = mergeInlineValues(inlineValues)

    const decorations = merged.map((iv) => {
      const lineLength = lines[iv.line - 1]?.length ?? 0
      return {
        range: new monaco.Range(iv.line, 1, iv.line, 1),
        options: {
          isWholeLine: false,
          after: {
            content: iv.variables.map(v =>
              `  \u{1F50D} ${v.variable} = ${v.value}`
            ).join(''),
            inlineClassName: 'inline-debug-value',
            inlineClassNameAffectsLetterSpacing: true,
          },
          stickiness: monaco.editor.TrackedRangeStickiness.NeverGrowsWhenTypingAtEdges,
        },
      }
    })

    inlineDecoIds = editor.deltaDecorations([], decorations)
  }

  /** 在源码中搜索变量定义行 */
  function findVariableLine(lines: string[], varName: string): number {
    // 精确匹配: `let/var/const name =` 或 `name =`
    const patterns = [
      new RegExp(`\\b(let|var|const)\\s+${escapeRegex(varName)}\\b`),
      new RegExp(`\\b${escapeRegex(varName)}\\s*=\\s*`),
      new RegExp(`\\b${escapeRegex(varName)}\\s*:\\s*`),
    ]

    for (let i = 0; i < lines.length; i++) {
      // 跳过注释行
      if (lines[i].trim().startsWith('//') || lines[i].trim().startsWith('#')) continue
      for (const pat of patterns) {
        if (pat.test(lines[i])) return i + 1
      }
    }
    return -1
  }

  /** 格式化变量值（截断过长值） */
  function formatValue(value: string, type?: string): string {
    if (!value) return 'undefined'
    const display = value.length > 60 ? value.slice(0, 57) + '...' : value
    const prefix = type ? `/* ${type} */ ` : ''
    return `${prefix}${display}`
  }

  /** 合并同行变量为一个 entry（多个变量间用 | 分隔） */
  function mergeInlineValues(values: InlineValue[]): Array<{ line: number; variables: Array<{ variable: string; value: string }> }> {
    const map = new Map<number, Array<{ variable: string; value: string }>>()
    for (const v of values) {
      if (!map.has(v.line)) map.set(v.line, [])
      const entries = map.get(v.line)!
      // 避免同一变量重复
      if (!entries.some(e => e.variable === v.variable)) {
        entries.push({ variable: v.variable, value: v.value })
      }
    }
    return Array.from(map.entries()).map(([line, variables]) => ({ line, variables }))
  }

  /** 转义正则特殊字符 */
  function escapeRegex(s: string): string {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  }

  // ── 自动同步调试状态 ──

  // 当调试暂停/恢复时自动显示/隐藏内联值
  watch(
    () => debugStore.isPaused,
    (paused) => {
      if (paused && debugStore.variables.length > 0) {
        // 延迟显示，等编辑器渲染完
        setTimeout(() => show(debugStore.variables as DebugVariable[]), 200)
      } else if (!paused) {
        hide()
      }
    },
  )

  // 变量列表变化时更新
  watch(
    () => debugStore.variables,
    (vars) => {
      if (debugStore.isPaused && vars.length > 0) {
        setTimeout(() => show(vars as DebugVariable[]), 100)
      }
    },
    { deep: true },
  )

  return { show, hide }
}

/**
 * 对单体 variable 列表模拟内联值（不依赖编辑器的独立版本）
 * 适用于调用方传入任意变量数组
 */
export function simulateInlineValues(
  variables: DebugVariable[],
  fileContent: string,
): InlineValue[] {
  const lines = fileContent.split('\n')
  const results: InlineValue[] = []

  for (const v of variables) {
    const patterns = [
      new RegExp(`\\b(let|var|const)\\s+${v.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`),
      new RegExp(`\\b${v.name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*=\\s*`),
    ]
    for (let i = 0; i < lines.length; i++) {
      if (lines[i].trim().startsWith('//') || lines[i].trim().startsWith('#')) continue
      for (const pat of patterns) {
        if (pat.test(lines[i])) {
          results.push({
            line: i + 1,
            variable: v.name,
            value: v.value.length > 60 ? v.value.slice(0, 57) + '...' : v.value,
            type: v.type,
          })
          break
        }
      }
    }
  }
  return results
}
