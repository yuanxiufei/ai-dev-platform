/**
 * i18n 国际化系统 — 轻量、响应式、零依赖
 *
 * 用法 (组件内):
 *   const { t, locale, setLocale } = useI18n()
 *   t('chat.newChat')  // "新建对话" / "New Chat"
 *   t('editor.goToLine', { line: 42 })  // "转到行 42..."
 *
 * 用法 (组件外):
 *   import { i18n } from '@/i18n'
 *   i18n.t('common.ok')  // "确定" / "OK"
 */

import { ref, computed } from "vue"
import zhCN from "./locales/zh-CN"
import enUS from "./locales/en-US"

export type LocaleCode = "zh-CN" | "en-US"

type LocaleDict = Record<string, unknown>

const LOCALE_DATA: Record<LocaleCode, LocaleDict> = {
  "zh-CN": zhCN as unknown as LocaleDict,
  "en-US": enUS as unknown as LocaleDict,
}

const FALLBACK: LocaleCode = "en-US"
const AVAILABLE: LocaleCode[] = ["zh-CN", "en-US"]
const DISPLAY_NAMES: Record<LocaleCode, string> = {
  "zh-CN": "中文",
  "en-US": "English",
}

// ── Reactive state ──
const _locale = ref<LocaleCode>(
  (localStorage.getItem("app_locale") as LocaleCode) || "zh-CN",
)

// ── Core translate ──
function resolveValue(obj: unknown, path: string): string | undefined {
  const keys = path.split(".")
  let current: unknown = obj
  for (const k of keys) {
    if (current == null || typeof current !== "object") return undefined
    current = (current as Record<string, unknown>)[k]
  }
  return typeof current === "string" ? current : undefined
}

function applyParams(template: string, params?: Record<string, string | number>): string {
  if (!params) return template
  return template.replace(/\{(\w+)\}/g, (_, key) => {
    return params[key] !== undefined ? String(params[key]) : `{${key}}`
  })
}

function doTranslate(
  key: string,
  params?: Record<string, string | number>,
  localeOverride?: LocaleCode,
): string {
  const loc = localeOverride ?? _locale.value

  let val = resolveValue(LOCALE_DATA[loc], key)
  if (val === undefined && loc !== FALLBACK) {
    val = resolveValue(LOCALE_DATA[FALLBACK], key)
  }
  if (val === undefined) {
    console.warn(`[i18n] ✗ Missing: "${key}"`)
    return key
  }

  return applyParams(val, params)
}

// ── Exports ──

/** Singleton i18n (non-reactive, for outside components) */
export const i18n = {
  t: doTranslate,
  get locale(): LocaleCode {
    return _locale.value
  },
  setLocale(code: LocaleCode) {
    _locale.value = code
    localStorage.setItem("app_locale", code)
  },
  localeName() {
    return DISPLAY_NAMES[_locale.value]
  },
  available: AVAILABLE,
  names: DISPLAY_NAMES,
}

/** Vue composable (reactive inside components) */
export function useI18n() {
  return {
    /** Translate function */
    t: doTranslate,
    /** Reactive current locale */
    locale: computed(() => _locale.value),
    /** Reactive locale display name */
    localeName: computed(() => DISPLAY_NAMES[_locale.value]),
    /** Available locale codes */
    availableLocales: AVAILABLE,
    /** Set locale and persist */
    setLocale(code: LocaleCode) {
      _locale.value = code
      localStorage.setItem("app_locale", code)
    },
    /** Locale names map */
    localeNames: DISPLAY_NAMES,
  }
}
