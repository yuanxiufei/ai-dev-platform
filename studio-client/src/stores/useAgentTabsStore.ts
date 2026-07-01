/**
 * Agent Session Tab Store (Session 10)
 *
 * Multi-tab conversation management inspired by RooCode's Task Persistence.
 * Each tab is an independent session with its own messages, streaming state,
 * tool calls, and reasoning steps.
 *
 * Persisted to localStorage under key "agent_tabs_v1".
 */

import { defineStore } from "pinia"
import { computed, ref, watch } from "vue"
import type { ChatMessage, ToolCallRecord, ReasoningStep } from "@/types/studio"

// ── Types ─────────────────────────────────────────────────
export interface AgentTab {
  /** Unique tab id (UUID) */
  id: string
  /** Display label */
  title: string
  /** ISO timestamp of creation */
  createdAt: string
  /** Agent mode (craft/chat/architect/...) */
  mode: string
  /** Is this tab currently active? */
  active: boolean
  /** Pinned tabs stay in place */
  pinned: boolean
  /** Serialized messages (max 100 per tab for storage quota) */
  messagesJson?: string
}

interface PersistedTabs {
  tabs: AgentTab[]
  activeTabId: string
}

const STORAGE_KEY = "agent_tabs_v1"
const MAX_TABS = 15
const MAX_STORE_MSGS = 50

// ── Store ─────────────────────────────────────────────────
export const useAgentTabsStore = defineStore("agentTabs", () => {
  // ── State ──
  const tabs = ref<AgentTab[]>([])
  const activeTabId = ref<string>("")

  // ── Computed ──
  const activeTab = computed(() =>
    tabs.value.find((t) => t.id === activeTabId.value) ?? null,
  )
  const pinnedTabs = computed(() => tabs.value.filter((t) => t.pinned))
  const unpinnedTabs = computed(() => tabs.value.filter((t) => !t.pinned))

  // ── Persistence ──
  function loadTabs(): void {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      const data: PersistedTabs = JSON.parse(raw)
      if (Array.isArray(data.tabs) && data.tabs.length > 0) {
        tabs.value = data.tabs
        activeTabId.value = data.activeTabId || data.tabs[0].id
      }
    } catch {
      /* corrupted storage — start fresh */
    }
  }

  function persistTabs(): void {
    try {
      const payload: PersistedTabs = {
        tabs: tabs.value.map((t) => ({ ...t, messagesJson: undefined })),
        activeTabId: activeTabId.value,
      }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    } catch {
      /* storage full — silently drop */
    }
  }

  // Auto-persist on changes
  watch(
    [tabs, activeTabId],
    () => persistTabs(),
    { deep: true },
  )

  // ── Tab CRUD ──
  function createTab(title?: string, mode?: string): string {
    if (tabs.value.length >= MAX_TABS) {
      // Remove oldest unpinned tab
      const oldest = tabs.value
        .filter((t) => !t.pinned)
        .sort(
          (a, b) =>
            new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
        )
      if (oldest.length > 0) {
        removeTab(oldest[0].id)
      }
    }

    const id = crypto.randomUUID()
    const tab: AgentTab = {
      id,
      title: title || "新对话",
      createdAt: new Date().toISOString(),
      mode: mode || "craft",
      active: false,
      pinned: false,
    }

    tabs.value.push(tab)
    switchToTab(id)
    return id
  }

  function removeTab(tabId: string): void {
    const idx = tabs.value.findIndex((t) => t.id === tabId)
    if (idx < 0) return

    tabs.value.splice(idx, 1)

    // If removed tab was active, switch to next available
    if (activeTabId.value === tabId) {
      const next = tabs.value[Math.min(idx, tabs.value.length - 1)]
      activeTabId.value = next?.id ?? ""
    }

    // Ensure at least one tab exists
    if (tabs.value.length === 0) {
      createTab()
    }
  }

  function switchToTab(tabId: string): void {
    // Deactivate all
    tabs.value.forEach((t) => (t.active = false))
    const tab = tabs.value.find((t) => t.id === tabId)
    if (tab) {
      tab.active = true
      activeTabId.value = tabId
    }
  }

  function renameTab(tabId: string, title: string): void {
    const tab = tabs.value.find((t) => t.id === tabId)
    if (tab) {
      tab.title = title.slice(0, 60)
    }
  }

  function togglePin(tabId: string): void {
    const tab = tabs.value.find((t) => t.id === tabId)
    if (tab) {
      tab.pinned = !tab.pinned
    }
  }

  function updateTabMode(tabId: string, mode: string): void {
    const tab = tabs.value.find((t) => t.id === tabId)
    if (tab) {
      tab.mode = mode
    }
  }

  // ── Serialized message storage per tab ──
  function saveMessages(tabId: string, msgs: ChatMessage[]): void {
    const tab = tabs.value.find((t) => t.id === tabId)
    if (!tab) return
    const slice = msgs.slice(-MAX_STORE_MSGS)
    tab.messagesJson = JSON.stringify(slice)
    // Auto-rename tab from first user message
    if (msgs.length > 0 && tab.title === "新对话") {
      const firstUser = msgs.find((m) => m.role === "user")
      if (firstUser) {
        tab.title = firstUser.content.slice(0, 40)
      }
    }
  }

  function loadMessages(tabId: string): ChatMessage[] {
    const tab = tabs.value.find((t) => t.id === tabId)
    if (!tab?.messagesJson) return []
    try {
      return JSON.parse(tab.messagesJson) as ChatMessage[]
    } catch {
      return []
    }
  }

  // ── Init ──
  loadTabs()
  if (tabs.value.length === 0) {
    createTab()
  }

  return {
    // State
    tabs,
    activeTabId,
    activeTab,
    pinnedTabs,
    unpinnedTabs,

    // Actions
    createTab,
    removeTab,
    switchToTab,
    renameTab,
    togglePin,
    updateTabMode,
    saveMessages,
    loadMessages,
  }
})
