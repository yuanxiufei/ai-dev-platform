/**
 * useFolding — VSCode 风格代码折叠
 *
 * 对标: VSCode FoldingRangeProvider + foldingController
 * Session 53: 新增，连接后端 /system/lsp/folding-ranges
 *
 * 使用 Monaco 内置 foldingRangeProvider 注册后端返回的折叠范围，
 * 支持 AST 分析 (Python) 和缩进/大括号回退 (JS/TS/Java/...)
 */
import { ref } from "vue"
import type * as monacoNs from "monaco-editor"
import * as lspApi from "@/api/lsp"

export interface FoldingRangeItem {
  start_line: number
  end_line: number
  kind: string
}

let monacoRef: typeof monacoNs | null = null
try { monacoRef = (window as any).monaco } catch { /* preload */ }

/** 注册过的 provider 引用，用于卸载 */
let registeredProvider: monacoNs.IDisposable | null = null

export function useFolding(
  getContent: () => string,
  getLanguage: () => string,
  getFilePath: () => string,
) {
  const isEnabled = ref(true)
  const isPending = ref(false)
  const foldingCount = ref(0)

  /** 注册自定义 FoldingRangeProvider */
  function registerFoldingProvider(): monacoNs.IDisposable | null {
    if (!monacoRef) {
      monacoRef = (window as any).monaco
      if (!monacoRef) return null
    }

    const provider: monacoNs.languages.FoldingRangeProvider = {
      provideFoldingRanges: async (model) => {
        if (!isEnabled.value) return []

        const content = model.getValue()
        const language = model.getLanguageId()
        const filePath = getFilePath()
        isPending.value = true

        try {
          const result = await lspApi.getFoldingRanges({
            content,
            language,
            file_path: filePath,
          })

          const ranges: monacoNs.languages.FoldingRange[] = []
          for (const fr of result.ranges) {
            ranges.push({
              start: fr.start_line + 1,  // Monaco 1-based
              end: fr.end_line + 1,
              kind: monacoRef!.languages.FoldingRangeKind.Region,
            })
          }
          foldingCount.value = ranges.length
          return ranges
        } catch {
          // 回退到 Monaco 内置的缩进折叠
          return []
        } finally {
          isPending.value = false
        }
      },
    }

    // 注册为全局 provider
    registeredProvider = monacoRef.languages.registerFoldingRangeProvider(
      { scheme: "file" },
      provider
    )

    return registeredProvider
  }

  /** 卸载 FoldingProvider */
  function unregisterFoldingProvider(): void {
    if (registeredProvider) {
      registeredProvider.dispose()
      registeredProvider = null
      foldingCount.value = 0
    }
  }

  return {
    isEnabled,
    isPending,
    foldingCount,
    registerFoldingProvider,
    unregisterFoldingProvider,
  }
}
