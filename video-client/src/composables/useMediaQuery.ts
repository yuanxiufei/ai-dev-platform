import { ref, onMounted, onUnmounted } from 'vue'

export function useMediaQuery(query: string) {
  const matches = ref(false)

  let mql: MediaQueryList | null = null

  function handler(e: MediaQueryListEvent) {
    matches.value = e.matches
  }

  onMounted(() => {
    mql = window.matchMedia(query)
    matches.value = mql.matches
    mql.addEventListener('change', handler)
  })

  onUnmounted(() => {
    mql?.removeEventListener('change', handler)
  })

  return matches
}

export function useIsMobile() {
  return useMediaQuery('(max-width: 767px)')
}

export function useIsTablet() {
  return useMediaQuery('(min-width: 768px) and (max-width: 1023px)')
}
