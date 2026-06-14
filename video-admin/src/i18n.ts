import { createI18n } from "vue-i18n"
import en from "./locales/en/translation.json"
import zh from "./locales/zh/translation.json"

const i18n = createI18n({
  legacy: false,
  locale: "en",
  fallbackLocale: "en",
  messages: { en, zh },
})

export default i18n
