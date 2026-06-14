import { onMounted, onUnmounted, ref } from "vue"

const MOBILE_BREAKPOINT = 768

export function useIsMobile() {
  const isMobile = ref(window.innerWidth < MOBILE_BREAKPOINT)

  function onResize() {
    isMobile.value = window.innerWidth < MOBILE_BREAKPOINT
  }

  onMounted(() => {
    window.addEventListener("resize", onResize)
    onResize()
  })

  onUnmounted(() => {
    window.removeEventListener("resize", onResize)
  })

  return isMobile
}
