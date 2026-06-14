import { defineStore } from "pinia"
import { ref, watchEffect } from "vue"

export type ThemeMode = "dark" | "light" | "system"

export const useThemeStore = defineStore("theme", () => {
  const theme = ref<ThemeMode>(
    (localStorage.getItem("theme") as ThemeMode) || "system",
  )
  const resolvedTheme = ref<"dark" | "light">("light")

  function applyTheme() {
    const root = document.documentElement
    const resolved: "dark" | "light" =
      theme.value === "system"
        ? window.matchMedia("(prefers-color-scheme: dark)").matches
          ? "dark"
          : "light"
        : theme.value
    resolvedTheme.value = resolved
    root.classList.toggle("dark", resolved === "dark")
    localStorage.setItem("theme", theme.value)
  }

  function setTheme(value: ThemeMode) {
    theme.value = value
    applyTheme()
  }

  applyTheme()

  watchEffect((onCleanup) => {
    const mq = window.matchMedia("(prefers-color-scheme: dark)")
    const handler = () => {
      if (theme.value === "system") applyTheme()
    }
    mq.addEventListener("change", handler)
    onCleanup(() => mq.removeEventListener("change", handler))
  })

  return { theme, resolvedTheme, setTheme, applyTheme }
})
