<script setup lang="ts">
/**
 * ContextPanel.vue — Agent 上下文面板
 *
 * 参考项目：Continue (RAG/Embeddings/Context管理)
 *
 * 展示 Agent 当前使用的上下文：
 *   1. 代码库上下文 (引用的文件/代码片段)
 *   2. 已激活的技能 (Skills)
 *   3. 长期记忆 (Memory context)
 *   4. MCP 工具 (可用工具列表)
 */
import {
  Blocks,
  BookOpen,
  Brain,
  Database,
  FileCode,
  FileText,
  Layers,
  Loader2,
  Wrench,
} from "lucide-vue-next"
import { computed, onMounted, ref } from "vue"
import type { ReferencedFile } from "@/types/studio"
import { skillsApi, type SkillInfo } from "@/api/skills"

const props = defineProps<{
  /** 当前加载的文件 */
  files?: ReferencedFile[]
  /** 激活的技能名 */
  activeSkills?: string[]
  /** 记忆节点数 */
  memoryNodes?: number
}>()

const emit = defineEmits<{
  (e: "refresh"): void
  (e: "removeFile", path: string): void
  (e: "toggleSkill", name: string): void
}>()

// ── 折叠控制 ──
const activeSection = ref<"files" | "skills" | "memory" | "tools" | null>("files")

// ── 加载技能列表 ──
const skills = ref<SkillInfo[]>([])
const skillsLoading = ref(false)

async function loadSkills() {
  skillsLoading.value = true
  try {
    const res = await skillsApi.list()
    skills.value = res.data.skills || []
  } catch {
    // 静默
  } finally {
    skillsLoading.value = false
  }
}

onMounted(loadSkills)

// ── 技能分组 ──
const activeSkillList = computed(() =>
  skills.value.filter(s => s.enabled && props.activeSkills?.includes(s.name))
)

const inactiveSkillList = computed(() =>
  skills.value.filter(s => !s.enabled || !props.activeSkills?.includes(s.name))
)

// ── Section 定义 ──
interface ContextSection {
  id: "files" | "skills" | "memory" | "tools"
  icon: typeof BookOpen
  label: string
  count: number
}

const sections = computed<ContextSection[]>(() => [
  { id: "files",  icon: FileCode,  label: "代码上下文", count: props.files?.length || 0 },
  { id: "skills", icon: Layers,    label: "激活技能",   count: activeSkillList.value.length },
  { id: "memory", icon: Database,  label: "长期记忆",   count: props.memoryNodes || 0 },
  { id: "tools",  icon: Wrench,    label: "MCP 工具",   count: 0 },
])
</script>

<template>
  <div class="context-panel rounded-lg border border-white/[0.06] bg-white/[0.01] overflow-hidden">
    <!-- 标题栏 -->
    <div class="flex items-center justify-between px-3.5 py-2.5 border-b border-white/[0.04]">
      <div class="flex items-center gap-2">
        <div class="w-5 h-5 rounded bg-brand-500/10 flex items-center justify-center">
          <Brain class="w-3 h-3 text-brand-400" />
        </div>
        <span class="text-xs font-semibold text-gray-300">上下文</span>
      </div>
      <button
        @click="emit('refresh')"
        class="p-1 rounded hover:bg-white/5 text-gray-600 hover:text-gray-400 transition-colors"
        title="刷新上下文"
      >
        <Loader2 class="w-3 h-3" />
      </button>
    </div>

    <!-- Section 导航 -->
    <div class="flex border-b border-white/[0.04]">
      <button
        v-for="sec in sections"
        :key="sec.id"
        @click="activeSection = activeSection === sec.id ? null : sec.id"
        class="flex-1 flex items-center justify-center gap-1 py-2 text-[10px] transition-colors"
        :class="activeSection === sec.id
          ? 'text-brand-400 bg-brand-500/5 border-b border-brand-500/30'
          : 'text-gray-500 hover:text-gray-300'"
      >
        <component :is="sec.icon" class="w-3 h-3" />
        {{ sec.label }}
        <span v-if="sec.count > 0" class="text-[9px] px-1 rounded-full" :class="activeSection === sec.id ? 'bg-brand-500/10' : 'bg-white/[0.03]'">
          {{ sec.count }}
        </span>
      </button>
    </div>

    <!-- ═══ 文件上下文 ═══ -->
    <div v-if="activeSection === 'files'" class="p-2 space-y-1 max-h-48 overflow-y-auto custom-scroll">
      <div v-if="!files?.length" class="py-4 text-center text-xs text-gray-600">
        <FileCode class="w-5 h-5 mb-1 mx-auto opacity-20" />
        暂无引用文件
        <p class="text-[10px] mt-1">在输入框中使用 @ 引用文件</p>
      </div>
      <div
        v-for="file in files"
        :key="file.path"
        class="flex items-center gap-2 px-2.5 py-1.5 rounded-md hover:bg-white/[0.02] group cursor-pointer"
      >
        <FileText class="w-3.5 h-3.5 text-brand-400/60 shrink-0" />
        <div class="flex-1 min-w-0">
          <p class="text-[11px] text-gray-300 truncate font-mono">{{ file.name }}</p>
          <p class="text-[10px] text-gray-600 truncate">{{ file.path }}</p>
        </div>
        <button
          @click="emit('removeFile', file.path)"
          class="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-500/10 text-gray-600 hover:text-red-400 transition-all"
          title="移除"
        >
          ✕
        </button>
      </div>
    </div>

    <!-- ═══ 激活技能 ═══ -->
    <div v-else-if="activeSection === 'skills'" class="max-h-48 overflow-y-auto custom-scroll">
      <!-- 已激活 -->
      <div v-if="activeSkillList.length > 0" class="p-2 space-y-1">
        <p class="text-[10px] font-semibold text-emerald-400/60 uppercase tracking-wider px-2">
          已激活 ({{ activeSkillList.length }})
        </p>
        <div
          v-for="skill in activeSkillList"
          :key="skill.name"
          class="flex items-center gap-2 px-2.5 py-1.5 rounded-md bg-emerald-500/[0.04] cursor-pointer group"
          @click="emit('toggleSkill', skill.name)"
        >
          <div class="w-5 h-5 rounded bg-emerald-500/10 flex items-center justify-center shrink-0">
            <Blocks class="w-3 h-3 text-emerald-400" />
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[11px] text-gray-300 truncate">{{ skill.name }}</p>
            <p class="text-[10px] text-gray-600 truncate">{{ skill.description }}</p>
          </div>
          <span class="w-2 h-2 rounded-full bg-emerald-400" />
        </div>
      </div>

      <!-- 可用 -->
      <div v-if="inactiveSkillList.length > 0" class="p-2 space-y-1 border-t border-white/[0.04]">
        <p class="text-[10px] font-semibold text-gray-500 uppercase tracking-wider px-2">
          可用 ({{ inactiveSkillList.length }})
        </p>
        <div
          v-for="skill in inactiveSkillList.slice(0, 10)"
          :key="skill.name"
          class="flex items-center gap-2 px-2.5 py-1.5 rounded-md hover:bg-white/[0.02] cursor-pointer group transition-colors"
          @click="emit('toggleSkill', skill.name)"
        >
          <div class="w-5 h-5 rounded bg-white/[0.03] flex items-center justify-center shrink-0">
            <Blocks class="w-3 h-3 text-gray-500" />
          </div>
          <div class="flex-1 min-w-0">
            <p class="text-[11px] text-gray-500 truncate">{{ skill.name }}</p>
            <p class="text-[10px] text-gray-700 truncate">{{ skill.description }}</p>
          </div>
          <span class="text-[10px] text-gray-600">{{ skill.category }}</span>
        </div>
      </div>

      <!-- 加载中 -->
      <div v-if="skillsLoading" class="flex items-center justify-center py-8 text-gray-600 text-xs gap-2">
        <Loader2 class="w-3.5 h-3.5 animate-spin" /> 加载技能...
      </div>

      <!-- 无技能 -->
      <div v-if="!skillsLoading && skills.length === 0" class="py-6 text-center text-xs text-gray-600">
        <Layers class="w-5 h-5 mb-1 mx-auto opacity-20" />
        暂无可用技能
      </div>
    </div>

    <!-- ═══ 长期记忆 ═══ -->
    <div v-else-if="activeSection === 'memory'" class="p-3">
      <div class="flex items-center justify-between mb-2">
        <span class="text-[10px] text-gray-500">关联记忆节点</span>
        <span class="text-[10px] font-mono text-brand-400">{{ memoryNodes || 0 }} nodes</span>
      </div>

      <!-- 衰减曲线示意 -->
      <div class="h-8 rounded-md bg-white/[0.02] border border-white/[0.04] relative overflow-hidden mb-2">
        <div class="absolute inset-0 flex items-end px-2 gap-px">
          <div
            v-for="i in 12"
            :key="i"
            class="flex-1 rounded-t-sm"
            style="background: linear-gradient(to top, rgba(99,102,241,0.3), rgba(99,102,241,0.05))"
            :style="{ height: `${10 + Math.sin(i * 0.8) * 25 + Math.cos(i * 0.5) * 15}%` }"
          />
        </div>
      </div>

      <p class="text-[10px] text-gray-600 leading-relaxed">
        记忆衰减公式：importance × 1/(1 + hours × 0.01)
        <br />遗忘阈值：0.05
      </p>

      <div v-if="!memoryNodes" class="py-4 text-center text-xs text-gray-600">
        <Database class="w-5 h-5 mb-1 mx-auto opacity-20" />
        暂无记忆节点
      </div>
    </div>

    <!-- ═══ MCP 工具 ═══ -->
    <div v-else-if="activeSection === 'tools'" class="p-3">
      <p class="text-[10px] text-gray-600 leading-relaxed">
        Agent 可通过 MCP 协议访问文件系统、Git、数据库、浏览器等外部工具。
        在 <span class="text-brand-400">MCP 设置</span> 页面管理服务器连接。
      </p>

      <!-- 预设工具清单 -->
      <div class="mt-2 space-y-1">
        <div
          v-for="tool in ['get_weather', 'web_search', 'calculate', 'file_read', 'datetime_now']"
          :key="tool"
          class="flex items-center gap-2 px-2 py-1 text-[10px] text-gray-500"
        >
          <Wrench class="w-3 h-3 text-gray-600" />
          {{ tool }}
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-scroll::-webkit-scrollbar { width: 3px; }
.custom-scroll::-webkit-scrollbar-thumb { background: rgba(255,255,255,.06); border-radius: 9999px; }
</style>
