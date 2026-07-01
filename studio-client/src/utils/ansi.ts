/**
 * ANSI Escape Code Parser (Session 10)
 *
 * Parses terminal output containing ANSI SGR sequences into renderable
 * segments with foreground/background colors and style flags.
 *
 * Supported sequences:
 *   - 3/4-bit colors (30-37, 90-97 fg; 40-47, 100-107 bg)
 *   - 256-color (38;5;n, 48;5;n)
 *   - True color (38;2;r;g;b, 48;2;r;g;b)
 *   - Styles: bold (1), dim (2), italic (3), underline (4), reset (0)
 */

export interface AnsiSegment {
  /** Plain text content (ANSI codes stripped) */
  text: string
  /** Foreground color in CSS format */
  fg?: string
  /** Background color in CSS format */
  bg?: string
  bold?: boolean
  dim?: boolean
  italic?: boolean
  underline?: boolean
}

// ── Standard 16-color palette (xterm) ─────────────────────
const PALETTE_4BIT_FG: Record<number, string> = {
  30: "#000000", 31: "#c21b22", 32: "#00a154", 33: "#c98200",
  34: "#0055c3", 35: "#a31489", 36: "#00858b", 37: "#b6b6b6",
}
const PALETTE_4BIT_FG_BRIGHT: Record<number, string> = {
  90: "#666666", 91: "#e54733", 92: "#3dca51", 93: "#e6d92e",
  94: "#5a8ef3", 95: "#dc66c1", 96: "#51c8c7", 97: "#ffffff",
}
const PALETTE_4BIT_BG: Record<number, string> = {
  40: "#000000", 41: "#c21b22", 42: "#00a154", 43: "#c98200",
  44: "#0055c3", 45: "#a31489", 46: "#00858b", 47: "#b6b6b6",
}
const PALETTE_4BIT_BG_BRIGHT: Record<number, string> = {
  100: "#666666", 101: "#e54733", 102: "#3dca51", 103: "#e6d92e",
  104: "#5a8ef3", 105: "#dc66c1", 106: "#51c8c7", 107: "#ffffff",
}

// ── 256-color cube ────────────────────────────────────────
function ansi256Color(code: number): string {
  if (code < 16) {
    // System colors (same as 4-bit)
    const map: Record<number, string> = {
      0: "#000000", 1: "#c21b22", 2: "#00a154", 3: "#c98200",
      4: "#0055c3", 5: "#a31489", 6: "#00858b", 7: "#b6b6b6",
      8: "#666666", 9: "#e54733", 10: "#3dca51", 11: "#e6d92e",
      12: "#5a8ef3", 13: "#dc66c1", 14: "#51c8c7", 15: "#ffffff",
    }
    return map[code] ?? "#b6b6b6"
  }
  if (code < 232) {
    // 6×6×6 color cube
    const idx = code - 16
    const r = idx / 36 | 0
    const g = (idx % 36) / 6 | 0
    const b = idx % 6
    return `rgb(${r > 0 ? (r * 40) + 55 : 0},${g > 0 ? (g * 40) + 55 : 0},${b > 0 ? (b * 40) + 55 : 0})`
  }
  // Grayscale (232-255)
  const gray = (code - 232) * 10 + 8
  return `rgb(${gray},${gray},${gray})`
}

// ── Style bitmask ──────────────────────────────────────────
interface StyleState {
  fg?: string
  bg?: string
  bold: boolean
  dim: boolean
  italic: boolean
  underline: boolean
}

function cloneStyle(s: StyleState): StyleState {
  return { ...s }
}

// ── Sequence parser ────────────────────────────────────────
const ANSI_RE = /\x1b\[([0-9;]*)[a-zA-Z]/

/**
 * Parse an ANSI-encoded string into CSS-renderable segments.
 * Non-SGR escape sequences (cursor movement, etc.) are stripped.
 */
export function parseAnsi(input: string): AnsiSegment[] {
  const segments: AnsiSegment[] = []
  const current: StyleState = {
    bold: false,
    dim: false,
    italic: false,
    underline: false,
  }
  let textBuf = ""
  let pos = 0

  function flush(): void {
    if (textBuf.length > 0) {
      segments.push({
        text: textBuf,
        fg: current.fg,
        bg: current.bg,
        bold: current.bold,
        dim: current.dim,
        italic: current.italic,
        underline: current.underline,
      })
      textBuf = ""
    }
  }

  while (pos < input.length) {
    const ch = input[pos]
    if (ch === "\x1b" && input[pos + 1] === "[") {
      // ANSI escape sequence
      const m = input.slice(pos).match(ANSI_RE)
      if (m) {
        flush()

        const code = m[1] || "0"
        if (input[pos + m[0].length - 1] === "m") {
          // SGR (Select Graphic Rendition)
          applySgr(code, current)
        }
        // Non-m sequences (cursor, etc.) are silently stripped

        pos += m[0].length
        continue
      }
    }
    // Plain character
    textBuf += input[pos]
    pos++
  }

  flush()
  return segments
}

// ── SGR command processor ─────────────────────────────────
function applySgr(codeStr: string, style: StyleState): void {
  if (!codeStr) {
    // ESC[m = reset
    resetStyle(style)
    return
  }

  const params = codeStr.split(";").map(Number)

  let i = 0
  while (i < params.length) {
    const p = params[i]

    if (p === 0) {
      resetStyle(style)
    } else if (p === 1) {
      style.bold = true
    } else if (p === 2) {
      style.dim = true
    } else if (p === 3) {
      style.italic = true
    } else if (p === 4) {
      style.underline = true
    } else if (p >= 30 && p <= 37) {
      style.fg = PALETTE_4BIT_FG[p] ?? style.fg
    } else if (p >= 40 && p <= 47) {
      style.bg = PALETTE_4BIT_BG[p] ?? style.bg
    } else if (p >= 90 && p <= 97) {
      style.fg = PALETTE_4BIT_FG_BRIGHT[p] ?? style.fg
    } else if (p >= 100 && p <= 107) {
      style.bg = PALETTE_4BIT_BG_BRIGHT[p] ?? style.bg
    } else if (p === 38) {
      // Extended foreground color
      i = parseExtendedColor(params, i, style, "fg")
    } else if (p === 48) {
      // Extended background color
      i = parseExtendedColor(params, i, style, "bg")
    } else if (p === 39) {
      style.fg = undefined // default fg
    } else if (p === 49) {
      style.bg = undefined // default bg
    }
    // Unknown codes (22-29, 50-55, etc.) are ignored

    i++
  }
}

function parseExtendedColor(
  params: number[],
  startIdx: number,
  style: StyleState,
  target: "fg" | "bg",
): number {
  if (startIdx + 1 >= params.length) return startIdx

  const mode = params[startIdx + 1]
  if (mode === 5 && startIdx + 2 < params.length) {
    // 256 color: 38;5;n  or  48;5;n
    style[target] = ansi256Color(params[startIdx + 2])
    return startIdx + 2
  }
  if (mode === 2 && startIdx + 4 < params.length) {
    // True color: 38;2;r;g;b  or  48;2;r;g;b
    const r = params[startIdx + 2]
    const g = params[startIdx + 3]
    const b = params[startIdx + 4]
    style[target] = `rgb(${r},${g},${b})`
    return startIdx + 4
  }

  return startIdx
}

function resetStyle(style: StyleState): void {
  style.fg = undefined
  style.bg = undefined
  style.bold = false
  style.dim = false
  style.italic = false
  style.underline = false
}

/**
 * Quick check: does the text contain ANSI escape codes?
 */
export function hasAnsi(text: string): boolean {
  return text.includes("\x1b[")
}

/**
 * Strip all ANSI escape sequences from a string.
 */
export function stripAnsi(text: string): string {
  // ANI_RE without global flag only replaces first match; use split+join
  // or construct a global regex on the fly to strip all sequences.
  return text.replace(/\x1b\[[0-9;]*[a-zA-Z]/g, "")
}

/**
 * Convert an AnsiSegment to CSS style object for use in :style binding.
 */
export function segmentStyle(seg: AnsiSegment): Record<string, string> {
  const s: Record<string, string> = {}
  if (seg.fg) s.color = seg.fg
  if (seg.bg) s["background-color"] = seg.bg
  if (seg.bold) s["font-weight"] = "700"
  if (seg.dim) s.opacity = "0.6"
  if (seg.italic) s["font-style"] = "italic"
  if (seg.underline) s["text-decoration"] = "underline"
  return s
}
