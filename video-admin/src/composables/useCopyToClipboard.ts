import { ref } from "vue"

export function useCopyToClipboard() {
  const copiedText = ref<string | null>(null)

  async function copy(text: string) {
    try {
      await navigator.clipboard.writeText(text)
      copiedText.value = text
      setTimeout(() => {
        copiedText.value = null
      }, 2000)
    } catch {
      // Fallback
      const textarea = document.createElement("textarea")
      textarea.value = text
      textarea.style.position = "fixed"
      textarea.style.opacity = "0"
      document.body.appendChild(textarea)
      textarea.select()
      document.execCommand("copy")
      document.body.removeChild(textarea)
      copiedText.value = text
      setTimeout(() => {
        copiedText.value = null
      }, 2000)
    }
  }

  return { copiedText, copy }
}
