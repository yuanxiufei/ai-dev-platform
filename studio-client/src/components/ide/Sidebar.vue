<script setup lang="ts">
/** CodeBuddy IDE — Left Sidebar (Activity Bar + Panel Content) */
import { ref, computed } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useIDEStore } from '@/stores/useIDEStore'
import { Files, Search, GitBranch, Bug, Blocks, Settings, Sparkles, Monitor } from 'lucide-vue-next'
import FileTree from './FileTree.vue'

const router = useRouter()
const store = useIDEStore()
const iconMap: Record<string, any> = { Files, Search, GitBranch, Bug, Blocks, Sparkles, Monitor }
const isDragging = ref(false)

function onDragStart(e: MouseEvent): void {
  e.preventDefault(); isDragging.value = true; document.body.classList.add('cursor-col-resize','select-none')
  const startX = e.clientX, startW = store.layout.sidebarWidth
  const move = (ev: MouseEvent) => { store.layout.sidebarWidth = Math.max(180, Math.min(500, startW + (ev.clientX - startX))) }
  const up = () => { isDragging.value = false; document.body.classList.remove('cursor-col-resize','select-none'); document.removeEventListener('mousemove',move); document.removeEventListener('mouseup',up) }
  document.addEventListener('mousemove',move); document.addEventListener('mouseup',up)
}

/** Studio page navigation links shown in the sidebar panel */
const studioLinks = [
  { path: '/chat', label: 'AI 对话', icon: 'Sparkles' },
  { path: '/projects', label: '我的项目', icon: 'LayoutGrid' },
  { path: '/knowledge', label: '知识库', icon: 'BookOpen' },
  { path: '/tools', label: '工具集', icon: 'Wrench' },
  { path: '/plugins', label: '插件市场', icon: 'Store' },
  { path: '/arena', label: '模型竞技场', icon: 'Swords' },
  { path: '/memory', label: '长期记忆', icon: 'Brain' },
  { path: '/mcp', label: 'MCP 连接', icon: 'Server' },
  { path: '/skills', label: '技能指令', icon: 'Sparkles' },
  { path: '/rules', label: '规则管理', icon: 'ScrollText' },
  { path: '/agents', label: 'Agent 管理', icon: 'Bot' },
  { path: '/image-gen', label: '图像生成', icon: 'Image' },
  { path: '/prompt-templates', label: 'Prompt 模板', icon: 'Wand2' },
  { path: '/screenshot-to-code', label: '截图转代码', icon: 'Code2' },
  { path: '/templates', label: '模板市场', icon: 'Layers' },
  { path: '/integrations', label: '集成服务', icon: 'Link2' },
  { path: '/storage', label: '存储设置', icon: 'HardDrive' },
  { path: '/standalone', label: '独立运行管理', icon: 'Monitor' },
]

function navigateTo(path: string) {
  if (store.activeTabId) store.closeTab(store.activeTabId)
  router.push(path)
}

/** Panel header title based on active activity item */
const route = useRoute()

const panelTitle = computed(() => {
  const titles: Record<string, string> = {
    explorer: '资源管理器',
    studio: 'AI Studio',
    search: '搜索',
    git: '源代码管理',
    debug: '运行和调试',
    extensions: '扩展',
    settings: '管理',
  }
  return titles[store.activeActivityItem] ?? store.activeActivityItem
})

function isStudioActive(path: string): boolean {
  if (path === '/chat') return route.path === '/chat' || route.path.startsWith('/projects/')
  return route.path.startsWith(path)
}

function getStudioIcon(path: string): string {
  const icons: Record<string, string> = {
    '/chat': '💬', '/projects': '📁', '/knowledge': '📚', '/tools': '🔧',
    '/plugins': '🧩', '/arena': '⚔️', '/memory': '🧠', '/mcp': '🔌',
    '/skills': '✨', '/rules': '📜', '/agents': '🤖', '/image-gen': '🎨',
    '/prompt-templates': '🪄', '/screenshot-to-code': '📸', '/templates': '📋',
    '/integrations': '🔗', '/storage': '💾', '/standalone': '🖥️',
  }
  for (const [key, icon] of Object.entries(icons)) {
    if (path.startsWith(key)) return icon
  }
  return '📄'
}
</script>

<template>
  <div v-if="store.layout.activityBarVisible" class="shrink-0 flex h-full" style="width: var(--sidebar-width);">
    <!-- Activity Bar -->
    <aside class="w-14 bg-[var(--color-activity-bg)] flex flex-col items-center py-1.5 shrink-0 z-20">
      <!-- Logo -->
      <button class="w-10 h-10 my-1 rounded-md flex items-center justify-center hover:bg-white/5 transition-colors mb-3"
        title="CodeBuddy" @click="store.activeActivityItem = 'explorer'; store.layout.fileTreeVisible = true">
        <div class="w-7 h-7 rounded bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center text-sm font-bold text-white">C</div>
      </button>

      <!-- Main Activity Items -->
      <div class="flex-1 flex flex-col gap-0.5 w-full">
        <button v-for="item in store.activityItems" :key="item.id"
          class="group relative w-full h-10 flex items-center justify-center transition-colors"
          :class="store.activeActivityItem === item.id ? 'text-white' : 'text-gray-500 hover:text-gray-300'"
          :title="item.label"
          @click="store.activeActivityItem = item.id; store.layout.fileTreeVisible = true">
          <div v-if="store.activeActivityItem === item.id" class="absolute left-0 w-0.5 h-6 bg-white rounded-r" />
          <component :is="iconMap[item.icon] ?? item.icon" :size="24" />
          <span class="absolute left-full ml-2 px-2.5 py-1.5 bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded text-sm whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-50">{{ item.label }}</span>
          <span v-if="item.badge" class="absolute top-1 right-1 min-w-[16px] h-4 flex items-center justify-center bg-blue-500 text-[10px] font-medium text-white rounded-full px-1">{{ item.badge }}</span>
        </button>
      </div>

      <!-- Bottom: Settings -->
      <div class="mt-auto pt-1 border-t border-[#33334a33] w-full">
        <button class="w-full h-10 flex items-center justify-center text-gray-500 hover:text-gray-300 transition-colors"
          title="管理" @click="store.activeActivityItem = 'settings'"><Settings :size="22" /></button>
      </div>
    </aside>

    <!-- Resize Handle -->
    <div class="resize-handle resize-handle-h" :class="{ active: isDragging }" @mousedown.prevent="onDragStart" />

    <!-- Panel Content Area -->
    <Transition name="slide-left">
      <aside v-show="store.layout.fileTreeVisible"
        class="bg-[var(--color-ide-surface)] flex flex-col overflow-hidden shrink-0"
        :style="{ width: `${store.layout.sidebarWidth}px` }">
        <!-- Panel Header -->
        <div class="h-9 flex items-center justify-between px-3 text-xs font-semibold text-[var(--color-ide-text)] shrink-0 border-b border-[var(--color-ide-border)]">
          <span class="truncate">{{ panelTitle }}</span>
          <div class="flex items-center gap-0.5">
            <button class="p-1 rounded hover:bg-white/5 opacity-60 hover:opacity-100" title="关闭面板"
              @click="store.layout.fileTreeVisible = false">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>
        </div>

        <!-- Panel Body -->
        <div class="flex-1 overflow-y-auto overflow-x-hidden">
          <!-- Explorer: File Tree -->
          <FileTree v-if="store.activeActivityItem === 'explorer'" />

          <!-- Studio: App navigation links -->
          <div v-else-if="store.activeActivityItem === 'studio'" class="p-2.5 space-y-0.5">
            <div class="px-2 py-2 text-[11px] uppercase tracking-wider text-[var(--color-ide-text-dim)] font-semibold">
              AI Studio 功能
            </div>
            <button
              v-for="link in studioLinks" :key="link.path"
              class="w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors text-left"
              :class="isStudioActive(link.path)
                ? 'bg-[var(--color-ide-accent)]/15 text-[var(--color-ide-accent)]'
                : 'text-[var(--color-ide-text-dim)] hover:bg-white/5 hover:text-[var(--color-ide-text)]'"
              @click="navigateTo(link.path)"
            >
              <span class="shrink-0 w-5 flex justify-center text-base leading-none">
                {{ getStudioIcon(link.path) }}
              </span>
              <span class="truncate">{{ link.label }}</span>
            </button>
          </div>

          <!-- Search -->
          <div v-else-if="store.activeActivityItem === 'search'" class="p-3 text-xs text-[var(--color-ide-text-dim)]">
            <input type="text" placeholder="搜索文件..." class="w-full bg-[var(--color-ide-bg)] border border-[var(--color-ide-border)] rounded px-2 py-1.5 text-xs focus:outline-none focus:border-[var(--color-ide-border-focus)]"/>
          </div>

          <!-- Git SCM -->
          <div v-else-if="store.activeActivityItem === 'git'" class="p-3 text-xs text-[var(--color-ide-text-dim)] space-y-2">
            <div class="text-[var(--color-ide-text)] font-semibold">源代码管理</div>
            <div class="flex items-center gap-1.5 text-[var(--color-ide-text-dim)]">
              <span class="w-1.5 h-1.5 rounded-full bg-[var(--color-ide-success)]"></span>main
            </div>
            <div class="border-t border-[var(--color-ide-border)] pt-2">
              <div class="text-[10px] uppercase tracking-wider text-[var(--color-ide-text-dim)] mb-1.5">更改 (9)</div>
              <div v-for="i in 9" :key="i" class="py-0.5 truncate hover:bg-white/5 rounded px-1 cursor-pointer">修改的文件_{{ i }}.ts</div>
            </div>
          </div>

          <!-- Run & Debug -->
          <div v-else-if="store.activeActivityItem === 'debug'" class="p-3 text-xs">
            <p class="text-[var(--color-ide-text)]">运行和调试</p>
            <p class="text-[var(--color-ide-text-dim)] mt-1">暂无配置</p>
            <button class="mt-3 w-full py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs transition-colors">创建 launch.json</button>
          </div>

          <!-- Extensions -->
          <div v-else-if="store.activeActivityItem === 'extensions'" class="p-3 text-xs text-[var(--color-ide-text-dim)] space-y-1">
            <p class="text-[var(--color-ide-text)] font-semibold mb-2">已安装的扩展</p>
            <div class="space-y-1.5">
              <div v-for="ext in ['AI 助手', 'Git 集成', '文件浏览器增强']" :key="ext"
                class="flex items-center gap-2 px-2 py-1.5 rounded hover:bg-white/5 cursor-pointer">
                <span class="w-5 h-5 rounded bg-[var(--color-ide-border)] flex items-center justify-center text-[10px]">{{ ext[0] }}</span>
                <span>{{ ext }}</span>
              </div>
            </div>
          </div>

          <!-- Settings -->
          <div v-else-if="store.activeActivityItem === 'settings'" class="p-3 text-xs text-[var(--color-ide-text-dim)] space-y-1">
            <p class="text-[var(--color-ide-text)] font-semibold mb-2">管理</p>
            <button class="w-full text-left px-2 py-1.5 rounded hover:bg-white/5 transition-colors">用户设置</button>
            <button class="w-full text-left px-2 py-1.5 rounded hover:bg-white/5 transition-colors">键盘快捷方式</button>
            <button class="w-full text-left px-2 py-1.5 rounded hover:bg-white/5 transition-colors">主题</button>
          </div>
        </div>
      </aside>
    </Transition>
  </div>
</template>
