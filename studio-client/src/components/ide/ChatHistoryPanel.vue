<script setup lang="ts">
/**
 * CodeBuddy IDE — Chat History Panel
 *
 * ChatGPT 风格左侧历史对话列表：
 * - 按时间分组（今天/昨天/本周/更早）
 * - 搜索过滤
 * - 点击切换对话 / 重命名 / 删除
 * - "新建对话" 按钮
 */
import { computed, nextTick, ref, watch } from "vue"
import { MessageSquare, Plus, Search, Trash2, X, Check, Pencil, Pin } from "lucide-vue-next"
import { useAgentTabsStore } from "@/stores/useAgentTabsStore"

const _props = defineProps<{
  modelValue: boolean
  currentTabId: string
}>()

const emit = defineEmits<{
  (e: "update:modelValue", v: boolean): void
  (e: "switch-tab", tabId: string): void
  (e: "create-tab"): void
  (e: "delete-tab", tabId: string): void
  (e: "rename-tab", tabId: string, title: string): void
  (e: "toggle-pin", tabId: string): void
}>()

const store = useAgentTabsStore()
const searchQuery = ref("")
const editingTabId = ref<string | null>(null)
const editTitle = ref("")

const SEP = "—"

// 过滤 & 排序
const sortedTabs = computed(() => {
  let list = store.tabs.filter(t => {
    if (!searchQuery.value.trim()) return true
    const q = searchQuery.value.toLowerCase()
    return t.title.toLowerCase().includes(q)
  })
  // Pinned first, then by createdAt desc
  return list.slice().sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
    return new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
  })
})

// 时间分组
type Group = { label: string; tabs: typeof sortedTabs.value }

const groupedTabs = computed<Group[]>(() => {
  const map = new Map<string, typeof sortedTabs.value>()
  const now = new Date()

  for (const tab of sortedTabs.value) {
    const d = new Date(tab.createdAt)
    let key: string

    if (isSameDay(d, now)) {
      key = "今天"
    } else if (isSameDay(d, shiftDay(now, -1))) {
      key = "昨天"
    } else if (d.getTime() > shiftDay(now, -7).getTime()) {
      key = "本周"
    } else {
      key = "更早"
    }

    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(tab)
  }

  const order = ["今天", "昨天", "本周", "更早"]
  const groups: Group[] = []
  for (const label of order) {
    if (map.has(label)) groups.push({ label, tabs: map.get(label)! })
  }
  return groups
})

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear()
    && a.getMonth() === b.getMonth()
    && a.getDate() === b.getDate()
}

function shiftDay(d: Date, days: number): Date {
  const n = new Date(d)
  n.setDate(n.getDate() + days)
  return n
}

function formatDate(ts: string): string {
  const d = new Date(ts)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`
}

function startRename(tab: any): void {
  editingTabId.value = tab.id
  editTitle.value = tab.title
  nextTick(() => {
    const el = document.querySelector(`[data-edit-id="${tab.id}"]`) as HTMLInputElement
    el?.focus()
    el?.select()
  })
}

function commitRename(): void {
  if (editingTabId.value && editTitle.value.trim()) {
    emit("rename-tab", editingTabId.value, editTitle.value.trim())
  }
  editingTabId.value = null
}

function cancelRename(): void {
  editingTabId.value = null
}

function handleClick(tabId: string): void {
  if (tabId !== _props.currentTabId) {
    emit("switch-tab", tabId)
  }
}

function handleDelete(tabId: string, e: MouseEvent): void {
  e.stopPropagation()
  emit("delete-tab", tabId)
}
</script>

<template>
  <div
    class="flex flex-col h-full overflow-hidden border-r select-none"
    :class="modelValue ? 'w-56 min-w-[180px]' : 'w-0 min-w-0 overflow-hidden'"
    style="border-color: var(--color-ide-border); background: var(--color-ide-bg-secondary); transition: width 0.15s ease;"
  >
    <div class="h-full flex flex-col" :class="modelValue ? '' : 'hidden'">
      <!-- 新建对话 + 搜索 -->
      <div class="shrink-0 p-2 space-y-1.5">
        <button
          class="w-full flex items-center gap-2 px-2.5 py-1.5 rounded text-[11px] font-medium transition-all"
          style="background: var(--color-ide-accent); color: #fff;"
          @click="emit('create-tab')"
        >
          <Plus :size="13" />
          <span>新建对话</span>
        </button>
        <div class="relative">
          <Search :size="12" class="absolute left-2 top-1/2 -translate-y-1/2 pointer-events-none" style="color: var(--color-ide-text-dim); opacity: 0.5;" />
          <input
            v-model="searchQuery"
            placeholder="搜索对话..."
            class="w-full h-7 pl-6.5 pr-2 rounded text-[11px] outline-none border border-transparent focus:border-[var(--color-ide-accent)]"
            style="background: var(--color-editor-bg); color: var(--color-ide-text);"
          />
        </div>
      </div>

      <!-- 历史列表（按时间分组） -->
      <div class="flex-1 overflow-y-auto overflow-x-hidden px-1.5 pb-1" style="scrollbar-width: thin;">
        <template v-for="group in groupedTabs" :key="group.label">
          <div class="text-[9px] uppercase tracking-wider px-2.5 pt-2 pb-1 font-medium" style="color: var(--color-ide-text-dim); opacity: 0.5;">
            {{ group.label }}
          </div>
          <div
            v-for="tab in group.tabs"
            :key="tab.id"
            class="group flex items-center gap-1.5 px-2 py-1.5 rounded cursor-pointer text-[11px] transition-all max-w-full"
            :class="tab.id === currentTabId
              ? 'bg-[var(--color-ide-accent)]/15 text-[var(--color-ide-text)] font-medium'
              : 'text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-hover)] hover:text-[var(--color-ide-text)]'"
            :title="tab.title"
            @click="handleClick(tab.id)"
          >
            <!-- 图标 -->
            <MessageSquare :size="11" class="shrink-0 opacity-40" />

            <!-- 标题/编辑 -->
            <div class="flex-1 min-w-0">
              <input
                v-if="editingTabId === tab.id"
                :data-edit-id="tab.id"
                v-model="editTitle"
                class="w-full text-[10px] px-1 py-0.5 rounded outline-none border"
                style="background: var(--color-editor-bg); border-color: var(--color-ide-accent); color: var(--color-ide-text);"
                @blur="commitRename"
                @keydown.enter="commitRename"
                @keydown.escape="cancelRename"
                @click.stop
              />
              <span v-else class="block truncate text-[11px] leading-snug">{{ tab.title }}</span>
            </div>

            <!-- Hover actions -->
            <div class="flex items-center gap-0.5 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                v-if="editingTabId !== tab.id"
                class="p-0.5 rounded hover:text-[var(--color-ide-accent)]"
                style="color: var(--color-ide-text-dim);"
                title="重命名"
                @click.stop="startRename(tab)"
              >
                <Pencil :size="10" />
              </button>
              <button
                class="p-0.5 rounded hover:text-red-400"
                style="color: var(--color-ide-text-dim);"
                title="删除"
                @click="handleDelete(tab.id, $event)"
              >
                <Trash2 :size="10" />
              </button>
            </div>
          </div>
        </template>

        <!-- 无结果 -->
        <div
          v-if="groupedTabs.length === 0"
          class="text-[10px] text-center py-6"
          style="color: var(--color-ide-text-dim);"
        >
          无匹配对话
        </div>
      </div>
    </div>
  </div>
</template>
