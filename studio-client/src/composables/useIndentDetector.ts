/**
 * useIndentDetector — 自动缩进检测
 *
 * 对标: vscode/src/vs/editor/common/model/indentationGuesser.ts
 *
 * 算法: 扫描前 N 行, 统计前导 tabs/spaces, 最大公约数确定缩进大小
 *
 * 用法:
 *   const detector = useIndentDetector()
 *   const info = detector.detect(code)
 *   // { indentSize: 2, usesTabs: false, confidence: 0.95, mixed: false }
 */

import { ref } from 'vue'

export interface IndentInfo {
  indentSize: number
  usesTabs: boolean
  confidence: number   // 0~1
  mixed: boolean       // tabs+spaces 混用
  tabCount: number
  spaceCount: number
  dominantStyle: 'tabs' | 'spaces' | 'unknown'
}

export function useIndentDetector() {
  const lastResult = ref<IndentInfo | null>(null)

  /**
   * 检测文本缩进风格
   *
   * @param content 文本内容
   * @param sampleLines 扫描行数上限 (默认 500)
   */
  function detect(content: string, sampleLines = 500): IndentInfo {
    const lines = content.split('\n').slice(0, sampleLines)

    let tabLines = 0
    let tabCount = 0
    let spaceIndents: number[] = []
    let spaceLines = 0

    for (const line of lines) {
      const trimmed = line.trimStart()
      if (!trimmed) continue

      const leading = line.slice(0, line.length - trimmed.length)
      if (!leading) {
        spaceIndents.push(0)
        continue
      }

      const tabs = (leading.match(/\t/g) || []).length
      const spaces = (leading.match(/ /g) || []).length

      if (tabs > 0) {
        tabCount += tabs
        tabLines++
      }
      if (spaces > 0) {
        spaceIndents.push(spaces)
        spaceLines++
      }
    }

    const totalLines = tabLines + spaceLines
    if (totalLines === 0 || spaceIndents.length === 0) {
      const result: IndentInfo = {
        indentSize: 2, usesTabs: false, confidence: 0.5, mixed: false,
        tabCount, spaceCount: 0, dominantStyle: 'unknown',
      }
      lastResult.value = result
      return result
    }

    // Tab 主导?
    const tabRatio = totalLines > 0 ? tabLines / totalLines : 0
    const usesTabs = tabCount > spaceIndents.length && tabRatio > 0.5
    const mixed = tabLines > 0 && spaceLines > 0

    if (usesTabs) {
      const result: IndentInfo = {
        indentSize: 4, usesTabs: true, confidence: Math.round(tabRatio * 100) / 100,
        mixed, tabCount, spaceCount: spaceLines,
        dominantStyle: 'tabs',
      }
      lastResult.value = result
      return result
    }

    // 空格主导: GCD 计算
    const unique = [...new Set(spaceIndents.filter(s => s > 0))]
    const size = _gcdList(unique)
    const indentSize = (size < 1 || size > 8) ? Math.min(...unique, 2) : size

    const confidence = totalLines > 0 ? spaceLines / totalLines : 0.5
    const result: IndentInfo = {
      indentSize,
      usesTabs: false,
      confidence: Math.round(confidence * 100) / 100,
      mixed,
      tabCount,
      spaceCount: spaceLines,
      dominantStyle: 'spaces',
    }
    lastResult.value = result
    return result
  }

  /** 检测缩进并返回建议的编辑器配置 */
  function detectAndSuggest(content: string, sampleLines?: number) {
    const info = detect(content, sampleLines)
    return {
      ...info,
      insertSpaces: !info.usesTabs,
      tabSize: info.indentSize,
    }
  }

  return { detect, detectAndSuggest, lastResult }
}

function _gcd(a: number, b: number): number {
  while (b) { [a, b] = [b, a % b] }
  return a
}

function _gcdList(nums: number[]): number {
  if (nums.length === 0) return 2
  let result = nums[0]
  for (const n of nums.slice(1)) {
    result = _gcd(result, n)
  }
  return result
}
