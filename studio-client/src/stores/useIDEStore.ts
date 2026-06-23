// ============================================
// CodeBuddy IDE — Global State (Pinia Store)
// ============================================

import { defineStore } from 'pinia'
import { ref, computed, shallowRef } from 'vue'
import type {
  FileEntry,
  EditorTab,
  TerminalSession,
  OutputChannel,
  SearchState,
  RightPanelView,
  ActivityItem,
  CursorPosition,
  IDELayoutState,
} from '@/types/ide'

let idCounter = 0
function uid(): string {
  return `id_${Date.now()}_${++idCounter}`
}

const extToLang: Record<string, string> = {
  ts: 'typescript', tsx: 'typescriptreact',
  js: 'javascript', jsx: 'javascriptreact',
  vue: 'html', py: 'python', rs: 'rust', go: 'go',
  java: 'java', json: 'json', yaml: 'yaml', yml: 'yaml',
  toml: 'ini', md: 'markdown', css: 'css', scss: 'scss',
  less: 'less', html: 'html', xml: 'xml', sh: 'shell',
  bat: 'batch', ps1: 'powershell', sql: 'sql',
  dockerfile: 'dockerfile', env: 'plaintext',
  txt: 'plaintext', log: 'plaintext', gitignore: 'plaintext',
  lock: 'toml', mod: 'go', c: 'cpp', cpp: 'cpp', h: 'cpp',
}

function getLanguageFromPath(filePath: string): string {
  const ext = filePath.split('.').pop()?.toLowerCase() ?? ''
  if (filePath.toLowerCase().includes('dockerfile')) return 'dockerfile'
  const fileName = filePath.split(/[/\\]/).pop() ?? ''
  if (fileName.startsWith('.')) return 'plaintext'
  return extToLang[ext] ?? 'plaintext'
}

export const useIDEStore = defineStore('ide', () => {
  const layout = ref<IDELayoutState>({
    sidebarWidth: 260,
    fileTreeVisible: true,
    rightPanelWidth: 420,
    rightPanelVisible: true,
    bottomPanelHeight: 240,
    bottomPanelVisible: false,
    activityBarVisible: true,
    statusBarVisible: true,
    menuBarVisible: true,
  })

  function buildDemoFileTree(): FileEntry[] {
    return [
      {
        name: 'ai-fullstack-platform', path: '', isDir: true, expanded: true, icon: 'FolderOpen',
        children: [
          { name: '.codebuddy', path: '.codebuddy', isDir: true, expanded: false, children: [] },
          { name: '.github', path: '.github', isDir: true, expanded: false, children: [
            { name: 'workflows', path: '.github/workflows', isDir: true, expanded: false, children: [] },
          ]},
          { name: 'ai_models', path: 'ai_models', isDir: true, expanded: false, icon: 'BrainCircuit' },
          { name: 'backend', path: 'backend', isDir: true, expanded: true, icon: 'Server',
            children: [
              { name: 'app', path: 'backend/app', isDir: true, expanded: true, children: [
                { name: 'api', path: 'backend/app/api', isDir: true, expanded: false },
                { name: 'core', path: 'backend/app/core', isDir: true, expanded: false },
                { name: 'models', path: 'backend/app/models', isDir: true, expanded: false },
              ]},
              { name: 'pyproject.toml', path: 'backend/pyproject.toml', isDir: false, language: 'toml' },
            ]},
          { name: 'compose.yml', path: 'compose.yml', isDir: false, language: 'yaml' },
          { name: 'package.json', path: 'package.json', isDir: false, language: 'json' },
          { name: 'pnpm-lock.yaml', path: 'pnpm-lock.yaml', isDir: false, language: 'yaml' },
          { name: 'README.md', path: 'README.md', isDir: false, language: 'markdown' },
          { name: 'studio-admin', path: 'studio-admin', isDir: true, expanded: false, icon: 'LayoutGrid' },
          { name: 'studio-client', path: 'studio-client', isDir: true, expanded: false, icon: 'Monitor' },
          { name: 'video-admin', path: 'video-admin', isDir: true, expanded: false, icon: 'Video' },
          { name: 'workers', path: 'workers', isDir: true, expanded: false, icon: 'Cog' },
        ],
      },
    ]
  }

  const fileTree = ref<FileEntry[]>(buildDemoFileTree())
  const selectedFilePath = ref<string | null>(null)

  function toggleExpand(entry: FileEntry): void {
    if (!entry.isDir) return
    entry.expanded = !entry.expanded
  }

  function findEntryByPath(entries: FileEntry[], targetPath: string): FileEntry | null {
    for (const e of entries) {
      if (e.path === targetPath) return e
      if (e.children?.length) {
        const found = findEntryByPath(e.children, targetPath)
        if (found) return found
      }
    }
    return null
  }

  // ─── Editor Tabs ───────────────────────────────
  const tabs = ref<EditorTab[]>([])
  const activeTabId = ref<string | null>(null)

  const activeTab = computed(() =>
    tabs.value.find(t => t.id === activeTabId.value) ?? null
  )
  const sortedTabs = computed(() =>
    [...tabs.value].sort((a, b) => a.order - b.order)
  )

  async function openFile(filePath: string): Promise<void> {
    const existing = tabs.value.find(t => t.filePath === filePath)
    if (existing) {
      activeTabId.value = existing.id
      return
    }

    const label = filePath.split(/[/\\]/).pop() ?? filePath
    const language = getLanguageFromPath(filePath)
    const demoContent = generateDemoContent(label, language)

    const newTab: EditorTab = {
      id: uid(),
      label,
      filePath,
      language,
      content: demoContent,
      originalContent: demoContent,
      modified: false,
      order: tabs.value.length,
    }

    tabs.value.push(newTab)
    activeTabId.value = newTab.id
    selectedFilePath.value = filePath
  }

  function createUntitledTab(): void {
    const newTab: EditorTab = {
      id: uid(),
      label: `未命名-${tabs.value.filter(t => !t.filePath).length + 1}`,
      content: '',
      originalContent: '',
      modified: false,
      language: 'plaintext',
      order: tabs.value.length,
    }
    tabs.value.push(newTab)
    activeTabId.value = newTab.id
  }

  function closeTab(tabId: string): void {
    const idx = tabs.value.findIndex(t => t.id === tabId)
    if (idx === -1) return
    tabs.value.splice(idx, 1)

    if (activeTabId.value === tabId) {
      if (tabs.value.length > 0) {
        const nextIdx = Math.min(idx, tabs.value.length - 1)
        activeTabId.value = sortedTabs.value[nextIdx]?.id ?? null
      } else {
        activeTabId.value = null
      }
    }
  }

  function updateActiveTabContent(content: string): void {
    const tab = activeTab.value
    if (!tab) return
    tab.content = content
    tab.modified = content !== tab.originalContent
  }

  const cursorPosition = ref<CursorPosition>({
    line: 1, column: 1, totalLines: 1, selectedChars: 0,
    encoding: 'UTF-8', eol: '\n', languageId: 'plaintext',
    fileType: '', indentSize: 2, indentUsesTabs: false,
  })

  function updateCursorPosition(pos: Partial<CursorPosition>): void {
    Object.assign(cursorPosition.value, pos)
  }

  // ─── Right Panel ───────────────────────────────
  const rightPanelView = ref<RightPanelView>('chat')

  // ─── Terminal Sessions ─────────────────────────
  const terminalSessions = ref<TerminalSession[]>([
    {
      id: uid(), title: '终端', shellType: 'powershell',
      lines: [
        { id: uid(), text: 'Windows PowerShell', type: 'info', timestamp: Date.now() },
        { id: uid(), text: 'Copyright (C) Microsoft Corporation. All rights reserved.', type: 'info', timestamp: Date.now() },
        { id: uid(), text: '', type: 'info', timestamp: Date.now() },
        { id: uid(), text: 'Try the new cross-platform PowerShell https://aka.ms/PS6', type: 'info', timestamp: Date.now() },
      ],
      active: true, cwd: 'D:\\code\\ai-fullstack-platform',
    },
  ])
  const activeTerminalId = computed(
    () => terminalSessions.value.find(t => t.active)?.id ?? null
  )

  function addTerminalLine(text: string, type: TerminalSession['lines'][0]['type'] = 'output'): void {
    const term = terminalSessions.value.find(t => t.active)
    if (!term) return
    term.lines.push({ id: uid(), text, type, timestamp: Date.now() })
  }

  // ─── Output Channels ───────────────────────────
  const outputChannels = ref<OutputChannel>([
    { id: 'output', name: '输出', visible: true, lines: ['[信息] CodeBuddy IDE v0.1.0 已启动', '[信息] 工作区: ai-fullstack-platform'] },
    { id: 'problems', name: '问题', visible: false, lines: [] },
    { id: 'debug-console', name: '调试控制台', visible: false, lines: [] },
  ])
  const activeOutputChannel = ref('output')

  // ─── Global Search ─────────────────────────────
  const searchState = ref<SearchState>({
    query: '', replaceQuery: '', includePattern: '*.ts,*.vue,*.py,*.json',
    excludePattern: 'node_modules,dist,.git', results: [], searching: false,
    caseSensitive: false, wholeWord: false, useRegex: false, currentResultIndex: -1,
  })
  const showGlobalSearch = ref(false)

  function toggleGlobalSearch(): void {
    showGlobalSearch.value = !showGlobalSearch.value
  }

  // ─── Activity Bar Items ────────────────────────
  const activityItems = computed<ActivityItem[]>(() => [
    { id: 'explorer', icon: 'Files', label: '资源管理器', badge: undefined },
    { id: 'studio', icon: 'Sparkles', label: 'AI Studio', badge: undefined },
    { id: 'search', icon: 'Search', label: '搜索', badge: undefined },
    { id: 'git', icon: 'GitBranch', label: '源代码管理', badge: '9' },
    { id: 'debug', icon: 'Bug', label: '运行和调试', badge: undefined },
    { id: 'extensions', icon: 'Blocks', label: '扩展', badge: undefined },
  ])
  const activeActivityItem = ref('explorer')

  // ─── Menu Bar Data ─────────────────────────────
  const menuBarOpen = ref<string | null>(null)

  function generateDemoContent(fileName: string, lang: string): string {
    const contents: Record<string, string> = {
      typescript: `{
  "name": "studio-admin",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "description": "AI Studio 管理端 - 项目管理 & 模板管理",
  "packageManager": "pnpm@9.12.3",
  "scripts": {
    "dev": "vite --c -b && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "@tailwindcss/vite": "^4.3.0",
    "@vitejs/plugin-vue": "^6.0.7",
    "axios": "1.13.5",
    "lucide-vue-next": "^0.468.0"
  }
}`,
      python: `"""AI Fullstack Platform — FastAPI Main Entry"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.model_router import init_model_router, get_model_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[CodeBuddy] Initializing AI Fullstack Platform...")
    router = init_model_router()
    print(f"[CodeBuddy] ModelRouter ready, {len(router.registry)} models loaded")
    yield
    print("[CodeBuddy] Shutting down...")


app = FastAPI(
    title="AI Fullstack Platform API",
    version="0.1.0",
    description="Unified API Gateway for Studio + Video modules",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/v1/system/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18000)
`,
      json: `{
  "name": "ai-fullstack-platform",
  "private": true,
  "description": "AI Fullstack Platform — Studio + Video",
  "scripts": {
    "dev": "pnpm dev",
    "build": "pnpm build"
  },
  "workspaces": ["studio-admin", "studio-client", "video-admin", "video-client"]
}`,
      markdown: `# AI Fullstack Platform

> 基于 Vue3 + FastAPI 的全栈 AI 开发平台

## 项目结构

| 模块 | 说明 |
|------|------|
| **Studio** | AI 编程工具（截图转代码、自然语言生成项目） |
| **Video** | 视频生成工具（文字转视频、UI演示视频） |

## 核心能力

- **模型调度**: 本地优先 → API 回退 → 内置兜底
- **五层回退链**: 用户指定 → 本地最优 → 本地次优 → 第三方API → 内置基础
- **统一接口**: 所有模型走 ModelRequest/ModelResponse 契约

\`\`\`bash
# 启动后端
cd backend && uv run uvicorn app.main:app --reload

# 启动前端
cd studio-client && pnpm dev
\`\`\`
`,
      html: `<template>
  <div class="flex h-screen bg-[#1e1e2e] text-gray-200">
    <aside class="w-12 bg-[#181825] flex flex-col items-center py-2 gap-1">
      <button v-for="item in activities" :key="item.id"
        class="w-10 h-10 flex items-center justify-center rounded-md transition-colors"
        :class="activeActivity === item.id ? 'bg-white/10 text-white' : 'text-gray-500 hover:text-gray-300'"
        @click="activeActivity = item.id">
        <component :is="item.icon" :size="20" />
      </button>
    </aside>
    <main class="flex-1 flex flex-col overflow-hidden">
      <EditorArea />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import EditorArea from './components/EditorArea.vue'
</script>
`,
      yaml: `services:
  web:
    build: .
    ports:
      - "18000:18000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/app
    depends_on:
      db:
        condition: service_healthy
  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user"]
      interval: 5s
      retries: 5
volumes:
  pgdata:
`,
      toml: `[project]
name = "studio-backend"
version = "0.1.0"
description = "AI Fullstack Platform Backend"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.30.0",
  "sqlalchemy>=2.0.35",
  "httpx>=0.27.0",
]
`,
    }
    if (contents[lang]) return contents[lang]
    if (['typescript','typescriptreact','javascript','javascriptreact'].includes(lang)) return contents.typescript
    if (['python','shell'].includes(lang)) return contents.python
    if (lang === 'json') return contents.json
    if (lang === 'markdown') return contents.markdown
    if (lang === 'html') return contents.html
    if (lang === 'yaml') return contents.yaml
    if (lang === 'toml') return contents.toml
    return `// ${fileName}\n// CodeBuddy IDE\n`
  }

  return {
    layout,
    fileTree, selectedFilePath, toggleExpand, findEntryByPath,
    tabs, activeTabId, activeTab, sortedTabs,
    openFile, createUntitledTab, closeTab, updateActiveTabContent,
    cursorPosition, updateCursorPosition,
    rightPanelView,
    terminalSessions, activeTerminalId, addTerminalLine,
    outputChannels, activeOutputChannel,
    searchState, showGlobalSearch, toggleGlobalSearch,
    activityItems, activeActivityItem,
    menuBarOpen,
  }
})
