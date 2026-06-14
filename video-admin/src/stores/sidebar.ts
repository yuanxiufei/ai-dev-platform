import { defineStore } from "pinia"
import { ref } from "vue"
import { useIsMobile } from "@/composables/useMobile"

export const useSidebarStore = defineStore("sidebar", () => {
  const isMobile = useIsMobile()
  const open = ref(!isMobile.value)
  const openMobile = ref(false)

  const state = ref<"expanded" | "collapsed">(
    (localStorage.getItem("sidebar:state") as "expanded" | "collapsed") ||
      "expanded",
  )

  function setOpen(value: boolean) {
    open.value = value
  }

  function setOpenMobile(value: boolean) {
    openMobile.value = value
  }

  function toggleSidebar() {
    state.value = state.value === "expanded" ? "collapsed" : "expanded"
    localStorage.setItem("sidebar:state", state.value)
  }

  return { open, openMobile, state, setOpen, setOpenMobile, toggleSidebar }
})
