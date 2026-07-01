<script setup lang="ts">
import { ref } from "vue"

interface PanelSection {
  id: string
  title: string
  count?: number
  collapsible?: boolean
}

const props = defineProps<{
  title: string
  sections?: PanelSection[]
}>()

const collapsedSections = ref<Set<string>>(new Set())

const toggleSection = (id: string) => {
  if (collapsedSections.value.has(id)) {
    collapsedSections.value.delete(id)
  } else {
    collapsedSections.value.add(id)
  }
}

const isCollapsed = (id: string) => collapsedSections.value.has(id)
</script>

<template>
  <div class="flex flex-col h-full border-l border-white/8 bg-surface-900/50 backdrop-blur">
    <!-- 面板头部 -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-white/8">
      <h3 class="text-xs font-semibold text-gray-300 uppercase tracking-wider">{{ title }}</h3>
      <span class="text-[10px] text-gray-600 font-mono">
        {{ sections?.length ?? 0 }}
      </span>
    </div>

    <!-- 空状态 -->
    <div v-if="!sections || sections.length === 0" class="flex-1 flex flex-col items-center justify-center p-6 text-center">
      <div class="w-12 h-12 rounded-xl bg-white/5 flex items-center justify-center mb-3">
        <div class="w-5 h-5 rounded border border-dashed border-gray-600" />
      </div>
      <p class="text-xs text-gray-600 leading-relaxed">
        暂无内容。<br>开始对话后这里将显示任务和工具调用记录。
      </p>
    </div>

    <!-- 分组列表 -->
    <div v-else class="flex-1 overflow-y-auto">
      <div v-for="section in sections" :key="section.id">
        <!-- 分组头 -->
        <button
          v-if="section.collapsible !== false"
          class="flex items-center gap-1.5 w-full px-4 py-2 text-left hover:bg-white/5 transition-colors group"
          @click="toggleSection(section.id)"
        >
          <component
            :is="isCollapsed(section.id) ? ChevronRight : ChevronDown"
            class="w-3 h-3 text-gray-600 group-hover:text-gray-400 transition-colors"
          />
          <span class="text-[11px] font-medium text-gray-500 flex-1">{{ section.title }}</span>
          <span v-if="section.count !== undefined" class="text-[10px] text-gray-600">{{ section.count }}</span>
        </button>
        <!-- 占位内容 -->
        <div
          v-if="!isCollapsed(section.id)"
          class="px-4 py-2"
        >
          <div class="text-[11px] text-gray-600 pl-5 italic">
            暂无项目
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
