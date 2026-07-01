/**
 * ANSI 颜色解析器单元测试
 *
 * 测试 src/utils/ansi.ts 的解析逻辑：
 * - 基本 SGR 样式 (bold/dim/italic/underline)
 * - 16 色标准颜色
 * - 256 色调色板
 * - True Color (38;2;R;G;B)
 * - hasAnsi / stripAnsi 辅助函数
 * - 边界情况（空字符串、无 ANSI、截断序列）
 */
import { describe, expect, it } from "vitest"
import { hasAnsi, parseAnsi, stripAnsi, segmentStyle } from "@/utils/ansi"

describe("hasAnsi — ANSI 转义序列检测", () => {
  it("包含 ANSI 的字符串应返回 true", () => {
    expect(hasAnsi("\x1b[31mRed\x1b[0m")).toBe(true)
  })

  it("纯文本应返回 false", () => {
    expect(hasAnsi("Plain text without codes")).toBe(false)
  })

  it("空字符串应返回 false", () => {
    expect(hasAnsi("")).toBe(false)
  })

  it("包含不完整的转义序列应返回 false", () => {
    expect(hasAnsi("\x1b31mMissing bracket")).toBe(false)
  })
})

describe("stripAnsi — 移除 ANSI 转义序列", () => {
  it("应正确移除颜色码", () => {
    expect(stripAnsi("\x1b[31mRed\x1b[0m")).toBe("Red")
  })

  it("应正确移除多段样式", () => {
    expect(stripAnsi("\x1b[1m\x1b[31mBold Red\x1b[0m")).toBe("Bold Red")
  })

  it("应正确保留纯文本", () => {
    expect(stripAnsi("No ANSI here")).toBe("No ANSI here")
  })

  it("空字符串应返回空字符串", () => {
    expect(stripAnsi("")).toBe("")
  })
})

describe("parseAnsi — ANSI 转义序列解析", () => {
  it("应为纯文本返回单个纯文本段", () => {
    const segments = parseAnsi("Hello World")
    expect(segments.length).toBe(1)
    expect(segments[0].text).toBe("Hello World")
    expect(segments[0].fg).toBeUndefined()
    expect(segments[0].bg).toBeUndefined()
  })

  it("应解析前景色 (31 = 红色)", () => {
    const segments = parseAnsi("\x1b[31mRed\x1b[0m")
    expect(segments.length).toBeGreaterThanOrEqual(1)
    const textSeg = segments.find((s) => s.text === "Red")
    expect(textSeg).toBeDefined()
    if (textSeg) {
      expect(textSeg.fg).toBeDefined()
    }
  })

  it("应解析多个样式段", () => {
    const segments = parseAnsi("\x1b[31mRed \x1b[32mGreen\x1b[0m")
    expect(segments.length).toBeGreaterThanOrEqual(2)
  })

  it("空字符串应返回空数组", () => {
    const segments = parseAnsi("")
    expect(segments.length).toBe(0)
  })

  it("bold (1) 样式应生效", () => {
    const segments = parseAnsi("\x1b[1mBold\x1b[0m")
    const textSeg = segments.find((s) => s.text === "Bold")
    expect(textSeg).toBeDefined()
    if (textSeg) {
      expect(textSeg.bold).toBe(true)
    }
  })

  it("dim (2) 样式应生效", () => {
    const segments = parseAnsi("\x1b[2mDimmed\x1b[0m")
    const textSeg = segments.find((s) => s.text === "Dimmed")
    expect(textSeg).toBeDefined()
    if (textSeg) {
      expect(textSeg.dim).toBe(true)
    }
  })

  it("italic (3) 样式应生效", () => {
    const segments = parseAnsi("\x1b[3mItalic\x1b[0m")
    const textSeg = segments.find((s) => s.text === "Italic")
    expect(textSeg).toBeDefined()
    if (textSeg) {
      expect(textSeg.italic).toBe(true)
    }
  })

  it("underline (4) 样式应生效", () => {
    const segments = parseAnsi("\x1b[4mUnderline\x1b[0m")
    const textSeg = segments.find((s) => s.text === "Underline")
    expect(textSeg).toBeDefined()
    if (textSeg) {
      expect(textSeg.underline).toBe(true)
    }
  })

  it("应解析复合样式 (bold + red)", () => {
    const segments = parseAnsi("\x1b[1;31mBold Red\x1b[0m")
    const textSeg = segments.find((s) => s.text === "Bold Red")
    expect(textSeg).toBeDefined()
    if (textSeg) {
      expect(textSeg.bold).toBe(true)
      expect(textSeg.fg).toBeDefined()
    }
  })

  it("应解析 256 色前景", () => {
    // 38;5;n — 256 色调色板
    const segments = parseAnsi("\x1b[38;5;196mRed\x1b[0m")
    const textSeg = segments.find((s) => s.text === "Red")
    expect(textSeg).toBeDefined()
    if (textSeg) {
      expect(textSeg.fg).toBeDefined()
    }
  })

  it("应解析 True Color 前景", () => {
    // 38;2;R;G;B — True Color
    const segments = parseAnsi("\x1b[38;2;255;0;0mBright Red\x1b[0m")
    const textSeg = segments.find((s) => s.text === "Bright Red")
    expect(textSeg).toBeDefined()
    if (textSeg) {
      expect(textSeg.fg).toBeDefined()
    }
  })

  it("应解析背景色", () => {
    const segments = parseAnsi("\x1b[41mRed BG\x1b[0m")
    const textSeg = segments.find((s) => s.text === "Red BG")
    expect(textSeg).toBeDefined()
    if (textSeg) {
      expect(textSeg.bg).toBeDefined()
    }
  })

  it("reset (0) 应重置所有样式", () => {
    const segments = parseAnsi("\x1b[1;31mBold Red\x1b[0m Plain")
    const plainSeg = segments.find((s) => s.text === " Plain")
    expect(plainSeg).toBeDefined()
    if (plainSeg) {
      expect(plainSeg.bold).toBeFalsy()
      expect(plainSeg.fg).toBeUndefined()
    }
  })
})

describe("segmentStyle — 段样式转 CSS", () => {
  it("应返回空对象（无样式时）", () => {
    const style = segmentStyle({ text: "hello" })
    expect(typeof style).toBe("object")
  })

  it("bold 样式应包含 font-weight", () => {
    const style = segmentStyle({ text: "bold", bold: true })
    // CSS numeric font-weight 700 is equivalent to "bold"
    expect(style).toHaveProperty("font-weight", "700")
  })

  it("前景色应包含 color", () => {
    const style = segmentStyle({ text: "red", fg: "#ff0000" })
    expect(style).toHaveProperty("color", "#ff0000")
  })

  it("背景色应包含 background-color", () => {
    const style = segmentStyle({ text: "bg", bg: "#0000ff" })
    expect(style).toHaveProperty("background-color", "#0000ff")
  })

  it("italic 样式应包含 font-style", () => {
    const style = segmentStyle({ text: "italic", italic: true })
    expect(style).toHaveProperty("font-style", "italic")
  })

  it("underline 样式应包含 text-decoration", () => {
    const style = segmentStyle({ text: "underline", underline: true })
    expect(style).toHaveProperty("text-decoration", "underline")
  })
})
