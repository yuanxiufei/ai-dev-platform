<script setup lang="ts">
/**
 * ExtensionsPanel — VS Code Extensions Viewlet (像素级对齐)
 *
 * 功能对标 VS Code 扩展视图:
 *   - 扩展搜索 (实时过滤)
 *   - 已安装 / 推荐 标签切换
 *   - 扩展卡片: 图标 + 名称 + 描述 + 作者 + 下载数 + 评分
 *   - 安装 / 卸载 / 启用 / 禁用 操作
 *   - 扩展详情 (点击展开)
 *   - 分类筛选
 */
import { ref, computed } from "vue"
import {
  Search, X, Blocks, Download, Star, Trash2, Power, PowerOff,
  RotateCw, ChevronRight, CheckCircle, AlertTriangle, ExternalLink,
  Shield, Zap, Puzzle
} from "lucide-vue-next"

// ── 扩展数据类型 ──
interface ExtensionInfo {
  id: string
  name: string
  displayName: string
  description: string
  version: string
  publisher: string
  publisherDisplayName: string
  icon?: string
  downloads: number
  rating: number
  ratingCount: number
  installed: boolean
  enabled: boolean
  category: string
  homepage?: string
  repository?: string
  isBuiltin: boolean
  size: string
  updatedAt: string
  // 详情
  detailDescription?: string
  features?: string[]
  screenshots?: string[]
}

// ── 模拟扩展列表 ──
const extensions = ref<ExtensionInfo[]>([
  {
    id: "codebuddy.ai-assistant",
    name: "ai-assistant",
    displayName: "CodeBuddy AI Assistant",
    description: "AI-powered coding assistant for smart completions and code generation",
    version: "2.5.1",
    publisher: "codebuddy",
    publisherDisplayName: "CodeBuddy",
    icon: "🤖",
    downloads: 1250000,
    rating: 4.8,
    ratingCount: 3200,
    installed: true,
    enabled: true,
    category: "AI & Machine Learning",
    isBuiltin: true,
    size: "12.4 MB",
    updatedAt: "2026-06-28",
    detailDescription: "CodeBuddy AI Assistant provides intelligent code completions, natural language to code generation, and context-aware suggestions. It supports over 50 programming languages and integrates seamlessly with your workflow.",
    features: ["智能代码补全", "自然语言生成代码", "上下文感知建议", "50+ 编程语言支持"],
  },
  {
    id: "ms-python.python",
    name: "python",
    displayName: "Python",
    description: "IntelliSense, linting, debugging, code formatting, refactoring, and more",
    version: "2026.8.0",
    publisher: "ms-python",
    publisherDisplayName: "Microsoft",
    icon: "🐍",
    downloads: 85000000,
    rating: 4.7,
    ratingCount: 15000,
    installed: true,
    enabled: true,
    category: "Programming Languages",
    isBuiltin: false,
    size: "28.6 MB",
    updatedAt: "2026-07-01",
    detailDescription: "Rich support for the Python language (for all actively supported versions of the language: >=3.8), including features such as IntelliSense (Pylance), linting, debugging, code navigation, code formatting, refactoring, variable explorer, test explorer, and more!",
    features: ["智能感知 (Pylance)", "Linting & 调试", "代码导航 & 格式化", "测试资源管理器"],
  },
  {
    id: "eamodio.gitlens",
    name: "gitlens",
    displayName: "GitLens — Git supercharged",
    description: "Supercharge Git within VS Code — Visualize code authorship at a glance",
    version: "15.6.0",
    publisher: "eamodio",
    publisherDisplayName: "GitKraken",
    icon: "🔍",
    downloads: 42000000,
    rating: 4.9,
    ratingCount: 8500,
    installed: false,
    enabled: false,
    category: "Version Control",
    isBuiltin: false,
    size: "18.2 MB",
    updatedAt: "2026-06-25",
    detailDescription: "GitLens supercharges Git within VS Code. Visualize code authorship at a glance via Git blame annotations and CodeLens, seamlessly navigate and explore Git repositories, gain valuable insights via rich visualizations and powerful comparison commands, and so much more.",
    features: ["Git Blame 注解", "代码镜头", "仓库可视化", "分支比较"],
  },
  {
    id: "dbaeumer.vscode-eslint",
    name: "vscode-eslint",
    displayName: "ESLint",
    description: "Integrates ESLint JavaScript into VS Code",
    version: "3.0.10",
    publisher: "dbaeumer",
    publisherDisplayName: "Microsoft",
    icon: "✅",
    downloads: 55000000,
    rating: 4.6,
    ratingCount: 11000,
    installed: false,
    enabled: false,
    category: "Linters",
    isBuiltin: false,
    size: "8.1 MB",
    updatedAt: "2026-06-20",
    detailDescription: "The ESLint extension integrates ESLint into VS Code. If you are new to ESLint check the documentation. The extension uses the ESLint library installed in the opened workspace folder.",
    features: ["实时 Linting", "自动修复", "配置规则", "插件支持"],
  },
  {
    id: "esbenp.prettier-vscode",
    name: "prettier-vscode",
    displayName: "Prettier - Code formatter",
    description: "Code formatter using prettier",
    version: "11.0.0",
    publisher: "esbenp",
    publisherDisplayName: "Prettier",
    icon: "✨",
    downloads: 48000000,
    rating: 4.5,
    ratingCount: 7200,
    installed: false,
    enabled: false,
    category: "Formatters",
    isBuiltin: false,
    size: "6.4 MB",
    updatedAt: "2026-06-18",
    detailDescription: "Prettier is an opinionated code formatter. It enforces a consistent style by parsing your code and re-printing it with its own rules that take the maximum line length into account, wrapping code when necessary.",
    features: ["代码格式化", "多语言支持", "配置灵活", "保存时格式化"],
  },
  {
    id: "bierner.markdown-mermaid",
    name: "markdown-mermaid",
    displayName: "Markdown Preview Mermaid Support",
    description: "Adds Mermaid diagram and flowchart support to VS Code's built-in Markdown preview",
    version: "1.27.0",
    publisher: "bierner",
    publisherDisplayName: "Matt Bierner",
    icon: "📊",
    downloads: 8200000,
    rating: 4.7,
    ratingCount: 1800,
    installed: false,
    enabled: false,
    category: "Visualization",
    isBuiltin: false,
    size: "2.1 MB",
    updatedAt: "2026-05-15",
    detailDescription: "Adds support for rendering Mermaid diagrams and flowcharts in VS Code's built-in Markdown preview. Mermaid lets you create diagrams and visualizations using text and code.",
    features: ["Mermaid 图表渲染", "流程图", "序列图", "甘特图"],
  },
  {
    id: "github.copilot",
    name: "copilot",
    displayName: "GitHub Copilot",
    description: "Your AI pair programmer",
    version: "1.200.0",
    publisher: "github",
    publisherDisplayName: "GitHub",
    icon: "🧠",
    downloads: 65000000,
    rating: 4.3,
    ratingCount: 28000,
    installed: false,
    enabled: false,
    category: "AI & Machine Learning",
    isBuiltin: false,
    size: "22.8 MB",
    updatedAt: "2026-07-02",
    detailDescription: "GitHub Copilot is an AI pair programmer that helps you write code faster and with less work. It draws context from comments and code to suggest individual lines and whole functions instantly.",
    features: ["代码自动补全", "Chat 对话", "上下文感知", "多语言支持"],
  },
  {
    id: "redhat.vscode-yaml",
    name: "vscode-yaml",
    displayName: "YAML",
    description: "YAML Language Support by Red Hat, with built-in Kubernetes syntax support",
    version: "1.16.0",
    publisher: "redhat",
    publisherDisplayName: "Red Hat",
    icon: "📋",
    downloads: 38000000,
    rating: 4.7,
    ratingCount: 4500,
    installed: false,
    enabled: false,
    category: "Programming Languages",
    isBuiltin: false,
    size: "5.8 MB",
    updatedAt: "2026-06-22",
    detailDescription: "Provides comprehensive YAML Language support to Visual Studio Code, via the yaml-language-server, with built-in Kubernetes and Kedge syntax support.",
    features: ["YAML 语法高亮", "Schema 验证", "Kubernetes 支持", "自动完成"],
  },
  {
    id: "vue.volar",
    name: "volar",
    displayName: "Vue - Official",
    description: "Language support for Vue 3 - TypeScript, templates, CSS and more",
    version: "2.2.6",
    publisher: "vue",
    publisherDisplayName: "Vue",
    icon: "💚",
    downloads: 18000000,
    rating: 4.8,
    ratingCount: 6200,
    installed: true,
    enabled: true,
    category: "Programming Languages",
    isBuiltin: false,
    size: "15.3 MB",
    updatedAt: "2026-06-30",
    detailDescription: "Official Vue.js extension for VS Code. Provides TypeScript integration, template IntelliSense, CSS support, and more for Vue Single File Components (SFCs).",
    features: ["TypeScript 集成", "模板智能感知", "CSS 支持", "SFC 语法高亮"],
  },
  {
    id: "streetsidesoftware.code-spell-checker",
    name: "code-spell-checker",
    displayName: "Code Spell Checker",
    description: "Spelling checker for source code",
    version: "4.0.12",
    publisher: "streetsidesoftware",
    publisherDisplayName: "Street Side Software",
    icon: "📝",
    downloads: 25000000,
    rating: 4.4,
    ratingCount: 3800,
    installed: false,
    enabled: false,
    category: "Utilities",
    isBuiltin: false,
    size: "7.2 MB",
    updatedAt: "2026-06-15",
    detailDescription: "A basic spell checker that works well with camelCase code. The goal of this spell checker is to help catch common spelling errors while keeping the number of false positives low.",
    features: ["拼写检查", "camelCase 支持", "多语言词典", "忽略列表"],
  },
  {
    id: "bradlc.vscode-tailwindcss",
    name: "vscode-tailwindcss",
    displayName: "Tailwind CSS IntelliSense",
    description: "Intelligent Tailwind CSS tooling for VS Code",
    version: "0.12.18",
    publisher: "bradlc",
    publisherDisplayName: "Tailwind Labs",
    icon: "🎨",
    downloads: 22000000,
    rating: 4.8,
    ratingCount: 5400,
    installed: false,
    enabled: false,
    category: "CSS & Styling",
    isBuiltin: false,
    size: "9.6 MB",
    updatedAt: "2026-06-28",
    detailDescription: "Tailwind CSS IntelliSense enhances the Tailwind development experience by providing Visual Studio Code users with advanced features such as autocomplete, syntax highlighting, and linting.",
    features: ["类名自动完成", "语法高亮", "Linting", "悬停预览"],
  },
  {
    id: "ms-vscode-remote.remote-ssh",
    name: "remote-ssh",
    displayName: "Remote - SSH",
    description: "Open any folder on a remote machine using SSH and take advantage of VS Code's full feature set",
    version: "0.115.0",
    publisher: "ms-vscode-remote",
    publisherDisplayName: "Microsoft",
    icon: "🌐",
    downloads: 28000000,
    rating: 4.6,
    ratingCount: 6200,
    installed: false,
    enabled: false,
    category: "Remote Development",
    isBuiltin: false,
    size: "21.5 MB",
    updatedAt: "2026-06-26",
    detailDescription: "The Remote - SSH extension lets you use any remote machine with a SSH server as your development environment. This can greatly simplify development and troubleshooting in a wide variety of situations.",
    features: ["远程开发", "SSH 连接", "端口转发", "扩展同步"],
  },
])

// ── 搜索与筛选 ──
const searchQuery = ref("")
const activeTab = ref<"installed" | "marketplace">("installed")
const selectedCategory = ref<string | null>(null)
const expandedExt = ref<string | null>(null)
const installing = ref<Record<string, boolean>>({})

// ── 分类列表 ──
const categories = computed(() => {
  const cats = new Set<string>()
  for (const ext of extensions.value) {
    cats.add(ext.category)
  }
  return Array.from(cats).sort()
})

// ── 过滤后的扩展列表 ──
const filteredExtensions = computed(() => {
  let list = extensions.value

  // 按 tab 筛选
  if (activeTab.value === "installed") {
    list = list.filter(e => e.installed)
  }

  // 按分类筛选
  if (selectedCategory.value) {
    list = list.filter(e => e.category === selectedCategory.value)
  }

  // 按搜索词筛选
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(e =>
      e.displayName.toLowerCase().includes(q) ||
      e.description.toLowerCase().includes(q) ||
      e.publisher.toLowerCase().includes(q) ||
      e.name.toLowerCase().includes(q)
    )
  }

  return list
})

// ── 操作 ──
function toggleExtension(ext: ExtensionInfo): void {
  ext.enabled = !ext.enabled
}

async function installExtension(ext: ExtensionInfo): Promise<void> {
  installing.value[ext.id] = true
  // 模拟安装延迟
  await new Promise(r => setTimeout(r, 1200))
  ext.installed = true
  ext.enabled = true
  installing.value[ext.id] = false
}

function uninstallExtension(ext: ExtensionInfo): void {
  if (ext.isBuiltin) return
  ext.installed = false
  ext.enabled = false
  if (expandedExt.value === ext.id) expandedExt.value = null
}

function toggleDetail(extId: string): void {
  expandedExt.value = expandedExt.value === extId ? null : extId
}

function formatDownloads(n: number): string {
  if (n >= 1000000) return `${(n / 1000000).toFixed(1)}M`
  if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
  return String(n)
}

function formatRating(r: number): string {
  const full = Math.floor(r)
  const half = r - full >= 0.5
  return "★".repeat(full) + (half ? "½" : "") + "☆".repeat(5 - full - (half ? 1 : 0))
}
</script>

<template>
  <div class="extensions-panel flex flex-col h-full text-[13px]"
    style="color: var(--color-ide-text); background: var(--color-ide-surface);">

    <!-- ═══ 搜索框 ═══ -->
    <div class="shrink-0 px-3 pt-3 pb-2"
      style="border-bottom: 1px solid var(--color-ide-border);">
      <div class="flex items-center gap-1 border rounded-[3px] overflow-hidden"
        :style="{
          background: 'var(--color-chat-input-bg)',
          borderColor: searchQuery.trim() ? 'var(--color-ide-border-focus)' : 'transparent',
        }">
        <Search :size="14" class="ml-2" style="color: var(--color-ide-text-dim);" />
        <input
          v-model="searchQuery"
          type="text"
          class="flex-1 h-7 bg-transparent text-[13px] outline-none px-1"
          placeholder="在扩展市场中搜索扩展"
        />
        <button
          v-if="searchQuery"
          class="shrink-0 w-7 h-7 flex items-center justify-center hover:bg-[var(--color-ide-surface-hover)] rounded-[3px]"
          @click="searchQuery = ''"
        >
          <X :size="12" style="color: var(--color-ide-text-dim);" />
        </button>
      </div>
    </div>

    <!-- ═══ 标签切换 + 分类筛选 ═══ -->
    <div class="shrink-0 flex items-center gap-0 px-3 h-8"
      style="border-bottom: 1px solid var(--color-ide-border);">
      <button
        class="h-full flex items-center px-3 text-[11px] font-semibold uppercase tracking-wider relative transition-colors"
        :class="activeTab === 'installed'
          ? 'text-[var(--color-ide-text)]'
          : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]'"
        @click="activeTab = 'installed'; selectedCategory = null"
      >
        已安装
        <div v-if="activeTab === 'installed'" class="absolute bottom-0 left-3 right-3"
          style="height: 2px; background: var(--color-ide-accent); border-radius: 1px 1px 0 0;" />
      </button>
      <button
        class="h-full flex items-center px-3 text-[11px] font-semibold uppercase tracking-wider relative transition-colors"
        :class="activeTab === 'marketplace'
          ? 'text-[var(--color-ide-text)]'
          : 'text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]'"
        @click="activeTab = 'marketplace'; selectedCategory = null"
      >
        市场
        <div v-if="activeTab === 'marketplace'" class="absolute bottom-0 left-3 right-3"
          style="height: 2px; background: var(--color-ide-accent); border-radius: 1px 1px 0 0;" />
      </button>

      <!-- 🔥 分类筛选下拉 -->
      <div class="flex-1" />
      <select
        class="h-6 text-[11px] rounded-[3px] px-2 border-0 outline-none cursor-pointer"
        :style="{
          background: 'var(--color-chat-input-bg)',
          color: 'var(--color-ide-text)',
          border: '1px solid var(--color-ide-border)',
        }"
        v-model="selectedCategory"
        @change="selectedCategory = selectedCategory || null"
      >
        <option :value="null">所有分类</option>
        <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
      </select>
    </div>

    <!-- ═══ 扩展列表 ═══ -->
    <div class="flex-1 overflow-y-auto min-h-0 py-1">
      <div
        v-for="ext in filteredExtensions"
        :key="ext.id"
        class="extension-item"
        :class="{ 'expanded': expandedExt === ext.id }"
      >
        <!-- 🔥 扩展卡片 (紧凑模式) -->
        <div
          class="extension-card flex items-start gap-3 px-3 py-2 cursor-pointer hover:bg-[var(--color-ide-surface-hover)] transition-colors"
          :class="{ 'border-l-2 border-[var(--color-ide-accent)]': expandedExt === ext.id }"
          @click="toggleDetail(ext.id)"
        >
          <!-- 图标 -->
          <div
            class="shrink-0 w-9 h-9 rounded-md flex items-center justify-center text-lg"
            :style="{
              background: ext.installed ? 'var(--color-ide-accent)' : 'var(--color-ide-surface-hover)',
              border: ext.installed ? 'none' : '1px solid var(--color-ide-border)',
            }"
          >
            {{ ext.icon || ext.displayName.charAt(0) }}
          </div>

          <!-- 信息 -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="text-[13px] font-semibold truncate">{{ ext.displayName }}</span>
              <span
                v-if="ext.installed"
                class="shrink-0 text-[9px] px-1.5 py-0 rounded-full font-semibold"
                :class="ext.enabled ? 'bg-[var(--color-ide-success)]/20 text-[var(--color-ide-success)]' : 'bg-[var(--color-ide-text-dim)]/20 text-[var(--color-ide-text-dim)]'"
              >
                {{ ext.enabled ? '已启用' : '已禁用' }}
              </span>
              <span
                v-if="ext.isBuiltin"
                class="shrink-0 text-[9px] px-1.5 py-0 rounded-full font-medium"
                style="background: rgba(117,190,255,0.12); color: var(--color-ide-info);"
              >
                内置
              </span>
            </div>
            <div class="flex items-center gap-2 mt-0.5">
              <span class="text-[11px] truncate" style="color: var(--color-ide-text-dim);">
                {{ ext.description }}
              </span>
            </div>
            <div class="flex items-center gap-3 mt-1">
              <span class="text-[10px]" style="color: var(--color-ide-text-dim);">
                {{ ext.publisherDisplayName }}
              </span>
              <span class="text-[10px] flex items-center gap-0.5" style="color: var(--color-ide-text-dim);">
                <Download :size="10" opacity="0.5" />
                {{ formatDownloads(ext.downloads) }}
              </span>
              <span class="text-[10px] flex items-center gap-0.5" style="color: var(--color-ide-warning);">
                <Star :size="10" />
                {{ ext.rating }}
              </span>
            </div>
          </div>

          <!-- 🔥 操作按钮组 -->
          <div class="flex items-center gap-1 shrink-0" @click.stop>
            <!-- 安装/卸载按钮 -->
            <button
              v-if="!ext.installed"
              class="btn-install flex items-center gap-1 px-2 h-6 rounded-[3px] text-[11px] font-medium transition-all"
              :disabled="installing[ext.id]"
              @click="installExtension(ext)"
              :style="{
                background: installing[ext.id] ? 'var(--color-ide-surface-hover)' : 'var(--color-ide-accent)',
                color: installing[ext.id] ? 'var(--color-ide-text-dim)' : '#FFFFFF',
                opacity: installing[ext.id] ? 0.6 : 1,
              }"
            >
              <RotateCw v-if="installing[ext.id]" :size="11" class="animate-spin" />
              <Download v-else :size="11" />
              {{ installing[ext.id] ? '安装中...' : '安装' }}
            </button>

            <!-- 启用/禁用按钮 -->
            <button
              v-if="ext.installed"
              class="w-6 h-6 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-active)] transition-colors"
              :title="ext.enabled ? '禁用' : '启用'"
              @click="toggleExtension(ext)"
            >
              <Power v-if="ext.enabled" :size="13" style="color: var(--color-ide-success);" />
              <PowerOff v-else :size="13" style="color: var(--color-ide-text-dim);" />
            </button>

            <!-- 卸载按钮 -->
            <button
              v-if="ext.installed && !ext.isBuiltin"
              class="w-6 h-6 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-active)] transition-colors"
              title="卸载"
              @click="uninstallExtension(ext)"
            >
              <Trash2 :size="12" style="color: var(--color-ide-error);" />
            </button>

            <!-- 展开箭头 -->
            <ChevronRight
              :size="14"
              class="transition-transform duration-150"
              :class="{ 'rotate-90': expandedExt === ext.id }"
              style="color: var(--color-ide-text-dim);"
            />
          </div>
        </div>

        <!-- 🔥 扩展详情 (展开) -->
        <div v-if="expandedExt === ext.id" class="extension-detail px-6 py-3"
          style="border-top: 1px solid var(--color-ide-border); border-bottom: 1px solid var(--color-ide-border);">
          <!-- 简介 -->
          <div v-if="ext.detailDescription" class="mb-3">
            <p class="text-[12px] leading-relaxed" style="color: var(--color-ide-text);">
              {{ ext.detailDescription }}
            </p>
          </div>

          <!-- 特性列表 -->
          <div v-if="ext.features && ext.features.length > 0" class="mb-3">
            <span class="text-[10px] uppercase tracking-wider font-semibold mb-1.5 block"
              style="color: var(--color-ide-text-dim);">特性</span>
            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="f in ext.features"
                :key="f"
                class="text-[11px] px-2 py-0.5 rounded-[3px]"
                style="background: var(--color-ide-surface-hover); color: var(--color-ide-text); border: 1px solid var(--color-ide-border);"
              >
                {{ f }}
              </span>
            </div>
          </div>

          <!-- 元信息 -->
          <div class="grid grid-cols-2 gap-x-6 gap-y-1">
            <div class="flex items-center gap-2 text-[11px]">
              <span style="color: var(--color-ide-text-dim);">版本:</span>
              <span style="color: var(--color-ide-text); font-family: monospace;">{{ ext.version }}</span>
            </div>
            <div class="flex items-center gap-2 text-[11px]">
              <span style="color: var(--color-ide-text-dim);">大小:</span>
              <span style="color: var(--color-ide-text);">{{ ext.size }}</span>
            </div>
            <div class="flex items-center gap-2 text-[11px]">
              <span style="color: var(--color-ide-text-dim);">更新:</span>
              <span style="color: var(--color-ide-text);">{{ ext.updatedAt }}</span>
            </div>
            <div class="flex items-center gap-2 text-[11px]">
              <span style="color: var(--color-ide-text-dim);">分类:</span>
              <span style="color: var(--color-ide-accent); cursor: pointer;" @click="selectedCategory = ext.category">{{ ext.category }}</span>
            </div>
          </div>

          <!-- 操作按钮 -->
          <div class="flex items-center gap-2 mt-3">
            <button
              v-if="!ext.installed"
              class="flex items-center gap-1 px-3 h-7 rounded-[3px] text-[12px] font-medium transition-colors"
              :style="{ background: 'var(--color-ide-accent)', color: '#FFFFFF' }"
              @click="installExtension(ext)"
            >
              <Download :size="12" /> 安装
            </button>
            <button
              v-if="ext.installed && !ext.isBuiltin"
              class="flex items-center gap-1 px-3 h-7 rounded-[3px] text-[12px] font-medium transition-colors hover:bg-[var(--color-ide-surface-active)]"
              style="color: var(--color-ide-error);"
              @click="uninstallExtension(ext)"
            >
              <Trash2 :size="12" /> 卸载
            </button>
            <button
              v-if="ext.homepage || ext.repository"
              class="flex items-center gap-1 px-3 h-7 rounded-[3px] text-[12px] font-medium transition-colors hover:bg-[var(--color-ide-surface-hover)]"
              style="color: var(--color-ide-text-dim);"
              @click="window.open(ext.homepage || ext.repository, '_blank')"
            >
              <ExternalLink :size="12" /> 主页
            </button>
          </div>
        </div>
      </div>

      <!-- 🔥 空状态 -->
      <div v-if="filteredExtensions.length === 0 && !searchQuery.trim()"
        class="flex flex-col items-center justify-center py-16 gap-2">
        <Blocks :size="32" style="color: var(--color-ide-text-dim); opacity: 0.2;" />
        <span class="text-[12px]" style="color: var(--color-ide-text-dim);">
          {{ activeTab === 'installed' ? '没有已安装的扩展' : '扩展市场暂无内容' }}
        </span>
        <button
          v-if="activeTab === 'installed'"
          class="mt-2 px-4 py-1.5 rounded-[3px] text-[12px] font-medium transition-colors"
          :style="{ background: 'var(--color-ide-accent)', color: '#FFFFFF' }"
          @click="activeTab = 'marketplace'"
        >
          浏览市场
        </button>
      </div>

      <div v-if="filteredExtensions.length === 0 && searchQuery.trim()"
        class="flex flex-col items-center justify-center py-16 gap-2">
        <Search :size="24" style="color: var(--color-ide-text-dim); opacity: 0.2;" />
        <span class="text-[12px]" style="color: var(--color-ide-text-dim);">
          未找到 "{{ searchQuery }}" 相关扩展
        </span>
        <button
          class="mt-1 text-[11px] hover:underline"
          style="color: var(--color-ide-accent);"
          @click="searchQuery = ''"
        >清除搜索</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ═══ 扩展列表项 ═══ */
.extension-item {
  border-bottom: 1px solid transparent;
}
.extension-item:hover {
  border-bottom-color: var(--color-ide-border);
}
.extension-item.expanded {
  border-bottom-color: var(--color-ide-border);
}

/* ═══ 安装按钮 ═══ */
.btn-install {
  border: none;
  cursor: pointer;
}
.btn-install:disabled {
  cursor: not-allowed;
}
.btn-install:hover:not(:disabled) {
  filter: brightness(1.1);
}

/* ═══ 扩展详情 ═══ */
.extension-detail {
  background: rgba(0, 0, 0, 0.15);
}
</style>
