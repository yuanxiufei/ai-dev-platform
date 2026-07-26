<script setup lang="ts">
/**
 * CodeBuddy IDE — StudioPanel
 *
 * 左侧 Sidebar "AI 工具" 视图（精简版）
 *   - 顶部快速搜索
 *   - 按场景分组：内容生成 / 知识 / 工具 / 数据 / 协作 / 系统
 *   - 跳转 = 路由导航（不污染 fileTreeVisible，由 EditorArea 决定 overlay）
 *   - 当前路由项高亮
 *
 * Session 33 重大改版：
 *   - 与 ActivityBar AI 工具去重（5 个高频入口已放 ActivityBar）
 *   - 字号统一: 标签 13px / 描述 11px（更易读）
 *   - 间距统一: 列表项 py-1.5 改为 py-2，行高更舒展
 *   - 跳转逻辑修正: 只 router.push，不再强设 activeActivityItem='projects'
 */
import { computed, ref } from "vue"
import { useRoute, useRouter } from "vue-router"
import { useIDEStore } from "@/stores/useIDEStore"
import {
  Search, Sparkles, Volume2, BookOpen,
  Network, Brain, Trophy, Users as UsersIcon, ScrollText,
  BarChart3, HardDrive, Activity, Globe, Webhook, Trello,
  GitBranch, Calendar, Settings as SettingsIcon, Keyboard, Bot,
  MessageSquare,
} from "lucide-vue-next"

interface StudioItem {
  id: string
  path: string
  label: string
  desc: string
  icon: any
}

interface StudioGroup {
  id: string
  label: string
  icon: any
  items: StudioItem[]
}

const router = useRouter()
const route = useRoute()
const ideStore = useIDEStore()
const searchText = ref("")

const groups: StudioGroup[] = [
  {
    // AI 内容生成：只保留语音合成 (截图/图片 已在 ActivityBar 顶层)
    id: "media", label: "AI 内容生成", icon: Sparkles, items: [
      { id: "voice", path: "/voice", label: "语音合成", desc: "TTS 文本转语音", icon: Volume2 },
    ],
  },
  {
    // 知识与记忆: 知识库已在 ActivityBar → 只留图谱/记忆
    id: "knowledge", label: "知识与记忆", icon: BookOpen, items: [
      { id: "kg",     path: "/knowledge-graph", label: "知识图谱", desc: "代码关系可视化", icon: Network },
      { id: "memory", path: "/memory",          label: "长期记忆", desc: "Agent 记忆管理", icon: Brain },
    ],
  },
  {
    // Agent 与模型: Agent 管理已在 ActivityBar → 只留竞技场/Rules/AgentChat
    id: "agent", label: "Agent 与模型", icon: Bot, items: [
      { id: "agent-chat", path: "/chat", label: "Agent 对话", desc: "完整 AI 编程 Agent (SSE流式/工具调用/会话历史)", icon: MessageSquare },
      { id: "arena", path: "/arena", label: "模型竞技场", desc: "多模型对比", icon: Trophy },
      { id: "rules", path: "/rules", label: "Rules 配置", desc: "Agent 行为规则", icon: ScrollText },
    ],
  },
  {
    // 数据分析
    id: "data", label: "数据分析", icon: BarChart3, items: [
      { id: "analytics",    path: "/analytics",    label: "数据分析",    desc: "使用统计",        icon: BarChart3 },
      { id: "storage",      path: "/storage",      label: "存储管理",    desc: "文件 / 对象存储",  icon: HardDrive },
      { id: "trajectory",   path: "/trajectory",   label: "链路追踪",    desc: "调用链可视化",    icon: Activity },
      { id: "openapi",      path: "/openapi",      label: "OpenAPI 发现", desc: "API 自动发现",   icon: Globe },
      { id: "webhooks",     path: "/webhooks",     label: "Webhooks",    desc: "事件回调",        icon: Webhook },
      { id: "integrations", path: "/integrations", label: "集成管理",    desc: "外部系统对接",    icon: Plug2 },
    ],
  },
  {
    // 协作与流程
    id: "collab", label: "协作与流程", icon: Trello, items: [
      { id: "kanban",     path: "/kanban",     label: "Kanban 看板", desc: "任务看板",         icon: Trello },
      { id: "workflow",   path: "/workflow",   label: "工作流",      desc: "可视化工作流",     icon: GitBranch },
      { id: "jobs",       path: "/jobs",       label: "定时任务",    desc: "Cron 调度",        icon: Calendar },
      { id: "group-chat", path: "/group-chat", label: "群聊协作",    desc: "多人 Agent 对话",  icon: UsersIcon },
    ],
  },
  {
    // 系统设置
    id: "settings", label: "系统设置", icon: SettingsIcon, items: [
      { id: "keybindings", path: "/keybindings", label: "快捷键", desc: "键盘映射", icon: Keyboard },
    ],
  },
]

const filteredGroups = computed<StudioGroup[]>(() => {
  const q = searchText.value.trim().toLowerCase()
  if (!q) return groups
  return groups
    .map((g) => ({
      ...g,
      items: g.items.filter(
        (it) => it.label.toLowerCase().includes(q) || it.desc.toLowerCase().includes(q),
      ),
    }))
    .filter((g) => g.items.length > 0)
})

/**
 * 跳转逻辑（修复版）
 *
 * 旧 bug: navigate() 强设 `activeActivityItem='projects'` + `fileTreeVisible=true`，
 *        导致中央 EditorArea 在 /knowledge 等 overlay 路径下被 projects 视图遮挡。
 *
 * 修复: 只 router.push，EditorArea 通过 showPageOverlay 自动判断该路径是否需要
 *       overlay（参见 EditorArea.vue 的 OVERLAY_ROUTES 白名单）。其他路径由
 *       主 App.vue 的 <router-view> 渲染。
 */
function navigate(item: StudioItem): void {
  if (route.path === item.path) return
  router.push(item.path)
}

function isActive(path: string): boolean {
  return route.path === path || route.path.startsWith(path + "/")
}
</script>

<template>
  <div class="studio-nav h-full flex flex-col overflow-hidden">
    <!-- 搜索栏 -->
    <div class="shrink-0 flex items-center gap-1 px-2 py-1.5 border-b border-[var(--color-ide-border)]">
      <div class="relative flex-1">
        <Search class="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--color-ide-text-dim)] pointer-events-none" />
        <input
          v-model="searchText"
          type="text"
          placeholder="搜索工具…"
          class="w-full rounded-md bg-[var(--color-ide-surface-hover)] border border-transparent
                 pl-7 pr-2 py-1 text-[13px]
                 text-[var(--color-ide-text)] placeholder-[var(--color-ide-text-dim)]
                 focus:outline-none focus:border-[var(--color-ide-accent)]/40"
        />
      </div>
    </div>

    <!-- 工具列表（按组分类） -->
    <div class="flex-1 overflow-y-auto overflow-x-hidden py-1.5">
      <div v-if="!filteredGroups.length" class="px-4 py-8 text-center text-[var(--color-ide-text-dim)] text-[12px]">
        没有匹配的工具
      </div>

      <div v-for="group in filteredGroups" :key="group.id" class="mb-3">
        <!-- 组标题 -->
        <div class="px-3 py-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-ide-text-dim)]/80">
          <component :is="group.icon" :size="11" />
          <span>{{ group.label }}</span>
        </div>

        <!-- 组内项目 -->
        <ul class="space-y-0.5 px-1">
          <li v-for="item in group.items" :key="item.id">
            <button
              class="w-full group/item flex items-center gap-2.5 px-2 py-1.5 rounded-md border border-transparent
                     hover:border-[var(--color-ide-border)] hover:bg-[var(--color-ide-surface-hover)]
                     transition-all duration-150 text-left"
              :class="isActive(item.path) ? '!border-[var(--color-ide-accent)]/40 !bg-[var(--color-ide-surface-active)]' : ''"
              @click="navigate(item)"
            >
              <!-- 图标 -->
              <div
                class="shrink-0 w-6 h-6 rounded-md flex items-center justify-center"
                :style="isActive(item.path)
                  ? 'background: var(--studio-nav-active-bg);'
                  : 'background: var(--studio-nav-bg);'"
              >
                <component
                  :is="item.icon"
                  :size="13"
                  :style="{ color: isActive(item.path) ? '#a78bfa' : '#c0c1ff' }"
                />
              </div>
              <!-- 文本 -->
              <div class="flex-1 min-w-0">
                <div
                  class="text-[13px] font-medium truncate"
                  :style="{ color: isActive(item.path) ? 'var(--color-ide-text)' : 'var(--color-ide-text-dim)' }"
                >
                  {{ item.label }}
                </div>
                <div class="text-[11px] text-[var(--color-ide-text-dim)]/70 truncate mt-px">
                  {{ item.desc }}
                </div>
              </div>
            </button>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══ Studio 导航图标渐变（组件级 CSS 变量） ═══ */
.studio-nav {
  --studio-nav-active-bg: linear-gradient(135deg, rgba(139, 92, 246, 0.25), rgba(139, 92, 246, 0.15));
  --studio-nav-bg: linear-gradient(135deg, rgba(192, 193, 255, 0.18), rgba(127, 127, 213, 0.12));
}
</style>
