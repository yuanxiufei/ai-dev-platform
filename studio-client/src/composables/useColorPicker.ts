/**
 * useColorPicker — VSCode 颜色选择器
 * 借鉴: VSCode colorPickerContribution
 * 检测代码中 hex/rgb/hsl/named 颜色值，提供预览和选色能力。
 */

export interface ColorInfo {
  hex: string; raw: string; column: number; length: number; name?: string
}

const NAMED_COLORS: Record<string, string> = {
  red: "#FF0000", green: "#008000", blue: "#0000FF", white: "#FFFFFF",
  black: "#000000", yellow: "#FFFF00", orange: "#FFA500", purple: "#800080",
  pink: "#FFC0CB", gray: "#808080", grey: "#808080", cyan: "#00FFFF",
  magenta: "#FF00FF", lime: "#00FF00", navy: "#000080", teal: "#008080",
  aqua: "#00FFFF", maroon: "#800000", olive: "#808000", silver: "#C0C0C0",
}

function rgbToHex(r: number, g: number, b: number): string {
  return "#" + [r, g, b].map(c => c.toString(16).padStart(2, "0")).join("")
}

function hslToHex(h: number, s: number, l: number): string {
  s /= 100; l /= 100
  const a = s * Math.min(l, 1 - l)
  const f = (n: number) => { const k = (n + h / 30) % 12; return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)) }
  return rgbToHex(Math.round(f(0) * 255), Math.round(f(8) * 255), Math.round(f(4) * 255))
}

export function extractColors(lineText: string): ColorInfo[] {
  const colors: ColorInfo[] = []
  const HEX_REGEX = /#([0-9a-fA-F]{3,8})\b(?!\w)/g
  let m: RegExpExecArray | null
  while ((m = HEX_REGEX.exec(lineText)) !== null) {
    let hex = m[0].toUpperCase()
    if (hex.length === 4) hex = "#" + hex[1]+hex[1]+hex[2]+hex[2]+hex[3]+hex[3]
    colors.push({ hex, raw: m[0], column: m.index + 1, length: m[0].length })
  }
  const RGB_REGEX = /rgb\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*\)/g
  while ((m = RGB_REGEX.exec(lineText)) !== null) {
    colors.push({ hex: rgbToHex(+m[1],+m[2],+m[3]), raw: m[0], column: m.index+1, length: m[0].length })
  }
  const HSL_REGEX = /hsl\(\s*(\d{1,3})\s*,\s*(\d{1,3})%\s*,\s*(\d{1,3})%\s*\)/g
  while ((m = HSL_REGEX.exec(lineText)) !== null) {
    colors.push({ hex: hslToHex(+m[1],+m[2],+m[3]), raw: m[0], column: m.index+1, length: m[0].length })
  }
  for (const [name, hex] of Object.entries(NAMED_COLORS)) {
    const re = new RegExp(`\\b${name}\\b`, "i")
    const rm = re.exec(lineText)
    if (rm && !colors.some(c => rm!.index >= c.column-1 && rm!.index <= c.column+c.length-1)) {
      colors.push({ hex, raw: name, column: rm.index+1, length: name.length, name })
    }
  }
  return colors
}

export function isColorDark(hex: string): boolean {
  const r = parseInt(hex.slice(1,3), 16); const g = parseInt(hex.slice(3,5), 16); const b = parseInt(hex.slice(5,7), 16)
  return (r * 299 + g * 587 + b * 114) / 1000 < 128
}

export function useColorPicker() {
  return { extractColors, isColorDark }
}
