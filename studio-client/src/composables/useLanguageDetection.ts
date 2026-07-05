/**
 * useLanguageDetection — 自动语言检测（无扩展名文件）
 *
 * 借鉴: VSCode src/vs/workbench/contrib/languageDetection/
 * 能力:
 *   - 基于文件内容的启发式语言识别
 *   - Shebang 行分析
 *   - 常见模式匹配 (import/require/<?php/#!/etc)
 */
import { ref } from "vue"

export interface LanguageGuess {
  language: string
  confidence: number
  reason: string
}

/** 启发式检测：根据文件内容猜测语言 */
function detectLanguage(content: string, fileName: string): LanguageGuess[] {
  const guesses: LanguageGuess[] = []
  const firstLine = content.split("\n")[0]?.trim() ?? ""

  // Shebang 行
  if (firstLine.startsWith("#!")) {
    if (firstLine.includes("python") || firstLine.includes("python3"))
      guesses.push({ language: "python", confidence: 0.95, reason: "Shebang: python" })
    else if (firstLine.includes("node"))
      guesses.push({ language: "javascript", confidence: 0.9, reason: "Shebang: node" })
    else if (firstLine.includes("bash") || firstLine.includes("sh"))
      guesses.push({ language: "shell", confidence: 0.9, reason: "Shebang: bash/sh" })
    else if (firstLine.includes("ruby"))
      guesses.push({ language: "ruby", confidence: 0.9, reason: "Shebang: ruby" })
    else if (firstLine.includes("perl"))
      guesses.push({ language: "perl", confidence: 0.9, reason: "Shebang: perl" })
    else
      guesses.push({ language: "plaintext", confidence: 0.5, reason: "Shebang: unknown" })
  }

  // XML/HTML 检测
  if (/<[?!]xml/i.test(firstLine))
    guesses.push({ language: "xml", confidence: 0.9, reason: "XML declaration" })
  if (/^<!DOCTYPE\s+html/i.test(firstLine) || /<html/i.test(content.substring(0, 500)))
    guesses.push({ language: "html", confidence: 0.95, reason: "HTML structure" })

  // 代码模式检测
  const patterns: Array<{ regex: RegExp; language: string; confidence: number; reason: string }> = [
    // TypeScript/JavaScript
    { regex: /^(import|export)\s+.*\s+from\s+['"]/, language: "typescript", confidence: 0.7, reason: "ES import/export with from" },
    { regex: /^(import|export)\s+(type\s+)?\{/, language: "typescript", confidence: 0.8, reason: "Named import/export" },
    { regex: /:\s*(string|number|boolean|void|any|never)\b/, language: "typescript", confidence: 0.85, reason: "TypeScript type annotation" },
    { regex: /interface\s+\w+\s*\{/, language: "typescript", confidence: 0.9, reason: "TypeScript interface" },
    { regex: /const\s+\w+\s*:\s*\w+/, language: "typescript", confidence: 0.75, reason: "Typed const declaration" },
    { regex: /^import\s/, language: "javascript", confidence: 0.6, reason: "ES import" },
    { regex: /const\s+\w+\s*=\s*require/, language: "javascript", confidence: 0.8, reason: "CommonJS require" },

    // Python
    { regex: /^(import\s+\w+|from\s+\w+\s+import)/, language: "python", confidence: 0.85, reason: "Python import" },
    { regex: /^def\s+\w+\s*\(/, language: "python", confidence: 0.9, reason: "Python function definition" },
    { regex: /^class\s+\w+.*:$/, language: "python", confidence: 0.85, reason: "Python class" },
    { regex: /^if __name__\s*==\s*['"]__main__['"]/, language: "python", confidence: 0.95, reason: "Python main guard" },

    // Rust
    { regex: /^(fn|pub\s+fn|pub\s+struct|impl)\s+\w+/, language: "rust", confidence: 0.9, reason: "Rust fn/struct/impl" },
    { regex: /^(use|mod)\s+\w+/, language: "rust", confidence: 0.8, reason: "Rust use/mod" },

    // Go
    { regex: /^package\s+\w+/, language: "go", confidence: 0.9, reason: "Go package declaration" },
    { regex: /^func\s+\w+/, language: "go", confidence: 0.85, reason: "Go function" },

    // PHP
    { regex: /^<\?php/, language: "php", confidence: 0.95, reason: "PHP opening tag" },

    // Ruby
    { regex: /^(require|gem)\s+['"]/, language: "ruby", confidence: 0.8, reason: "Ruby require" },

    // Java
    { regex: /^(public|private|protected)\s+(static\s+)?(class|interface)\s+\w+/, language: "java", confidence: 0.9, reason: "Java class declaration" },
    { regex: /^package\s+[\w.]+\s*;/, language: "java", confidence: 0.9, reason: "Java package" },

    // C/C++
    { regex: /^#include\s*[<"]/, language: "cpp", confidence: 0.85, reason: "C/C++ include" },
    { regex: /int\s+main\s*\(/, language: "cpp", confidence: 0.7, reason: "C main function" },

    // YAML
    { regex: /^---\s*$/, language: "yaml", confidence: 0.7, reason: "YAML document start" },

    // JSON
    { regex: /^\s*[{[]/, language: "json", confidence: 0.7, reason: "Starts with { or [" },

    // Shell
    { regex: /^(#!/, language: "shellscript", confidence: 0.7, reason: "Shebang" },
    { regex: /^(echo|cd|export|source)\s/, language: "shellscript", confidence: 0.6, reason: "Shell command" },

    // Markdown
    { regex: /^#\s+\w+/, language: "markdown", confidence: 0.8, reason: "Markdown heading" },

    // Makefile
    { regex: /^[\w./-]+\s*:\s*[\w./-]+/, language: "makefile", confidence: 0.85, reason: "Make target" },

    // Dockerfile
    { regex: /^(FROM|RUN|COPY|CMD|EXPOSE|ENV|WORKDIR)\s/, language: "dockerfile", confidence: 0.9, reason: "Dockerfile instruction" },

    // CSS
    { regex: /^[\w.#\[].*\{/, language: "css", confidence: 0.6, reason: "CSS rule" },
  ]

  for (const { regex, language, confidence, reason } of patterns) {
    if (regex.test(content)) {
      // 避免重复添加同语言的较低信心猜测
      const existing = guesses.find(g => g.language === language)
      if (!existing || existing.confidence < confidence) {
        if (existing) {
          existing.confidence = confidence
          existing.reason = reason
        } else {
          guesses.push({ language, confidence, reason })
        }
      }
    }
  }

  // 如果完全没有匹配，回退到基于文件名的猜测
  if (guesses.length === 0) {
    const nameLower = fileName.toLowerCase()
    if (nameLower.includes("makefile")) guesses.push({ language: "makefile", confidence: 0.7, reason: "Filename: Makefile" })
    else if (nameLower === "dockerfile") guesses.push({ language: "dockerfile", confidence: 0.8, reason: "Filename: Dockerfile" })
    else if (nameLower.includes("docker-compose")) guesses.push({ language: "yaml", confidence: 0.6, reason: "Filename: docker-compose" })
    else guesses.push({ language: "plaintext", confidence: 0.3, reason: "No patterns detected" })
  }

  return guesses.sort((a, b) => b.confidence - a.confidence)
}

/** Monaco language ID 映射 (部分语言名需要转换) */
const LANG_ID_MAP: Record<string, string> = {
  "shell": "shellscript",
  "bash": "shellscript",
  "zsh": "shellscript",
  "node": "javascript",
}

export function useLanguageDetection() {
  const lastDetection = ref<LanguageGuess[]>([])

  function detect(content: string, fileName: string): LanguageGuess[] {
    lastDetection.value = detectLanguage(content, fileName)
    return lastDetection.value
  }

  function getMonacoLanguage(content: string, fileName: string): string {
    const guesses = detect(content, fileName)
    if (guesses.length > 0 && guesses[0].confidence >= 0.6) {
      const lang = guesses[0].language
      return LANG_ID_MAP[lang] ?? lang
    }
    return "plaintext"
  }

  return { detect, getMonacoLanguage, lastDetection }
}
