/**
 * CodeBuddy IDE — Enhanced Theme Store
 *
 * Theme presets: dark | light | high-contrast | system | vscode-dark+ | one-dark-pro |
 *                monokai | solarized-dark | solarized-light | dracula | nord | tokyo-night
 * Persisted to localStorage. Reactive HTML class + Monaco mapping.
 */
import { ref, computed, watch, onMounted, onUnmounted } from "vue"
import { defineStore } from "pinia"

export type ThemeId =
  | "dark"
  | "light"
  | "high-contrast"
  | "system"
  | "vscode-dark-plus"
  | "one-dark-pro"
  | "monokai"
  | "solarized-dark"
  | "solarized-light"
  | "dracula"
  | "nord"
  | "tokyo-night"

export type IconThemeId = "material" | "seti" | "vscode-icons" | "minimal"

export interface ThemeDefinition {
  id: ThemeId
  label: string
  labelZh: string
  htmlClass: string
  monacoTheme: string
  /** Category for grouping in UI */
  category: "builtin" | "dark" | "light"
}

export interface IconThemeDefinition {
  id: IconThemeId
  label: string
  labelZh: string
  /** Icon mapping: file extension → lucide icon name */
  fileIcons: Record<string, string>
  /** Default file icon */
  defaultFileIcon: string
  /** Default folder icons */
  folderOpenIcon: string
  folderClosedIcon: string
}

const THEMES: ThemeDefinition[] = [
  { id: "system", label: "System", labelZh: "跟随系统", htmlClass: "theme-system", monacoTheme: "vs-dark", category: "builtin" },
  { id: "dark", label: "CodeBuddy Dark", labelZh: "CodeBuddy 暗色", htmlClass: "theme-dark", monacoTheme: "codebuddy-dark", category: "builtin" },
  { id: "light", label: "CodeBuddy Light", labelZh: "CodeBuddy 亮色", htmlClass: "theme-light", monacoTheme: "vs", category: "builtin" },
  { id: "high-contrast", label: "High Contrast", labelZh: "高对比度", htmlClass: "theme-high-contrast", monacoTheme: "hc-black", category: "builtin" },
  { id: "vscode-dark-plus", label: "Dark+ (VSCode)", labelZh: "Dark+ 暗色", htmlClass: "theme-vscode-dark-plus", monacoTheme: "vs-dark", category: "dark" },
  { id: "one-dark-pro", label: "One Dark Pro", labelZh: "One Dark Pro", htmlClass: "theme-one-dark-pro", monacoTheme: "one-dark-pro", category: "dark" },
  { id: "monokai", label: "Monokai", labelZh: "Monokai", htmlClass: "theme-monokai", monacoTheme: "monokai", category: "dark" },
  { id: "solarized-dark", label: "Solarized Dark", labelZh: "Solarized（暗）", htmlClass: "theme-solarized-dark", monacoTheme: "solarized-dark", category: "dark" },
  { id: "dracula", label: "Dracula", labelZh: "Dracula", htmlClass: "theme-dracula", monacoTheme: "dracula", category: "dark" },
  { id: "nord", label: "Nord", labelZh: "Nord", htmlClass: "theme-nord", monacoTheme: "nord", category: "dark" },
  { id: "tokyo-night", label: "Tokyo Night", labelZh: "Tokyo Night", htmlClass: "theme-tokyo-night", monacoTheme: "tokyo-night", category: "dark" },
  { id: "solarized-light", label: "Solarized Light", labelZh: "Solarized（亮）", htmlClass: "theme-solarized-light", monacoTheme: "solarized-light", category: "light" },
]

const THEME_MAP: Record<string, ThemeDefinition> = {}
THEMES.forEach(t => (THEME_MAP[t.id] = t))

/** Session 35: File Icon Theme Definitions */
const ICON_THEMES: IconThemeDefinition[] = [
  {
    id: "material",
    label: "Material Icon Theme",
    labelZh: "Material 图标主题",
    fileIcons: {
      ".ts": "FileCode", ".tsx": "FileCode", ".js": "FileCode", ".jsx": "FileCode",
      ".vue": "FileCode", ".rs": "FileCode", ".py": "FileCode", ".go": "FileCode",
      ".java": "FileCode", ".cpp": "FileCode", ".c": "FileCode", ".h": "FileCode",
      ".css": "FileCode", ".scss": "FileCode", ".less": "FileCode",
      ".html": "FileCode", ".htm": "FileCode", ".xml": "FileCode",
      ".json": "FileJson", ".jsonc": "FileJson", ".yaml": "FileJson", ".yml": "FileJson",
      ".md": "FileText", ".txt": "FileText", ".log": "FileText",
      ".png": "FileImage", ".jpg": "FileImage", ".jpeg": "FileImage", ".gif": "FileImage",
      ".svg": "FileImage", ".ico": "FileImage", ".webp": "FileImage",
      ".zip": "Archive", ".tar": "Archive", ".gz": "Archive", ".rar": "Archive", ".7z": "Archive",
      ".toml": "FileJson", ".lock": "FileJson",
      ".env": "FileText", ".gitignore": "FileText", ".dockerignore": "FileText",
    },
    defaultFileIcon: "File",
    folderOpenIcon: "FolderOpen",
    folderClosedIcon: "FolderClosed",
  },
  {
    id: "seti",
    label: "Seti",
    labelZh: "Seti 图标主题",
    fileIcons: {
      ".ts": "FileType2", ".tsx": "FileType2", ".js": "FileType2", ".jsx": "FileType2",
      ".vue": "FileType", ".py": "FileType", ".go": "FileType",
      ".json": "FileJson", ".md": "FileText",
      ".css": "FileCode", ".scss": "FileCode",
      ".html": "FileCode",
    },
    defaultFileIcon: "File",
    folderOpenIcon: "FolderOpen",
    folderClosedIcon: "FolderClosed",
  },
  {
    id: "vscode-icons",
    label: "VSCode Icons",
    labelZh: "VSCode 图标主题",
    fileIcons: {
      ".ts": "FileCode2", ".tsx": "FileCode2", ".js": "FileCode2", ".jsx": "FileCode2",
      ".vue": "FileCode2", ".py": "FileCode2", ".go": "FileCode2",
      ".json": "FileJson2", ".md": "FileText",
      ".css": "FileCode2", ".html": "FileCode2",
    },
    defaultFileIcon: "File",
    folderOpenIcon: "FolderOpen",
    folderClosedIcon: "FolderClosed",
  },
  {
    id: "minimal",
    label: "Minimal",
    labelZh: "极简图标",
    fileIcons: {},
    defaultFileIcon: "File",
    folderOpenIcon: "Folder",
    folderClosedIcon: "Folder",
  },
]

const ICON_THEME_MAP: Record<string, IconThemeDefinition> = {}
ICON_THEMES.forEach(t => (ICON_THEME_MAP[t.id] = t))

const STORAGE_KEY = "codebuddy_theme"
const ICON_STORAGE_KEY = "codebuddy_icon_theme"
const VALID_IDS = new Set(THEMES.map(t => t.id))

function loadTheme(): ThemeId {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw && VALID_IDS.has(raw)) return raw as ThemeId
  } catch { /* ignore */ }
  return "dark"
}

function persist(id: ThemeId): void {
  try {
    localStorage.setItem(STORAGE_KEY, id)
  } catch { /* ignore */ }
}

/** Detect OS color scheme */
function osPrefersDark(): boolean {
  if (typeof window === "undefined") return true
  return window.matchMedia("(prefers-color-scheme: dark)").matches
}

function resolveAppliedId(id: ThemeId): "dark" | "light" | "high-contrast" {
  if (id === "system") return osPrefersDark() ? "dark" : "light"
  // All dark-category themes use "dark" base
  const def = THEME_MAP[id]
  if (def?.category === "dark") return "dark"
  if (def?.category === "light") return "light"
  return id === "high-contrast" ? "high-contrast" : "dark"
}

function applyHtmlClass(def: ThemeDefinition, actualThemeId: "dark" | "light" | "high-contrast"): void {
  const root = document.documentElement
  // Remove all theme classes
  const toRemove: string[] = []
  root.classList.forEach(c => {
    if (c.startsWith("theme-")) toRemove.push(c)
  })
  toRemove.forEach(c => root.classList.remove(c))

  // Add the specific theme class
  root.classList.add(def.htmlClass)

  // For system mode, also add the resolved base class
  if (def.id === "system") {
    root.classList.add(`theme-${actualThemeId}`)
  }
  // For dark-category themes that aren't "dark", add theme-dark for base styles
  else if (def.category === "dark" && def.id !== "dark") {
    root.classList.add("theme-dark")
  }
}

export const useThemeStore = defineStore("theme", () => {
  const active = ref<ThemeId>(loadTheme())
  const appliedType = ref<"dark" | "light" | "high-contrast">(resolveAppliedId(active.value))

  // Session 35: Icon theme state
  const activeIconTheme = ref<IconThemeId>(loadIconTheme())
  const iconDefinition = computed(() => ICON_THEME_MAP[activeIconTheme.value])
  const allIconThemes = computed(() => ICON_THEMES)

  const definition = computed(() => THEME_MAP[active.value])
  const allThemes = computed(() => THEMES)

  // Grouped for UI
  const builtinThemes = computed(() => THEMES.filter(t => t.category === "builtin"))
  const darkThemes = computed(() => THEMES.filter(t => t.category === "dark"))
  const lightThemes = computed(() => THEMES.filter(t => t.category === "light"))

  // Apply on creation (with no-transition to prevent flash)
  if (typeof document !== "undefined") {
    document.documentElement.classList.add("no-transitions")
  }
  applyHtmlClass(THEME_MAP[active.value], appliedType.value)

  // Remove no-transitions after a frame
  if (typeof window !== "undefined") {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document.documentElement.classList.remove("no-transitions")
      })
    })
  }

  // Persist + react
  watch(active, (id) => {
    persist(id)
    const def = THEME_MAP[id]
    appliedType.value = resolveAppliedId(id)
    applyHtmlClass(def, appliedType.value)
  })

  // Listen system color scheme changes for "system" mode
  let mediaQuery: MediaQueryList | null = null

  function handleSystemChange(e: MediaQueryListEvent): void {
    if (active.value === "system") {
      appliedType.value = e.matches ? "dark" : "light"
      const def = THEME_MAP["system"]
      applyHtmlClass(def, appliedType.value)
    }
  }

  if (typeof window !== "undefined") {
    mediaQuery = window.matchMedia("(prefers-color-scheme: dark)")
    mediaQuery.addEventListener("change", handleSystemChange)
  }

  function setTheme(id: ThemeId): void {
    if (THEME_MAP[id]) {
      active.value = id
    }
  }

  /** Cycle through all visible themes in order: builtin → dark → light */
  function cycleTheme(): void {
    const order: ThemeId[] = [
      "dark", "vscode-dark-plus", "one-dark-pro", "monokai",
      "solarized-dark", "dracula", "nord", "tokyo-night",
      "light", "solarized-light", "high-contrast", "system",
    ]
    const idx = order.indexOf(active.value)
    active.value = order[(idx + 1) % order.length]
  }

  function isDark(): boolean {
    return appliedType.value === "dark" || (active.value === "system" && osPrefersDark())
  }

  // Session 35: Icon theme functions
  function loadIconTheme(): IconThemeId {
    try {
      const raw = localStorage.getItem(ICON_STORAGE_KEY)
      if (raw && ICON_THEME_MAP[raw]) return raw as IconThemeId
    } catch { /* ignore */ }
    return "material"
  }

  function setIconTheme(id: IconThemeId): void {
    if (ICON_THEME_MAP[id]) {
      activeIconTheme.value = id
      try { localStorage.setItem(ICON_STORAGE_KEY, id) } catch { /* ignore */ }
    }
  }

  return {
    active,
    appliedType,
    definition,
    allThemes,
    builtinThemes,
    darkThemes,
    lightThemes,
    setTheme,
    cycleTheme,
    isDark,
    // Icon themes
    activeIconTheme,
    iconDefinition,
    allIconThemes,
    setIconTheme,
  }
})
