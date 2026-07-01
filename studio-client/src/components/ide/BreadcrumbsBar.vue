<script setup lang="ts">/**
 * BreadcrumbsBar.vue — VSCode 风格文件路径面包屑导航
 *
 * 借鉴 VSCode Editor Breadcrumbs 设计：
 *   - 文件路径分段显示，每段可点击
 *   - 点击某段弹出同级文件/文件夹列表
 *   - 支持快捷导航到同级文件
 */
import { ChevronRight, FileCode, FolderOpen } from "lucide-vue-next"
import { computed, ref, type Ref } from "vue"
import { useIDEStore } from "@/stores/useIDEStore"

const store = useIDEStore()

/** 当前文件路径分段 */
const segments = computed<string[]>(() => {
  const fp = store.activeTab?.filePath
  if (!fp) return []
  return fp.split(/[/\\]/).filter(Boolean)
})

/** 哪个分段的下拉菜单打开 */
const openSegmentIdx: Ref<number | null> = ref(null)

/** 同级候选项 */
const siblings = computed<Array<{ name: string; isDir: boolean }>>(() => {
  if (openSegmentIdx.value === null || openSegmentIdx.value >= segments.value.length)
    return []
  // 前 N 段拼接成目录路径
  const prefix = segments.value.slice(0, openSegmentIdx.value).join("/")
  return getSiblings(store.fileTree, prefix)
})

function getSiblings(
  entries: typeof store.fileTree,
  prefix: string,
): Array<{ name: string; isDir: boolean }> {
  const parts = prefix ? prefix.split("/") : []
  let current = entries
  for (const part of parts) {
    const dir = current.find((e) => e.name === part && e.isDir)
    if (dir?.children) current = dir.children
    else return []
  }
  return current.map((e) => ({ name: e.name, isDir: e.isDir }))
}

function handleSegmentClick(idx: number) {
  openSegmentIdx.value = openSegmentIdx.value === idx ? null : idx
}

function handleSelectSibling(name: string, isDir: boolean) {
  if (isDir) {
    // 进入目录：不打开文件，但定位到该目录
    openSegmentIdx.value = null
    return
  }
  // 打开文件
  const prefix = segments.value.slice(0, openSegmentIdx.value!).join("/")
  const filePath = prefix ? `${prefix}/${name}` : name
  store.openFile(filePath)
  openSegmentIdx.value = null
}

function closeDropdown() {
  openSegmentIdx.value = null
}

/** 🆕 VSCode 风格: 文件图标含颜色 */
function fileColor(name: string): string {
  const ext = name.split(".").pop()?.toLowerCase() ?? ""
  const map: Record<string, string> = {
    vue: "#38BDF8", ts: "#60A5FA", tsx: "#60A5FA", js: "#F7DF1E",
    jsx: "#61DAFB", py: "#3776AB", json: "#FB923C", md: "#3B82F6",
    css: "#264DE4", html: "#E06C75",
  }
  return map[ext] ?? "#90A4AE"
}
</script>

<template>
  <!-- VSCode 风格 Breadcrumbs -->
  <div
    v-if="segments.length > 0"
    class="breadcrumb-bar flex items-center h-full px-2 text-xs shrink-0 select-none relative"
    style="background: var(--color-editor-bg); border-right: 1px solid var(--color-tab-border);"
    @mouseleave="closeDropdown"
  >
    <!-- 根图标 (Workspace) -->
    <span class="flex items-center text-[var(--color-ide-text-dim)] mr-0.5" title="工作区根目录">
      <FolderOpen :size="14" />
    </span>

    <!-- 路径分段 -->
    <template v-for="(seg, i) in segments" :key="i">
      <ChevronRight :size="10" class="mx-0.5 opacity-30 shrink-0" />
      <button
        class="breadcrumb-segment shrink-0 rounded-sm px-1 py-0.5 transition-colors hover:bg-white/10 max-w-[160px] truncate"
        :class="{
          'text-[var(--color-ide-text)] font-medium': i === segments.length - 1,
          'text-[var(--color-ide-text-dim)]': i !== segments.length - 1,
        }"
        :title="seg"
        @click="handleSegmentClick(i)"
      >
        {{ seg }}
      </button>
    </template>

    <!-- Dropdown: 同级文件/文件夹列表 -->
    <Teleport to="body">
      <div
        v-if="openSegmentIdx !== null && siblings.length > 0"
        class="fixed z-[350] mt-1 w-52 max-h-64 overflow-y-auto bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded-lg shadow-2xl py-1 text-xs"
        :style="{
          left: '220px',
          top: '110px',
        }"
      >
        <div class="px-3 py-1.5 text-[10px] uppercase tracking-wider text-[var(--color-ide-text-dim)] opacity-50">
          同级文件
        </div>
        <button
          v-for="sib in siblings"
          :key="sib.name"
          class="w-full text-left flex items-center gap-2 px-3 py-1.5 hover:bg-white/5 transition-colors"
          @click="handleSelectSibling(sib.name, sib.isDir)"
        >
          <component :is="sib.isDir ? FolderOpen : FileCode" :size="13"
            :style="{ color: sib.isDir ? '#FBBF24' : fileColor(sib.name) }"
            class="shrink-0"
          />
          <span class="truncate">{{ sib.name }}</span>
        </button>
      </div>
    </Teleport>

    <!-- 空状态 -->
    <span v-if="segments.length === 0" class="opacity-40 text-[var(--color-ide-text-dim)] px-2">
      无打开的文件
    </span>
  </div>
</template>
