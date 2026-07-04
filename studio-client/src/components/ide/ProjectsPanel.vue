<script setup lang="ts">
/**
 * ProjectsPanel — IDE 左侧 Activity Bar "项目" 面板
 *
 * 功能:
 *   - 列出当前用户的所有 AI 项目
 *   - 顶部"+"按钮快速创建项目
 *   - 搜索过滤
 *   - 点击项目 → 跳转到 /projects/:id (IDE 视图)
 *   - 右键菜单: 打开/在文件中查看/删除
 *
 * 设计参考: VSCode + Continue
 */
import { computed, onMounted, ref } from "vue"
import { useRouter } from "vue-router"
import {
  Briefcase,
  ExternalLink,
  FolderPlus,
  Loader2,
  Plus,
  RefreshCw,
  Search,
  Sparkles,
  Trash2,
} from "lucide-vue-next"
import { deleteProject, listProjects } from "@/api/studio"
import type { Project } from "@/types/studio"

const router = useRouter()
const projects = ref<Project[]>([])
const loading = ref(false)
const searchText = ref("")
const refreshing = ref(false)
const errorMsg = ref("")

async function load(silent = false): Promise<void> {
  if (silent) refreshing.value = true
  else loading.value = true
  errorMsg.value = ""
  try {
    const res = await listProjects()
    projects.value = res.data.data ?? []
  } catch (e: any) {
    errorMsg.value = e?.message ?? "加载失败"
    projects.value = []
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

onMounted(() => load())

const filteredProjects = computed(() => {
  if (!searchText.value.trim()) return projects.value
  const q = searchText.value.toLowerCase()
  return projects.value.filter(
    (p) =>
      p.name.toLowerCase().includes(q) ||
      p.description?.toLowerCase().includes(q),
  )
})

const statusLabel: Record<string, string> = {
  draft: "草稿",
  building: "构建中",
  deploying: "部署中",
  running: "运行中",
  failed: "失败",
}

const statusColor: Record<string, string> = {
  draft: "bg-gray-500/15 text-[var(--color-ide-text-dim)]",
  building: "bg-yellow-500/15 text-yellow-400",
  deploying: "bg-blue-500/15 text-blue-400",
  running: "bg-green-500/15 text-green-400",
  failed: "bg-red-500/15 text-red-400",
}

function goDetail(id: string): void {
  router.push(`/projects/${id}`)
}

function goCreate(): void {
  router.push("/projects/new")
}

async function handleDelete(e: Event, id: string, name: string): Promise<void> {
  e.stopPropagation()
  if (!confirm(`确定删除项目 "${name}" 吗？`)) return
  try {
    await deleteProject(id)
    projects.value = projects.value.filter((p) => p.id !== id)
  } catch {
    // toast 已在拦截器中显示
  }
}

function formatDate(s: string): string {
  if (!s) return ""
  const d = new Date(s)
  if (isNaN(d.getTime())) return s
  const now = Date.now()
  const diff = (now - d.getTime()) / 1000
  if (diff < 60) return "刚刚"
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  if (diff < 604800) return `${Math.floor(diff / 86400)} 天前`
  return d.toLocaleDateString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit" })
}
</script>

<template>
  <div class="projects-panel h-full flex flex-col overflow-hidden">
    <!-- 操作工具栏 -->
    <div class="shrink-0 flex items-center gap-1 px-2 py-1.5 border-b border-[var(--color-ide-border)]">
      <div class="relative flex-1">
        <Search
          class="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-[var(--color-ide-text-dim)] pointer-events-none"
        />
        <input
          v-model="searchText"
          type="text"
          placeholder="搜索项目…"
          class="w-full rounded-md bg-[var(--color-ide-surface-hover)] border border-transparent
                 pl-7 pr-2 py-1 text-[12px]
                 text-[var(--color-ide-text)] placeholder-[var(--color-ide-text-dim)]
                 focus:outline-none transition-colors focus:border-[#007ACC]/30"
        />
      </div>
      <button
        class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)]
               hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]
               transition-colors disabled:opacity-40"
        :disabled="refreshing"
        title="刷新"
        @click="load(true)"
      >
        <RefreshCw :size="13" :class="{ 'animate-spin': refreshing }" />
      </button>
      <button
        class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)]
               hover:bg-[var(--color-ide-surface-hover)] hover:text-[var(--color-ide-text)]
               transition-colors"
        title="新建项目"
        @click="goCreate"
      >
        <Plus :size="13" />
      </button>
    </div>

    <!-- 标题区 -->
    <div class="shrink-0 px-3 py-2 flex items-center justify-between">
      <div class="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-[var(--color-ide-text-dim)]">
        <Briefcase :size="12" />
        <span>我的项目</span>
        <span class="ml-1 text-[var(--color-ide-text-dim)]/70">({{ projects.length }})</span>
      </div>
    </div>

    <!-- 内容区 -->
    <div class="flex-1 overflow-y-auto overflow-x-hidden pb-2">
      <!-- 加载中 -->
      <div v-if="loading" class="px-4 py-8 text-center text-[var(--color-ide-text-dim)]">
        <Loader2 :size="16" class="mx-auto mb-2 animate-spin opacity-60" />
        <p class="text-[11px]">加载中…</p>
      </div>

      <!-- 错误 -->
      <div v-else-if="errorMsg" class="px-4 py-6 text-center">
        <p class="text-[11px] text-red-400 mb-2">{{ errorMsg }}</p>
        <button
          class="text-[11px] hover:underline"
          style="color: #007ACC;"
          @click="load()"
        >
          重试
        </button>
      </div>

      <!-- 空状态 -->
      <div v-else-if="!projects.length" class="px-4 py-10 text-center">
        <div
          class="w-12 h-12 mx-auto mb-3 rounded-xl flex items-center justify-center"
          style="background: var(--projects-empty-icon-bg);"
        >
          <Sparkles :size="20" style="color: var(--projects-accent-icon);" />
        </div>
        <p class="text-[12px] text-[var(--color-ide-text-dim)] mb-1">还没有项目</p>
        <p class="text-[11px] text-[var(--color-ide-text-dim)]/70 mb-3">创建你的第一个 AI 项目</p>
        <button
          class="inline-flex items-center gap-1 rounded-md text-white px-2.5 py-1.5 text-[11px] font-medium transition-all hover:shadow-md"
          style="background: var(--projects-create-btn-bg);"
          @click="goCreate"
        >
          <Plus :size="12" />
          创建项目
        </button>
      </div>

      <!-- 搜索无结果 -->
      <div v-else-if="!filteredProjects.length" class="px-4 py-8 text-center">
        <Search :size="20" class="mx-auto mb-2 text-[var(--color-ide-text-dim)]/40" />
        <p class="text-[11px] text-[var(--color-ide-text-dim)]">未找到匹配的项目</p>
      </div>

      <!-- 项目列表 -->
      <ul v-else class="space-y-0.5 px-1">
        <li
          v-for="p in filteredProjects"
          :key="p.id"
          class="group relative rounded-md border border-transparent
                 hover:border-[var(--color-ide-border)] hover:bg-[var(--color-ide-surface-hover)]
                 transition-all duration-150 cursor-pointer"
          @click="goDetail(p.id)"
        >
          <div class="flex items-start gap-2 px-2.5 py-2">
            <!-- 项目图标 -->
            <div
              class="shrink-0 w-7 h-7 rounded-md flex items-center justify-center mt-0.5"
              style="background: var(--projects-item-icon-bg);"
            >
              <Briefcase :size="13" style="color: var(--projects-accent-icon);" />
            </div>

            <!-- 项目信息 -->
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-1.5">
                <span class="text-[12px] font-medium text-[var(--color-ide-text)] truncate">
                  {{ p.name }}
                </span>
                <span
                  :class="['shrink-0 rounded-full px-1.5 py-0 text-[9px] font-medium leading-[1.4rem]',
                           statusColor[p.status] || statusColor.draft]"
                >
                  {{ statusLabel[p.status] || p.status }}
                </span>
              </div>
              <p v-if="p.description" class="text-[11px] text-[var(--color-ide-text-dim)] truncate mt-0.5">
                {{ p.description }}
              </p>
              <p class="text-[10px] text-[var(--color-ide-text-dim)]/60 mt-0.5">
                {{ formatDate(p.created_at) }}
              </p>
            </div>

            <!-- 操作按钮 (hover 显示) -->
            <div
              class="absolute right-1.5 top-1.5 flex items-center gap-0.5
                     opacity-0 group-hover:opacity-100 transition-opacity"
            >
              <button
                class="w-5 h-5 flex items-center justify-center rounded
                       text-[var(--color-ide-text-dim)] hover:bg-white/10 hover:text-white
                       transition-colors"
                title="在 IDE 中打开"
                @click.stop="goDetail(p.id)"
              >
                <ExternalLink :size="11" />
              </button>
              <button
                class="w-5 h-5 flex items-center justify-center rounded
                       text-[var(--color-ide-text-dim)] hover:bg-red-500/15 hover:text-red-400
                       transition-colors"
                title="删除项目"
                @click="handleDelete($event, p.id, p.name)"
              >
                <Trash2 :size="11" />
              </button>
            </div>
          </div>
        </li>
      </ul>
    </div>

    <!-- 底部新建按钮 -->
    <div
      v-if="!loading && projects.length > 0"
      class="shrink-0 p-2 border-t border-[var(--color-ide-border)]"
    >
      <button
        class="w-full flex items-center justify-center gap-1.5 rounded-md py-1.5 text-[11px] font-medium transition-all"
        style="background: var(--projects-new-btn-bg); border: 1px solid var(--projects-new-btn-border); color: var(--projects-accent-text);"
        @click="goCreate"
      >
        <FolderPlus :size="12" />
        新建项目
      </button>
    </div>
  </div>
</template>

<style scoped>
/* ═══ 项目面板主题色（组件级 CSS 变量，VSCode 蓝主题） ═══ */
.projects-panel {
  --projects-accent-icon: rgba(0, 122, 204, 0.7);
  --projects-accent-text: #007ACC;
  --projects-empty-icon-bg: linear-gradient(135deg, rgba(0, 122, 204, 0.18), rgba(0, 90, 158, 0.18));
  --projects-item-icon-bg: linear-gradient(135deg, rgba(0, 122, 204, 0.3), rgba(0, 90, 158, 0.3));
  --projects-create-btn-bg: linear-gradient(90deg, #007ACC, #005A9E);
  --projects-new-btn-bg: linear-gradient(90deg, rgba(0, 122, 204, 0.15), rgba(0, 90, 158, 0.15));
  --projects-new-btn-border: rgba(0, 122, 204, 0.25);
}
</style>
