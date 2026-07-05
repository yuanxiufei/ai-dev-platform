/**
 * useSmartDropPaste — VSCode Drop/Paste API 对标
 * Session 42: 智能拖放和粘贴，支持文件/文字/图片类型
 */
import { ref, onMounted, onUnmounted } from "vue"

export interface DropPayload {
  type: "file" | "text" | "image"
  files?: File[]
  text?: string
  position: { line: number; column: number }
}

export interface PasteHandler {
  /** 处理类型: auto-detect by mimeType */
  accept: string[]
  /** 处理函数 */
  handler: (payload: DropPayload) => string | undefined
  /** 优先级 */
  priority?: number
}

const handlers = ref<PasteHandler[]>([])

/** 注册粘贴/拖放处理器 */
export function useSmartDropPaste() {
  const lastDropPosition = ref({ line: 0, column: 0 })

  function registerHandler(h: PasteHandler): () => void {
    handlers.value.push(h)
    return () => {
      const idx = handlers.value.indexOf(h)
      if (idx !== -1) handlers.value.splice(idx, 1)
    }
  }

  /** 处理拖放 */
  function handleDrop(e: DragEvent): string | undefined {
    e.preventDefault()
    if (!e.dataTransfer) return

    const files = Array.from(e.dataTransfer.files || [])
    const text = e.dataTransfer.getData("text/plain")
    const payload: DropPayload = {
      type: files.length > 0 ? "file" : "text",
      files: files.length > 0 ? files : undefined,
      text: text || undefined,
      position: { ...lastDropPosition.value },
    }

    // 按优先级排序处理
    const sorted = [...handlers.value].sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0))
    for (const h of sorted) {
      const result = h.handler(payload)
      if (result !== undefined) return result
    }
    return undefined
  }

  /** 处理粘贴 */
  function handlePaste(e: ClipboardEvent): string | undefined {
    if (!e.clipboardData) return

    const text = e.clipboardData.getData("text/plain")
    const files = Array.from(e.clipboardData.files || [])
    if (!text && files.length === 0) return

    const payload: DropPayload = {
      type: files.length > 0 ? "file" : (text ? "text" : "image"),
      files: files.length > 0 ? files : undefined,
      text: text || undefined,
      position: { ...lastDropPosition.value },
    }

    const sorted = [...handlers.value].sort((a, b) => (b.priority ?? 0) - (a.priority ?? 0))
    for (const h of sorted) {
      const result = h.handler(payload)
      if (result !== undefined) return result
    }
    return undefined
  }

  /** 更新拖放/粘贴位置 */
  function updatePosition(line: number, column: number): void {
    lastDropPosition.value = { line, column }
  }

  // 注册内置处理器
  onMounted(() => {
    // 内置: 文件路径插入
    registerHandler({
      accept: ["text/uri-list"],
      handler: (payload) => {
        if (payload.files && payload.files.length > 0) {
          // 图片文件
          const imgFiles = payload.files.filter(f => /\.(png|jpg|gif|svg|webp)$/i.test(f.name))
          if (imgFiles.length > 0) {
            return imgFiles.map(f => `![${f.name}](/${f.name})`).join("\n")
          }
          return payload.files.map(f => `\`${f.name}\``).join("\n")
        }
        return undefined
      },
      priority: 10,
    })

    // 内置: 文本智能粘贴
    registerHandler({
      accept: ["text/plain"],
      handler: (payload) => {
        if (payload.text) {
          // 检测是否 HTML - 尝试提取纯文本
          const html = payload.text
          if (/<[a-z][\s\S]*>/i.test(html)) {
            const div = document.createElement("div")
            div.innerHTML = html
            return div.textContent || undefined
          }
          // 纯文本直接原样返回
          return undefined // 让编辑器自行处理
        }
        return undefined
      },
      priority: 5,
    })
  })

  return {
    registerHandler,
    handleDrop,
    handlePaste,
    updatePosition,
    handlers,
  }
}
