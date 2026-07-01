<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue"
import { useRoute, useRouter } from "vue-router"
import { getProject } from "@/api/studio"
import type { Project } from "@/types/studio"
import { useIDEStore } from "@/stores/useIDEStore"
import {
  ArrowLeft, LayoutGrid, FileText, Terminal, Play,
  Hammer, Rocket, Eye, Code2, FolderTree, RefreshCw,
} from "lucide-vue-next"

const route = useRoute()
const router = useRouter()
const ideStore = useIDEStore()

const project = ref<Project | null>(null)
const loading = ref(true)
const buildOutput = ref<string[]>([])
const building = ref(false)
const activePanel = ref<"files" | "terminal">("files")

const id = route.params.id as string

/* ─── 模拟项目文件结构 ─── */
interface FileNode {
  name: string
  path: string
  type: "file" | "dir"
  children?: FileNode[]
  language?: string
}
const mockFiles = computed<FileNode[]>(() => {
  const name = project.value?.name ?? "project"
  return [
    { name: "src", path: "/src", type: "dir", children: [
      { name: "App.vue", path: "/src/App.vue", type: "file", language: "vue" },
      { name: "main.ts", path: "/src/main.ts", type: "file", language: "typescript" },
      { name: "style.css", path: "/src/style.css", type: "file", language: "css" },
      { name: "components", path: "/src/components", type: "dir", children: [
        { name: "Header.vue", path: "/src/components/Header.vue", type: "file", language: "vue" },
        { name: "Footer.vue", path: "/src/components/Footer.vue", type: "file", language: "vue" },
      ]},
    ]},
    { name: "backend", path: "/backend", type: "dir", children: [
      { name: "main.py", path: "/backend/main.py", type: "file", language: "python" },
      { name: "requirements.txt", path: "/backend/requirements.txt", type: "file", language: "text" },
    ]},
    { name: "package.json", path: "/package.json", type: "file", language: "json" },
    { name: "README.md", path: "/README.md", type: "file", language: "markdown" },
  ]
})

const statusLabel: Record<string, string> = {
  draft: "草稿",
  building: "构建中",
  deploying: "部署中",
  running: "运行中",
  failed: "失败",
}

const statusColor: Record<string, string> = {
  draft: "bg-gray-500/20 text-[var(--color-ide-text-dim)]",
  building: "bg-yellow-500/20 text-yellow-400",
  deploying: "bg-blue-500/20 text-blue-400",
  running: "bg-green-500/20 text-green-400",
  failed: "bg-red-500/20 text-red-400",
}

/* ─── 文件树展开状态 ─── */
const expandedDirs = ref<Set<string>>(new Set(["/src", "/backend"]))

onMounted(async () => {
  try {
    const res = await getProject(id)
    project.value = res.data
  } catch {
    // 项目不存在或后端未启动
  } finally {
    loading.value = false
  }
})

/* ─── 操作函数 ─── */
const goBack = () => router.push("/projects")

const handleEditCode = () => {
  // 在IDE编辑器中打开项目文件
  const file = mockFiles.value[0] // src 目录
  if (file.children?.[0]) {
    const tab = ideStore.createUntitledTab()
    tab.content = `// ${project.value?.name ?? 'Project'} — 编辑视图\n// 在左侧文件树中选择要编辑的文件`
    tab.label = `${project.value?.name ?? 'Project'}`
  }
}

const handleBuild = async () => {
  building.value = true
  buildOutput.value = []
  const lines = [
    "[INFO] 开始构建项目...",
    "[INFO] ✓ 安装依赖...",
    "[INFO] ✓ 编译 TypeScript...",
    "[INFO] ✓ 打包资源...",
    "[INFO] ✓ 构建完成 (2.3s)",
    "[SUCCESS] 项目构建成功!",
  ]
  for (const line of lines) {
    buildOutput.value.push(line)
    await new Promise((r) => setTimeout(r, 300))
  }
  building.value = false
}

const handlePreview = () => {
  router.push(`/chat?project=${id}`)
}

const handleDeploy = () => {
  router.push(`/integrations?project=${id}`)
}

/* ─── 文件树点击 ─── */
const toggleDir = (dirPath: string) => {
  if (expandedDirs.value.has(dirPath)) {
    expandedDirs.value.delete(dirPath)
  } else {
    expandedDirs.value.add(dirPath)
  }
}

const fileIcon = (lang?: string): string => {
  const map: Record<string, string> = {
    vue: "🟢", typescript: "🔷", python: "🐍",
    css: "🎨", json: "📋", markdown: "📝",
    javascript: "🟡", text: "📄",
  }
  return map[lang ?? ""] ?? "📄"
}

const openFile = (node: FileNode) => {
  if (node.type === "dir") {
    toggleDir(node.path)
    return
  }
  ideStore.rightPanelView = "chat"
  ideStore.layout.rightPanelVisible = true
  buildOutput.value.push(`[INFO] 打开文件: ${node.name}`)
}

/* ─── 监听项目变化 ─── */
watch(() => project.value?.status, (newStatus) => {
  if (newStatus) {
    buildOutput.value.push(`[INFO] 项目状态变更为: ${statusLabel[newStatus] ?? newStatus}`)
  }
})

</script>

<template>
  <div class="h-full w-full overflow-hidden bg-[var(--color-ide-bg)] text-[var(--color-ide-text)]">
    <!-- 顶部导航 -->
    <header class="border-b border-[var(--color-ide-border)] bg-surface-900/50 backdrop-blur">
      <div class="max-w-7xl mx-auto px-6 py-4 flex items-center gap-4">
        <button
          class="p-2 rounded-lg hover:bg-white/10 text-[var(--color-ide-text-dim)] hover:text-white transition-colors"
          @click="goBack"
        >
          <ArrowLeft class="w-5 h-5" />
        </button>
        <div class="flex items-center gap-3 flex-1">
          <div class="w-8 h-8 rounded-lg bg-brand-500 flex items-center justify-center">
            <LayoutGrid class="w-4 h-4 text-white" />
          </div>
          <h1 class="text-lg font-semibold">{{ project?.name || '项目详情' }}</h1>
          <span
            v-if="project"
            :class="['rounded-full px-2.5 py-0.5 text-xs font-medium ml-2', statusColor[project.status] || statusColor.draft]"
          >
            {{ statusLabel[project.status] || project.status }}
          </span>
        </div>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-6 py-8">
      <!-- 加载 -->
      <div v-if="loading" class="py-20 text-center text-[var(--color-ide-text-dim)]">
        <div class="w-8 h-8 border-2 border-brand-500/30 border-t-brand-500 rounded-full animate-spin mx-auto mb-4" />
        加载中…
      </div>

      <!-- 项目不存在 -->
      <div v-else-if="!project" class="py-20 text-center">
        <p class="text-[var(--color-ide-text-dim)] text-lg">项目不存在</p>
        <button
          class="mt-4 rounded-lg bg-brand-500 hover:bg-brand-600 px-4 py-2 text-sm font-medium transition-colors"
          @click="goBack"
        >
          返回列表
        </button>
      </div>

      <!-- 项目详情 -->
      <div v-else class="space-y-5">
        <!-- 项目信息卡片 -->
        <div class="rounded-xl border border-[var(--color-ide-border)] bg-surface-800 p-5">
          <div class="flex items-start justify-between gap-4">
            <div class="flex-1 min-w-0">
              <h2 class="text-xl font-semibold truncate">{{ project.name }}</h2>
              <p class="text-[var(--color-ide-text-dim)] text-sm mt-1 truncate">{{ project.description || '暂无描述' }}</p>
              <div class="flex items-center gap-3 mt-2 text-xs text-[var(--color-ide-text-dim)]">
                <span>创建于 {{ project.created_at }}</span>
                <span v-if="project.updated_at">· 更新于 {{ project.updated_at }}</span>
              </div>
            </div>
            <!-- 快捷操作 -->
            <div class="flex items-center gap-2 shrink-0">
              <button
                class="flex items-center gap-1.5 rounded-lg border border-[var(--color-ide-border)] bg-surface-700 hover:bg-surface-600 px-3 py-1.5 text-xs text-[var(--color-ide-text)] transition-colors"
                @click="handleEditCode"
              >
                <Code2 class="w-3.5 h-3.5" /> 编辑
              </button>
              <button
                class="flex items-center gap-1.5 rounded-lg bg-indigo-500/20 hover:bg-indigo-500/30 text-indigo-400 px-3 py-1.5 text-xs font-medium transition-colors"
                @click="handleBuild"
                :disabled="building"
              >
                <Hammer :class="['w-3.5 h-3.5', building && 'animate-spin']" /> {{ building ? '构建中' : '构建' }}
              </button>
              <button
                class="flex items-center gap-1.5 rounded-lg bg-green-500/20 hover:bg-green-500/30 text-green-400 px-3 py-1.5 text-xs font-medium transition-colors"
                @click="handlePreview"
              >
                <Eye class="w-3.5 h-3.5" /> 预览
              </button>
              <button
                class="flex items-center gap-1.5 rounded-lg bg-purple-500/20 hover:bg-purple-500/30 text-purple-400 px-3 py-1.5 text-xs font-medium transition-colors"
                @click="handleDeploy"
              >
                <Rocket class="w-3.5 h-3.5" /> 部署
              </button>
            </div>
          </div>
        </div>

        <!-- 工作区 -->
        <div class="rounded-xl border border-[var(--color-ide-border)] bg-surface-800 overflow-hidden">
          <!-- 面板切换 -->
          <div class="flex items-center border-b border-[var(--color-ide-border)] bg-surface-850">
            <button
              :class="[
                'flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-colors border-b-2',
                activePanel === 'files'
                  ? 'border-brand-500 text-brand-400'
                  : 'border-transparent text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]',
              ]"
              @click="activePanel = 'files'"
            >
              <FolderTree class="w-3.5 h-3.5" /> 文件
            </button>
            <button
              :class="[
                'flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-colors border-b-2',
                activePanel === 'terminal'
                  ? 'border-brand-500 text-brand-400'
                  : 'border-transparent text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]',
              ]"
              @click="activePanel = 'terminal'"
            >
              <Terminal class="w-3.5 h-3.5" /> 终端输出
              <span v-if="buildOutput.length" class="w-4 h-4 rounded-full bg-brand-500/20 text-[10px] text-brand-400 flex items-center justify-center">{{ buildOutput.length }}</span>
            </button>
          </div>

          <!-- 文件面板 -->
          <div v-if="activePanel === 'files'" class="p-4 min-h-[300px]">
            <div class="grid grid-cols-2 gap-5">
              <!-- 文件树 -->
              <div>
                <h3 class="text-xs font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-3 flex items-center gap-1.5">
                  <FolderTree class="w-3.5 h-3.5" /> 项目文件
                </h3>
                <div class="rounded-lg border border-[var(--color-ide-border)] bg-surface-900/50 overflow-hidden">
                  <template v-for="node in mockFiles" :key="node.path">
                    <!-- 目录 -->
                    <template v-if="node.type === 'dir'">
                      <div
                        class="flex items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)] cursor-pointer transition-colors"
                        @click="toggleDir(node.path)"
                      >
                        <span class="text-[10px] w-3 text-center">
                          {{ expandedDirs.has(node.path) ? '▼' : '▶' }}
                        </span>
                        <FolderTree class="w-3.5 h-3.5 text-yellow-500/70" />
                        <span class="font-medium">{{ node.name }}/</span>
                      </div>
                      <template v-if="expandedDirs.has(node.path)">
                        <div
                          v-for="child in node.children"
                          :key="child.path"
                          class="flex items-center gap-2 pl-8 pr-3 py-1.5 text-xs text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] cursor-pointer transition-colors"
                          @click="openFile(child)"
                        >
                          <span class="w-3 text-center">{{ fileIcon(child.language) }}</span>
                          <span>{{ child.name }}</span>
                        </div>
                      </template>
                    </template>
                    <!-- 文件 -->
                    <div
                      v-else
                      class="flex items-center gap-2 pl-5 pr-3 py-1.5 text-xs text-[var(--color-ide-text)] hover:bg-[var(--color-ide-surface-hover)] cursor-pointer transition-colors"
                      @click="openFile(node)"
                    >
                      <span class="w-3 text-center">{{ fileIcon(node.language) }}</span>
                      <span>{{ node.name }}</span>
                    </div>
                  </template>
                </div>
              </div>

              <!-- 项目详情 -->
              <div class="space-y-4">
                <div>
                  <h3 class="text-xs font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-2">快捷入口</h3>
                  <div class="grid grid-cols-2 gap-2">
                    <button
                      class="flex items-center gap-2 rounded-lg border border-[var(--color-ide-border)] bg-surface-900/50 p-3 text-left hover:bg-[var(--color-ide-surface-hover)] transition-colors group"
                      @click="router.push('/chat')"
                    >
                      <div class="w-8 h-8 rounded-lg bg-indigo-500/15 flex items-center justify-center shrink-0">
                        <Code2 class="w-4 h-4 text-indigo-400" />
                      </div>
                      <div>
                        <div class="text-xs font-medium text-[var(--color-ide-text)] group-hover:text-white">AI 对话</div>
                        <div class="text-[10px] text-[var(--color-ide-text-dim)]">让 AI 帮你写代码</div>
                      </div>
                    </button>
                    <button
                      class="flex items-center gap-2 rounded-lg border border-[var(--color-ide-border)] bg-surface-900/50 p-3 text-left hover:bg-[var(--color-ide-surface-hover)] transition-colors group"
                      @click="router.push('/image-gen')"
                    >
                      <div class="w-8 h-8 rounded-lg bg-purple-500/15 flex items-center justify-center shrink-0">
                        <Eye class="w-4 h-4 text-purple-400" />
                      </div>
                      <div>
                        <div class="text-xs font-medium text-[var(--color-ide-text)] group-hover:text-white">生成素材</div>
                        <div class="text-[10px] text-[var(--color-ide-text-dim)]">AI 图片/语音</div>
                      </div>
                    </button>
                    <button
                      class="flex items-center gap-2 rounded-lg border border-[var(--color-ide-border)] bg-surface-900/50 p-3 text-left hover:bg-[var(--color-ide-surface-hover)] transition-colors group"
                      @click="router.push('/tools')"
                    >
                      <div class="w-8 h-8 rounded-lg bg-green-500/15 flex items-center justify-center shrink-0">
                        <Terminal class="w-4 h-4 text-green-400" />
                      </div>
                      <div>
                        <div class="text-xs font-medium text-[var(--color-ide-text)] group-hover:text-white">工具管理</div>
                        <div class="text-[10px] text-[var(--color-ide-text-dim)]">Agent 工具配置</div>
                      </div>
                    </button>
                    <button
                      class="flex items-center gap-2 rounded-lg border border-[var(--color-ide-border)] bg-surface-900/50 p-3 text-left hover:bg-[var(--color-ide-surface-hover)] transition-colors group"
                      @click="router.push('/knowledge')"
                    >
                      <div class="w-8 h-8 rounded-lg bg-yellow-500/15 flex items-center justify-center shrink-0">
                        <FileText class="w-4 h-4 text-yellow-400" />
                      </div>
                      <div>
                        <div class="text-xs font-medium text-[var(--color-ide-text)] group-hover:text-white">知识库</div>
                        <div class="text-[10px] text-[var(--color-ide-text-dim)]">项目文档管理</div>
                      </div>
                    </button>
                  </div>
                </div>
                <div>
                  <h3 class="text-xs font-semibold text-[var(--color-ide-text-dim)] uppercase tracking-wider mb-2">项目统计</h3>
                  <div class="rounded-lg border border-[var(--color-ide-border)] bg-surface-900/50 p-4 space-y-2">
                    <div class="flex justify-between text-xs">
                      <span class="text-[var(--color-ide-text-dim)]">状态</span>
                      <span :class="[statusColor[project.status] || statusColor.draft, 'rounded-full px-2 py-0.5 text-[10px] font-medium']">
                        {{ statusLabel[project.status] || project.status }}
                      </span>
                    </div>
                    <div class="flex justify-between text-xs">
                      <span class="text-[var(--color-ide-text-dim)]">文件数</span>
                      <span class="text-[var(--color-ide-text)]">{{ mockFiles.flatMap(f => f.type === 'dir' ? f.children ?? [] : [f]).length + mockFiles.filter(f => f.type === 'file').length }}</span>
                    </div>
                    <div class="flex justify-between text-xs">
                      <span class="text-[var(--color-ide-text-dim)]">框架</span>
                      <span class="text-[var(--color-ide-text)]">{{ project.framework ?? 'Vue 3' }}</span>
                    </div>
                    <div class="flex justify-between text-xs">
                      <span class="text-[var(--color-ide-text-dim)]">类型</span>
                      <span class="text-[var(--color-ide-text)]">{{ project.stack ?? '全栈' }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 终端面板 -->
          <div v-if="activePanel === 'terminal'" class="flex flex-col min-h-[300px]">
            <div class="flex-1 p-4 font-mono text-xs leading-relaxed space-y-0.5 bg-[#0d1117] max-h-[400px] overflow-y-auto">
              <div v-if="!buildOutput.length && !building" class="text-[var(--color-ide-text-dim)] py-8 text-center">
                <Terminal class="w-8 h-8 mx-auto mb-2 opacity-50" />
                点击"构建"按钮开始构建项目
              </div>
              <div
                v-for="(line, i) in buildOutput"
                :key="i"
                :class="[
                  line.startsWith('[SUCCESS]') ? 'text-green-400' :
                  line.startsWith('[ERROR]') ? 'text-red-400' :
                  line.startsWith('[WARN]') ? 'text-yellow-400' :
                  'text-[var(--color-ide-text-dim)]'
                ]"
              >{{ line }}</div>
              <div v-if="building" class="text-[var(--color-ide-text-dim)] animate-pulse">▊</div>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
