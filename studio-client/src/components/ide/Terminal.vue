<script setup lang="ts">
/**
 * IDE — Terminal Emulator (Session 10: ANSI-colored output)
 *
 * Renders terminal lines with full ANSI SGR support:
 *   - 3/4-bit, 256-color, true color
 *   - Bold, dim, italic, underline
 *   - Color-coded by type for non-ANSI lines
 *   - 14 terminal themes
 */
import { ref, computed, nextTick, onMounted } from "vue"
import { useIDEStore } from "@/stores/useIDEStore"
import { ChevronDown, Palette } from "lucide-vue-next"
import {
  parseAnsi,
  hasAnsi,
  segmentStyle,
  type AnsiSegment,
} from "@/utils/ansi"
import type { TerminalLine } from "@/types/ide"

interface TerminalTheme {
  id: string
  name: string
  bg: string
  fg: string
  accent: string
  green: string
  red: string
  yellow: string
  blue: string
  cyan: string
  magenta: string
  white: string
  brightBlack: string
  cursor: string
  selection: string
}

const TERMINAL_THEMES: TerminalTheme[] = [
  { id: "default", name: "Default Dark", bg: "#1a1a2e", fg: "#cdd6f4", accent: "#89b4fa", green: "#50fa7b", red: "#f38ba8", yellow: "#f9e2af", blue: "#89b4fa", cyan: "#89dceb", magenta: "#cba6f7", white: "#cdd6f4", brightBlack: "#45475a", cursor: "#f5f5f5", selection: "#45475a99" },
  { id: "solarized-dark", name: "Solarized Dark", bg: "#002b36", fg: "#839496", accent: "#268bd2", green: "#859900", red: "#dc322f", yellow: "#b58900", blue: "#268bd2", cyan: "#2aa198", magenta: "#d33682", white: "#eee8d5", brightBlack: "#586e75", cursor: "#839496", selection: "#073642" },
  { id: "solarized-light", name: "Solarized Light", bg: "#fdf6e3", fg: "#657b83", accent: "#268bd2", green: "#859900", red: "#dc322f", yellow: "#b58900", blue: "#268bd2", cyan: "#2aa198", magenta: "#d33682", white: "#073642", brightBlack: "#839496", cursor: "#657b83", selection: "#eee8d5" },
  { id: "tokyo-night", name: "Tokyo Night", bg: "#1a1b26", fg: "#a9b1d6", accent: "#7aa2f7", green: "#9ece6a", red: "#f7768e", yellow: "#e0af68", blue: "#7aa2f7", cyan: "#7dcfff", magenta: "#bb9af7", white: "#c0caf5", brightBlack: "#414868", cursor: "#c0caf5", selection: "#364A82" },
  { id: "dracula", name: "Dracula", bg: "#282a36", fg: "#f8f8f2", accent: "#bd93f9", green: "#50fa7b", red: "#ff5555", yellow: "#f1fa8c", blue: "#6272a4", cyan: "#8be9fd", magenta: "#ff79c6", white: "#f8f8f2", brightBlack: "#44475a", cursor: "#f8f8f2", selection: "#44475a" },
  { id: "monokai", name: "Monokai", bg: "#272822", fg: "#f8f8f2", accent: "#a6e22e", green: "#a6e22e", red: "#f92672", yellow: "#e6db74", blue: "#66d9ef", cyan: "#a1efe4", magenta: "#fd5ff0", white: "#f8f8f2", brightBlack: "#75715e", cursor: "#f8f8f2", selection: "#49483e" },
  { id: "nord", name: "Nord", bg: "#2e3440", fg: "#d8dee9", accent: "#88c0d0", green: "#a3be8c", red: "#bf616a", yellow: "#ebcb8b", blue: "#81a1c1", cyan: "#88c0d0", magenta: "#b48ead", white: "#e5e9f0", brightBlack: "#4c566a", cursor: "#d8dee9", selection: "#434c5e" },
  { id: "one-dark-pro", name: "One Dark Pro", bg: "#282c34", fg: "#abb2bf", accent: "#61afef", green: "#98c379", red: "#e06c75", yellow: "#d19a66", blue: "#61afef", cyan: "#56b6c2", magenta: "#c678dd", white: "#abb2bf", brightBlack: "#5c6370", cursor: "#528bff", selection: "#3e4452" },
  { id: "github-dark", name: "GitHub Dark", bg: "#0d1117", fg: "#c9d1d9", accent: "#58a6ff", green: "#3fb950", red: "#f85149", yellow: "#d2991d", blue: "#58a6ff", cyan: "#39c5cf", magenta: "#bc8cff", white: "#b1bac4", brightBlack: "#484f58", cursor: "#c9d1d9", selection: "#264f78" },
  { id: "github-light", name: "GitHub Light", bg: "#ffffff", fg: "#24292f", accent: "#0969da", green: "#1a7f37", red: "#cf222e", yellow: "#9a6700", blue: "#0969da", cyan: "#1b7c83", magenta: "#8250df", white: "#6e7781", brightBlack: "#57606a", cursor: "#24292f", selection: "#ddf4ff" },
  { id: "material", name: "Material", bg: "#263238", fg: "#eeffff", accent: "#82aaff", green: "#c3e88d", red: "#ff5370", yellow: "#ffcb6b", blue: "#82aaff", cyan: "#89ddff", magenta: "#c792ea", white: "#eeffff", brightBlack: "#546e7a", cursor: "#eeffff", selection: "#314549" },
  { id: "ayu-dark", name: "Ayu Dark", bg: "#0b0e14", fg: "#bfbdb6", accent: "#ff8f40", green: "#aad94c", red: "#f07178", yellow: "#ffb454", blue: "#59c2ff", cyan: "#95e6cb", magenta: "#d2a6ff", white: "#acb6bf", brightBlack: "#475266", cursor: "#f29668", selection: "#1f2430" },
  { id: "catppuccin", name: "Catppuccin", bg: "#1e1e2e", fg: "#cdd6f4", accent: "#89b4fa", green: "#a6e3a1", red: "#f38ba8", yellow: "#f9e2af", blue: "#89b4fa", cyan: "#94e2d5", magenta: "#cba6f7", white: "#cdd6f4", brightBlack: "#585b70", cursor: "#f5e0dc", selection: "#45475a" },
  { id: "vscode-dark", name: "VSCode Dark", bg: "#1e1e1e", fg: "#d4d4d4", accent: "#007acc", green: "#6a9955", red: "#f44747", yellow: "#d7ba7d", blue: "#569cd6", cyan: "#4ec9b0", magenta: "#c586c0", white: "#d4d4d4", brightBlack: "#808080", cursor: "#d4d4d4", selection: "#264f78" },
]

const store = useIDEStore()
const inputRef = ref<HTMLInputElement | null>(null)
const scrollRef = ref<HTMLDivElement | null>(null)
const currentInput = ref("")
const showThemeMenu = ref(false)

// Load saved theme or use default
const savedThemeId = localStorage.getItem('terminal_theme') || 'default'
const activeTheme = ref<TerminalTheme>(TERMINAL_THEMES.find(t => t.id === savedThemeId) || TERMINAL_THEMES[0])

const activeTerminal = computed(() =>
  store.terminalSessions.find((t) => t.id === store.activeTerminalId),
)

/** Apply theme CSS variables */
const themeStyle = computed(() => ({
  '--term-bg': activeTheme.value.bg,
  '--term-fg': activeTheme.value.fg,
  '--term-accent': activeTheme.value.accent,
  '--term-green': activeTheme.value.green,
  '--term-red': activeTheme.value.red,
  '--term-yellow': activeTheme.value.yellow,
  '--term-blue': activeTheme.value.blue,
  '--term-cyan': activeTheme.value.cyan,
  '--term-magenta': activeTheme.value.magenta,
  '--term-white': activeTheme.value.white,
  '--term-bright-black': activeTheme.value.brightBlack,
  '--term-cursor': activeTheme.value.cursor,
  '--term-selection': activeTheme.value.selection,
} as Record<string, string>))

function selectTheme(theme: TerminalTheme) {
  activeTheme.value = theme
  showThemeMenu.value = false
  localStorage.setItem('terminal_theme', theme.id)
  nextTick(() => inputRef.value?.focus())
}

function sb(): void {
  nextTick(() => {
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight
    }
  })
}

/**
 * Get ANSI segments for a line — prefers store pre-parsed segments,
 * falls back to on-demand parsing for compatibility.
 */
function getSegments(line: TerminalLine): AnsiSegment[] {
  if (line.segments && line.segments.length > 0) return line.segments
  if (hasAnsi(line.text)) {
    // On-demand fallback
    const segs = parseAnsi(line.text)
    line.segments = segs
    return segs
  }
  return []
}

onMounted(() => {
  nextTick(() => inputRef.value?.focus())
})

// ── Command execution (simulated local echo) ─────────────
function execute(): void {
  const cmd = currentInput.value.trim()
  if (!cmd) return

  store.addTerminalLine(
    `\n  ➜ ${activeTerminal?.cwd ?? "~/projects/ai-app"}`,
    "input",
  )
  store.addTerminalLine(cmd, "input")

  setTimeout(() => {
    if (cmd.startsWith("echo ")) {
      store.addTerminalLine(cmd.slice(5), "output")
    } else if (cmd === "cls" || cmd === "clear") {
      const t = store.terminalSessions.find((t) => t.active)
      if (t) t.lines = []
      return
    } else if (cmd === "pwd") {
      store.addTerminalLine(
        activeTerminal?.cwd ?? "~/projects/ai-app",
        "output",
      )
    } else if (cmd === "ls" || cmd === "dir") {
      store.addTerminalLine(
        "\n  drwxr-xr-x   ai_models/\n  drwxr-xr-x   backend/\n  -rw-r--r--  package.json\n  -rw-r--r--  README.md",
        "output",
      )
    } else if (cmd === "git status") {
      store.addTerminalLine(
        "On branch main\nChanges not staged:\n  modified: App.vue",
        "info",
      )
    } else if (
      cmd.startsWith("pnpm ") ||
      cmd.startsWith("npm ") ||
      cmd.startsWith("npm run")
    ) {
      store.addTerminalLine("", "output")
      store.addTerminalLine("> ai-app@1.0.0 dev", "info")
      store.addTerminalLine("> vite", "info")
      let step = 0
      const iv = setInterval(() => {
        step++
        const frames = [
          "⠋",
          "⠙",
          "⠹",
          "⠸",
          "⠼",
          "⠴",
          "⠦",
          "⠧",
          "⠇",
          "⠏",
        ]
        const s = frames[step % 10]
        store.terminalSessions.find((t) => t.active)?.lines.pop()
        store.addTerminalLine(
          `  ${s} VITE ready in ${420 + step * 10} ms`,
          "info",
        )
        sb()
        if (step > 5) {
          clearInterval(iv)
          store.addTerminalLine("", "output")
          store.addTerminalLine(
            "  ➜ Local: http://localhost:5173/",
            "success",
          )
          store.addTerminalLine(
            "  ➜ Network: use --host to expose",
            "output",
          )
          sb()
        }
      }, 200)
    } else {
      store.addTerminalLine(`${cmd}: command not found`, "error")
    }
    store.addTerminalLine("", "output")
    sb()
  }, 150)
  currentInput.value = ""
}
</script>

<template>
  <div
    class="h-full flex flex-col font-mono text-[12px]"
    :style="themeStyle"
    style="background:var(--term-bg, #1a1a2e); color:var(--term-fg, #cdd6f4);"
  >
    <!-- Session Tabs + Theme Selector (VSCode terminal bar style) -->
    <div
      class="flex items-center shrink-0 border-b border-[var(--color-ide-border)]"
      style="background:var(--color-ide-bg-secondary); height:28px;"
    >
      <!-- Terminal tabs -->
      <div class="flex-1 flex items-center h-full min-w-0">
        <button
          v-for="term in store.terminalSessions"
          :key="term.id"
          class="flex items-center gap-1 px-3 h-full text-[11px] uppercase tracking-wide relative font-semibold transition-colors shrink-0"
          :class="term.active ? 'text-[var(--color-ide-text)]' : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]'"
          @click="
            store.terminalSessions.forEach(
              (t) => (t.active = t.id === term.id),
            );
            sb();
            nextTick(() => inputRef.value?.focus())
          "
        >
          {{ term.title }}
          <div v-if="term.active" class="absolute bottom-0 left-3 right-3" style="height:1px; background:var(--term-accent, #89b4fa);" />
        </button>
      </div>

      <!-- Theme selector (compact inline) -->
      <div class="relative shrink-0">
        <button
          class="flex items-center gap-1 px-2 h-full text-[10px] font-medium transition-colors"
          style="color:var(--color-ide-text-dim);"
          :style="{ color: showThemeMenu ? 'var(--term-accent)' : '' }"
          @click="showThemeMenu = !showThemeMenu"
          title="终端主题"
        >
          <Palette :size="12" /> {{ activeTheme.name }}
          <ChevronDown :size="8" />
        </button>
        <Transition name="fade">
          <div v-if="showThemeMenu"
            class="absolute right-0 top-full z-50 mt-0.5 py-1 min-w-[160px] max-h-80 overflow-y-auto rounded-md shadow-xl border"
            style="background:var(--color-ide-surface); border-color:var(--color-ide-border);">
            <button
              v-for="theme in TERMINAL_THEMES"
              :key="theme.id"
              @click="selectTheme(theme)"
              class="w-full text-left px-3 py-1.5 text-[11px] flex items-center gap-2 transition-colors hover:bg-[var(--color-ide-surface-hover)]"
              style="color:var(--color-ide-text);"
            >
              <!-- Color preview dot -->
              <span class="w-3 h-3 rounded-full border shrink-0" style="background:var(--color-ide-border);"
                :style="{ background: theme.bg, borderColor: theme.fg + '40' }" />
              <span class="flex-1">{{ theme.name }}</span>
              <svg v-if="theme.id === activeTheme.id" width="10" height="8" viewBox="0 0 12 9" fill="none">
                <path d="M1 3l4 4 6-6" stroke="var(--term-accent)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </button>
          </div>
        </Transition>
      </div>
    </div>

    <!-- Output Area -->
    <div ref="scrollRef" class="flex-1 overflow-y-auto p-3 space-y-0">
      <template v-if="activeTerminal">
        <div
          v-for="line in activeTerminal.lines"
          :key="line.id"
          class="whitespace-pre-wrap break-all text-xs leading-relaxed"
        >
          <!-- Session 10: ANSI-rendered segments -->
          <template v-if="getSegments(line).length > 0">
            <span
              v-for="(seg, si) in getSegments(line)"
              :key="si"
              :style="segmentStyle(seg)"
            >{{ seg.text }}</span>
          </template>
          <!-- Fallback: color by type -->
          <template v-else>
            <span
              :style="{
                color:
                  line.type === 'success'
                    ? 'var(--term-green, #50fa7b)'
                    : line.type === 'error'
                      ? 'var(--term-red, #f38ba8)'
                      : line.type === 'info'
                        ? 'var(--term-yellow, #f9e2af)'
                        : line.type === 'input'
                          ? 'var(--term-blue, #60A5FA)'
                          : 'var(--term-fg, #cdd6f4)',
              }"
            >{{ line.text }}</span>
          </template>
        </div>
      </template>

      <!-- Input Prompt -->
      <div class="flex items-center pt-1">
        <span class="mr-2 shrink-0 select-none" style="color:var(--term-accent, #89b4fa);">➜</span>
        <span
          class="shrink-0 mr-2 text-xs select-none"
          style="font-family:'JetBrains Mono','Cascadia Code',monospace;font-size:11px;color:var(--term-fg, #cdd6f4);opacity:0.6;"
        >
          {{ activeTerminal?.cwd ?? "~/projects/ai-app" }}
        </span>
        <input
          ref="inputRef"
          v-model="currentInput"
          type="text"
          class="flex-1 bg-transparent outline-none"
          :style="{
            caretColor: 'var(--term-accent, #89b4fa)',
            color: 'var(--term-fg, #cdd6f4)',
            fontFamily: `'JetBrains Mono','Cascadia Code',monospace`,
            fontSize: '12px',
          }"
          spellcheck="false"
          autocomplete="off"
          autofocus
          @keydown.enter="execute"
          @focus="sb"
        />
      </div>
    </div>
  </div>
</template>
