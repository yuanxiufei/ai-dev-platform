/**
 * Markdown 渲染引擎 — 轻量级自实现
 *
 * 对标 hermes-studio MarkdownRenderer.vue，支持：
 *   - 标题 (h1-h6) / 粗体 / 斜体 / 删除线 / 行内代码 / 链接 / 图片
 *   - 有序/无序列表 / 引用 / 分割线 / 表格
 *   - 代码块 (```lang) / Mermaid 图表 / KaTeX 数学公式
 *   - 自动链接检测
 *
 * 零外部依赖，使用 CDN 动态加载 Mermaid/KaTeX
 */

import { nextTick, ref, type Ref } from "vue"

/** 渲染结果：每个段落的结构 */
export interface MdBlock {
  type: "heading" | "paragraph" | "code" | "mermaid" | "katex" | "list" | "blockquote" | "table" | "hr" | "html"
  level?: number // heading level
  lang?: string  // code block language
  content: string
  html?: string  // pre-rendered HTML
  items?: string[] // list items
}

// ── Mermaid 缓存 ──
let mermaidLoaded = false
const mermaidCache = new Map<string, string>()

// ── KaTeX 缓存 ──
let katexLoaded = false

/**
 * 解析 Markdown 文本为分段结构
 */
export function parseMarkdown(text: string): MdBlock[] {
  if (!text) return []
  const blocks: MdBlock[] = []
  let i = 0
  const lines = text.split("\n")

  while (i < lines.length) {
    const line = lines[i]

    // ── 围栏代码块 (```lang ... ```) ──
    const fenceMatch = line.match(/^```(\w*)\s*$/)
    if (fenceMatch) {
      const lang = (fenceMatch[1] || "").toLowerCase()
      const codeLines: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i])
        i++
      }
      const code = codeLines.join("\n")
      if (lang === "mermaid") {
        blocks.push({ type: "mermaid", lang: "mermaid", content: code })
      } else {
        blocks.push({ type: "code", lang: lang || "text", content: code })
      }
      i++ // 跳过闭合 ```
      continue
    }

    // ── KaTeX 块公式 ($$ ... $$) ──
    if (line.match(/^\$\$/)) {
      const mathLines: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith("$$")) {
        mathLines.push(lines[i])
        i++
      }
      blocks.push({ type: "katex", content: mathLines.join("\n") })
      i++ // 跳过闭合 $$
      continue
    }

    // ── 空行 ──
    if (line.trim() === "") {
      i++
      continue
    }

    // ── 水平线 ──
    if (/^(?:---|\*\*\*|___)\s*$/.test(line)) {
      blocks.push({ type: "hr", content: "" })
      i++
      continue
    }

    // ── HTML 注释 ──
    if (/^<!--/.test(line.trim())) {
      i++
      while (i < lines.length && !/-->/.test(lines[i])) i++
      i++
      continue
    }

    // ── 标题 ──
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/)
    if (headingMatch) {
      blocks.push({
        type: "heading",
        level: headingMatch[1].length,
        content: headingMatch[2],
      })
      i++
      continue
    }

    // ── 引用 ──
    if (line.startsWith("> ")) {
      const quoteLines: string[] = []
      while (i < lines.length && (lines[i].startsWith("> ") || lines[i].startsWith(">"))) {
        quoteLines.push(lines[i].replace(/^>\s?/, ""))
        i++
      }
      blocks.push({ type: "blockquote", content: quoteLines.join("\n") })
      continue
    }

    // ── 无序列表 ──
    if (/^[\s]*[-*+]\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^[\s]*[-*+]\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^[\s]*[-*+]\s+/, ""))
        i++
      }
      blocks.push({ type: "list", content: "", items })
      continue
    }

    // ── 有序列表 ──
    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = []
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s+/, ""))
        i++
      }
      blocks.push({ type: "list", content: "ordered", items })
      continue
    }

    // ── 表格 ──
    if (line.includes("|") && i + 1 < lines.length && lines[i + 1].match(/^\|?[\s:-]+\|/)) {
      blocks.push({ type: "table", content: lines[i], html: lines[i + 1] || "" })
      i += 2
      continue
    }

    // ── 普通段落 ──
    const paraLines: string[] = [line]
    i++
    while (i < lines.length && lines[i].trim() !== "" && !lines[i].startsWith("#") &&
      !lines[i].startsWith("```") && !lines[i].startsWith("$$") && !/^[-*+]\s/.test(lines[i]) &&
      !/^\d+\.\s/.test(lines[i]) && !lines[i].startsWith("> ") && !lines[i].includes("|")) {
      paraLines.push(lines[i])
      i++
    }
    blocks.push({ type: "paragraph", content: paraLines.join("\n") })
  }

  return blocks
}

/**
 * 内联 Markdown → HTML（行内渲染：加粗/斜体/删除线/代码/链接/图片/KaTeX）
 */
export function renderInline(text: string): string {
  let html = escapeHtml(text)

  // 行内 KaTeX $...$
  html = html.replace(/\$([^$]+)\$/g, (_: string, formula: string) => {
    return `<span class="katex-inline" data-formula="${escapeAttr(formula)}">$${escapeHtml(formula)}$</span>`
  })

  // 图片 ![alt](url)
  html = html.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" class="md-image rounded max-w-full my-1" loading="lazy" />')
  // 链接 [text](url)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener" class="md-link">$1</a>')
  // **粗体**
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  // *斜体*
  html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>')
  // ~~删除线~~
  html = html.replace(/~~([^~]+)~~/g, '<del>$1</del>')
  // `行内代码`
  html = html.replace(/`([^`]+)`/g, '<code class="md-inline-code">$1</code>')

  // 自动链接
  html = html.replace(/(?<!["'=])(https?:\/\/[^\s<>\[\]]+)/g, '<a href="$1" target="_blank" rel="noopener" class="md-link">$1</a>')

  return html
}

/**
 * 代码高亮（简单关键词着色）
 */
export function highlightCode(code: string, lang: string): string {
  const escaped = escapeHtml(code)
  if (!lang || lang === "text" || lang === "plaintext") return escaped

  // 通用关键词
  const keywords = [
    "function", "class", "const", "let", "var", "return", "if", "else", "for", "while",
    "import", "export", "from", "async", "await", "try", "catch", "throw", "new",
    "interface", "type", "enum", "extends", "implements", "static", "public", "private",
    "def", "self", "None", "True", "False", "print", "lambda", "yield",
    "func", "struct", "impl", "pub", "mut", "match", "use", "mod", "fn"
  ]
  const kwPattern = new RegExp(`\\b(${keywords.join("|")})\\b`, "g")
  let result = escaped.replace(kwPattern, '<span class="md-kw">$1</span>')

  // 字符串
  result = result.replace(/(["'`])(?:(?!\1|\\).|\\.)*\1/g, '<span class="md-str">$&</span>')
  // 注释 (//)
  result = result.replace(/(\/\/[^\n]*)/g, '<span class="md-cmt">$1</span>')
  // 数字
  result = result.replace(/\b(\d+\.?\d*)\b/g, '<span class="md-num">$1</span>')

  return result
}

/**
 * 渲染 Markdown → HTML 字符串
 * @param headingPrefix 标题 ID 前缀（可选，用于对话大纲跳转）
 */
export function renderMarkdownToHtml(text: string, headingPrefix = ""): string {
  const blocks = parseMarkdown(text)
  let hCount = 0
  return blocks.map(b => {
    if (b.type === "heading" && headingPrefix) {
      hCount++
      const id = `${headingPrefix}-${hCount}`
      return renderBlockWithId(b, id)
    }
    return renderBlock(b)
  }).join("")
}

/** 渲染带 ID 的标题 block */
function renderBlockWithId(block: MdBlock, id: string): string {
  return `<h${block.level} class="md-h${block.level}" id="${id}">${renderInline(block.content)}</h${block.level}>`
}

/**
 * 渲染单个 block → HTML
 */
function renderBlock(block: MdBlock): string {
  switch (block.type) {
    case "heading":
      return `<h${block.level} class="md-h${block.level}">${renderInline(block.content)}</h${block.level}>`

    case "paragraph":
      return `<p class="md-p">${renderInline(block.content)}</p>`

    case "code":
      return `<div class="md-code-block">
        <div class="md-code-header">
          <span class="md-code-lang">${block.lang || "text"}</span>
          <button class="md-code-copy" data-code="${escapeAttr(block.content)}" title="复制代码">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="5" y="5" width="9" height="9" rx="1"/><path d="M11 4V2a1 1 0 00-1-1H3a1 1 0 00-1 1v9a1 1 0 001 1h1"/></svg>
          </button>
        </div>
        <pre><code class="md-code-content language-${block.lang || ""}">${highlightCode(block.content, block.lang || "")}</code></pre>
      </div>`

    case "mermaid":
      return `<div class="md-mermaid-block" data-mermaid="${escapeAttr(block.content)}">
        <div class="md-code-header"><span class="md-code-lang">mermaid</span></div>
        <div class="md-mermaid-render">${escapeHtml(block.content)}</div>
      </div>`

    case "katex":
      return `<div class="md-katex-block" data-katex="${escapeAttr(block.content)}">$$${escapeHtml(block.content)}$$</div>`

    case "blockquote":
      return `<blockquote class="md-blockquote"><p>${renderInline(block.content)}</p></blockquote>`

    case "list": {
      const tag = block.content === "ordered" ? "ol" : "ul"
      const cls = block.content === "ordered" ? "md-ol" : "md-ul"
      const items = (block.items || []).map(item => `<li>${renderInline(item)}</li>`).join("")
      return `<${tag} class="${cls}">${items}</${tag}>`
    }

    case "table": {
      const headerCells = block.content.split("|").filter(c => c.trim())
        .map(c => `<th>${renderInline(c.trim())}</th>`).join("")
      return `<table class="md-table"><thead><tr>${headerCells}</tr></thead></table>`
    }

    case "hr":
      return '<hr class="md-hr" />'

    default:
      return ""
  }
}

/**
 * 动态加载 Mermaid 并渲染图表
 */
export async function renderMermaidElements(container: HTMLElement): Promise<void> {
  const blocks = container.querySelectorAll<HTMLElement>(".md-mermaid-block")
  if (blocks.length === 0) return

  // 动态加载 mermaid
  if (!mermaidLoaded) {
    await loadMermaid()
  }

  for (const block of blocks) {
    const code = block.dataset.mermaid || ""
    if (!code) continue

    try {
      const renderDiv = block.querySelector(".md-mermaid-render")
      if (!renderDiv) continue

      // 检查缓存
      const cacheKey = code.slice(0, 200)
      if (mermaidCache.has(cacheKey)) {
        renderDiv.innerHTML = mermaidCache.get(cacheKey)!
        continue
      }

      const mermaid = (window as any).mermaid
      if (!mermaid) { console.warn("[Markdown] Mermaid not loaded"); continue }
      const id = `mermaid-${Math.random().toString(36).slice(2, 8)}`
      const { svg } = await mermaid.render(id, code)
      renderDiv.innerHTML = svg
      mermaidCache.set(cacheKey, svg)
    } catch (e) {
      console.warn("[Markdown] Mermaid render error:", e)
    }
  }
}

/**
 * 动态加载 KaTeX 并渲染数学公式
 */
export async function renderKaTeXElements(container: HTMLElement): Promise<void> {
  const blocks = container.querySelectorAll<HTMLElement>(".md-katex-block")
  const inlines = container.querySelectorAll<HTMLElement>(".katex-inline")
  if (blocks.length === 0 && inlines.length === 0) return

  if (!katexLoaded) {
    await loadKaTeX()
  }

  const katex = (window as any).katex
  if (!katex) return

  for (const block of blocks) {
    const formula = block.dataset.katex || ""
    if (!formula) continue
    try {
      block.innerHTML = katex.renderToString(formula, { throwOnError: false, displayMode: true })
    } catch (e) {
      console.warn("[Markdown] KaTeX block error:", e)
    }
  }

  for (const inline of inlines) {
    const formula = inline.dataset.formula || ""
    if (!formula) continue
    try {
      inline.innerHTML = katex.renderToString(formula, { throwOnError: false, displayMode: false })
    } catch (e) {
      // silent
    }
  }
}

async function loadMermaid(): Promise<void> {
  // 从 CDN 动态加载 mermaid（非 npm 依赖）
  if ((window as any).mermaid) {
    mermaidLoaded = true
    return
  }
  try {
    await new Promise<void>((resolve, reject) => {
      const script = document.createElement("script")
      script.src = "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"
      script.onload = () => resolve()
      script.onerror = () => reject(new Error("Mermaid CDN load failed"))
      document.head.appendChild(script)
    })
    mermaidLoaded = true
  } catch (e) {
    console.warn("[Markdown] Mermaid not available:", e)
  }
}

async function loadKaTeX(): Promise<void> {
  try {
    await new Promise<void>((resolve, reject) => {
      const link = document.createElement("link")
      link.rel = "stylesheet"
      link.href = "https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.css"
      document.head.appendChild(link)

      const script = document.createElement("script")
      script.src = "https://cdn.jsdelivr.net/npm/katex@0.16/dist/katex.min.js"
      script.onload = () => resolve()
      script.onerror = () => reject(new Error("KaTeX CDN load failed"))
      document.head.appendChild(script)
    })
    katexLoaded = true
  } catch (e) {
    console.warn("[Markdown] KaTeX not available:", e)
  }
}

// ── 工具函数 ──

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
}

function escapeAttr(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
}

// ── 复制代码按钮 ──

/**
 * 为 container 中所有代码块绑定复制功能
 */
export function bindCodeCopy(container: HTMLElement): void {
  container.querySelectorAll(".md-code-copy").forEach(btn => {
    btn.addEventListener("click", async () => {
      const code = (btn as HTMLElement).dataset.code || ""
      try {
        await navigator.clipboard.writeText(decodeURIComponent(code))
        btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 8l3 3 7-7"/></svg>'
        setTimeout(() => {
          btn.innerHTML = '<svg width="12" height="12" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="5" y="5" width="9" height="9" rx="1"/><path d="M11 4V2a1 1 0 00-1-1H3a1 1 0 00-1 1v9a1 1 0 001 1h1"/></svg>'
        }, 2000)
      } catch {
        // fallback
      }
    })
  })
}

/**
 * 渲染完 HTML 后的后处理（Mermaid/KaTeX/代码复制）
 */
export async function postProcessMarkdown(container: HTMLElement): Promise<void> {
  await nextTick()
  bindCodeCopy(container)
  await Promise.all([
    renderMermaidElements(container),
    renderKaTeXElements(container),
  ])
}
