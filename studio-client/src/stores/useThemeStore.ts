/**
 * CodeBuddy IDE — Theme Store (Session 10)
 *
 * Three built-in themes: dark (default), light, high-contrast.
 * Persisted to localStorage under key "codebuddy_theme".
 * Provides reactive CSS class application and Monaco theme mapping.
 */

import { ref, computed, watch } from "vue"
import { defineStore } from "pinia"

export type ThemeId = "dark" | "light" | "high-contrast"

export interface ThemeDefinition {
  id: ThemeId
  label: string
  /** CSS class applied to <html> */
  htmlClass: string
  /** Monaco Editor built-in theme name */
  monacoTheme: string
  /** Icon: lucide icon name */
  icon: "Sun" | "Moon" | "Contrast"
}

const THEMES: Record<ThemeId, ThemeDefinition> = {
  dark: {
    id: "dark",
    label: "CodeBuddy Dark",
    htmlClass: "theme-dark",
    monacoTheme: "codebuddy-dark",
    icon: "Moon",
  },
  light: {
    id: "light",
    label: "CodeBuddy Light",
    htmlClass: "theme-light",
    monacoTheme: "vs",
    icon: "Sun",
  },
  "high-contrast": {
    id: "high-contrast",
    label: "高对比度",
    htmlClass: "theme-high-contrast",
    monacoTheme: "hc-black",
    icon: "Contrast",
  },
}

const STORAGE_KEY = "codebuddy_theme"

function loadTheme(): ThemeId {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw && (raw === "dark" || raw === "light" || raw === "high-contrast")) {
      return raw
    }
  } catch {
    /* localStorage unavailable */
  }
  return "dark"
}

function persistTheme(id: ThemeId): void {
  try {
    localStorage.setItem(STORAGE_KEY, id)
  } catch {
    /* ignore */
  }
}

/**
 * Apply theme HTML class to document root.
 * Removes all theme-* classes, then adds the active one.
 */
function applyHtmlClass(id: ThemeId): void {
  const root = document.documentElement
  root.classList.remove("theme-dark", "theme-light", "theme-high-contrast")
  root.classList.add(THEMES[id].htmlClass)
}

export const useThemeStore = defineStore("theme", () => {
  const active = ref<ThemeId>(loadTheme())
  const definition = computed(() => THEMES[active.value])
  const themes = computed(() => Object.values(THEMES))

  // ── Apply on creation ──
  applyHtmlClass(active.value)

  // ── Persist + react on change ──
  watch(active, (id) => {
    persistTheme(id)
    applyHtmlClass(id)
  })

  function setTheme(id: ThemeId): void {
    if (THEMES[id]) {
      active.value = id
    }
  }

  function cycleTheme(): void {
    const order: ThemeId[] = ["dark", "light", "high-contrast"]
    const idx = order.indexOf(active.value)
    active.value = order[(idx + 1) % order.length]
  }

  function isDark(): boolean {
    return active.value === "dark"
  }

  return {
    active,
    definition,
    themes,
    setTheme,
    cycleTheme,
    isDark,
  }
})
