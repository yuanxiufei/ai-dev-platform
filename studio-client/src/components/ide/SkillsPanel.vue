<script setup lang="ts">
/**
 * CodeBuddy IDE — Skills Panel (Hermes-Enhanced)
 * Skills list with enable/disable, search, and detail view
 */
import { computed, onMounted, ref } from "vue"
import { Bookmark, ChevronRight, ExternalLink, RefreshCw, Search, Sparkles, ToggleLeft, ToggleRight, X } from "lucide-vue-next"
import apiClient from "@/api/client"

interface SkillInfo {
  name: string
  description?: string
  enabled?: boolean
  source?: string
  pinned?: boolean
  useCount?: number
}

interface SkillCategory {
  name: string
  description?: string
  skills: SkillInfo[]
}

const categories = ref<SkillCategory[]>([])
const loading = ref(false)
const searchQuery = ref('')
const selectedSkill = ref<SkillInfo | null>(null)
const skillContent = ref('')
const skillContentLoading = ref(false)

const filteredCategories = computed(() => {
  if (!searchQuery.value.trim()) return categories.value
  const q = searchQuery.value.toLowerCase()
  return categories.value
    .map(c => ({
      ...c,
      skills: c.skills.filter(s => s.name.toLowerCase().includes(q) || (s.description || '').toLowerCase().includes(q)),
    }))
    .filter(c => c.skills.length > 0)
})

const sourceLabels: Record<string, string> = {
  builtin: '内置', hub: 'Hub', local: '本地', external: '外部',
}
const sourceColors: Record<string, string> = {
  builtin: 'text-blue-400', hub: 'text-purple-400', local: 'text-green-400', external: 'text-orange-400',
}

async function fetchSkills() {
  loading.value = true
  try {
    const resp = await apiClient.get('/skills/list')
    if (resp.data?.categories) {
      categories.value = resp.data.categories
    } else if (Array.isArray(resp.data)) {
      categories.value = resp.data
    } else if (resp.data?.skills) {
      categories.value = [{ name: '通用', description: '', skills: resp.data.skills }]
    }
  } catch {
    // Use demo data for offline mode
    categories.value = [
      {
        name: '开发工具',
        description: '代码生成与项目管理',
        skills: [
          { name: 'frontend-design', description: '前端UI设计与组件生成', enabled: true, source: 'builtin', useCount: 42 },
          { name: 'code-review', description: '代码审查与质量分析', enabled: true, source: 'builtin', useCount: 28 },
          { name: 'debug', description: '调试分析与错误定位', enabled: true, source: 'builtin', useCount: 35 },
          { name: 'test-gen', description: '自动生成测试用例', enabled: false, source: 'builtin' },
          { name: 'refactor', description: '代码重构建议', enabled: true, source: 'builtin', useCount: 15 },
        ],
      },
      {
        name: '文档与知识',
        description: '文档生成与知识管理',
        skills: [
          { name: 'explain', description: '代码解释与文档生成', enabled: true, source: 'builtin', useCount: 22 },
          { name: 'webapp-testing', description: 'Web应用端到端测试', enabled: false, source: 'builtin' },
          { name: 'pdf', description: 'PDF文档处理与编辑', enabled: true, source: 'hub', useCount: 8 },
          { name: 'docx', description: 'Word文档处理', enabled: false, source: 'hub' },
        ],
      },
      {
        name: '媒体与设计',
        description: '多媒体内容生成',
        skills: [
          { name: '多模态内容生成', description: '文生图、文生视频、图生3D', enabled: true, source: 'hub', useCount: 12 },
        ],
      },
    ]
  } finally {
    loading.value = false
  }
}

async function toggleSkill(skill: SkillInfo) {
  skill.enabled = !skill.enabled
  try {
    await apiClient.post('/skills/toggle', { name: skill.name, enabled: skill.enabled })
  } catch {
    skill.enabled = !skill.enabled // Revert on error
  }
}

async function viewSkillDetail(skill: SkillInfo) {
  selectedSkill.value = skill
  skillContentLoading.value = true
  skillContent.value = ''
  try {
    const resp = await apiClient.get(`/skills/${skill.name}/content`)
    skillContent.value = resp.data?.content || ''
  } catch {
    skillContent.value = `# ${skill.name}\n\n${skill.description || '暂无详细描述'}\n\n此技能的详细内容需要连接后端查看。`
  } finally {
    skillContentLoading.value = false
  }
}

function closeDetail() {
  selectedSkill.value = null
  skillContent.value = ''
}

onMounted(() => { fetchSkills() })
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden bg-[var(--color-ide-surface)]">
    <!-- Header -->
    <div class="flex items-center justify-between px-3 py-2 border-b border-[var(--color-ide-border)] shrink-0">
      <div class="flex items-center gap-2">
        <Sparkles :size="14" class="text-[var(--color-ide-accent)]" />
        <span class="text-[11px] font-semibold uppercase tracking-wider text-[var(--color-ide-text)]">技能管理</span>
      </div>
      <button class="p-1 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]"
        @click="fetchSkills" :disabled="loading" title="刷新">
        <RefreshCw :size="12" :class="{ 'animate-spin': loading }" />
      </button>
    </div>

    <!-- Search -->
    <div class="px-2 py-1.5 border-b border-[var(--color-ide-border)]/50 shrink-0">
      <div class="flex items-center gap-2 px-2 py-1 rounded-md text-[11px] border border-[var(--color-ide-border)] bg-[var(--color-ide-bg-secondary)]">
        <Search :size="11" class="text-[var(--color-ide-text-dim)] shrink-0" />
        <input v-model="searchQuery" type="text" placeholder="搜索技能..."
          class="flex-1 bg-transparent outline-none text-[var(--color-ide-text)] text-[11px] placeholder:text-[var(--color-ide-text-dim)]" />
        <button v-if="searchQuery" @click="searchQuery=''" class="text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]">
          <X :size="10" />
        </button>
      </div>
    </div>

    <!-- Skills List -->
    <div class="flex-1 overflow-y-auto">
      <div v-if="loading" class="flex items-center justify-center py-8">
        <div class="flex gap-1.5">
          <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:0ms"/>
          <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:150ms"/>
          <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:300ms"/>
        </div>
      </div>

      <template v-else>
        <div v-for="cat in filteredCategories" :key="cat.name" class="border-b border-[var(--color-ide-border)]/30 last:border-0">
          <!-- Category Header -->
          <div class="flex items-center gap-2 px-3 py-1.5 cursor-pointer sticky top-0 z-10"
            style="background:var(--color-ide-bg-tertiary);">
            <Bookmark :size="10" class="text-[var(--color-ide-accent)]" />
            <span class="text-[10px] font-semibold uppercase tracking-widest text-[var(--color-ide-text-dim)]">{{ cat.name }}</span>
            <span class="text-[9px] opacity-50 text-[var(--color-ide-text-dim)]">{{ cat.skills.length }}</span>
          </div>

          <!-- Skills -->
          <div v-for="skill in cat.skills" :key="skill.name"
            class="flex items-center gap-2 px-3 py-1.5 hover:bg-[var(--color-ide-surface-hover)]/50 transition-colors cursor-pointer group"
            @click="viewSkillDetail(skill)">
            <!-- Enable/Disable Toggle -->
            <button class="shrink-0" @click.stop="toggleSkill(skill)"
              :class="skill.enabled ? 'text-green-400' : 'text-[var(--color-ide-text-dim)]/30 hover:text-[var(--color-ide-text-dim)]/60'">
              <component :is="skill.enabled ? ToggleRight : ToggleLeft" :size="14" />
            </button>

            <!-- Info -->
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-1.5">
                <span class="text-[11px] font-medium text-[var(--color-ide-text)] truncate" :class="{ 'opacity-40': !skill.enabled }">{{ skill.name }}</span>
                <span v-if="skill.source" class="text-[8px] px-1 rounded font-medium"
                  :class="sourceColors[skill.source] || 'text-[var(--color-ide-text-dim)]'"
                  style="background:var(--color-ide-bg-tertiary);">
                  {{ sourceLabels[skill.source] || skill.source }}
                </span>
              </div>
              <div v-if="skill.description" class="text-[9px] text-[var(--color-ide-text-dim)] truncate mt-0.5">{{ skill.description }}</div>
            </div>

            <!-- Meta -->
            <div class="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
              <span v-if="skill.useCount" class="text-[9px] text-[var(--color-ide-text-dim)]">{{ skill.useCount }}次</span>
              <ChevronRight :size="10" class="text-[var(--color-ide-text-dim)]" />
            </div>
          </div>
        </div>

        <div v-if="filteredCategories.length === 0 && !loading"
          class="flex flex-col items-center justify-center py-8 text-[var(--color-ide-text-dim)]">
          <Search :size="18" class="mb-2 opacity-30" />
          <p class="text-[11px]">未找到匹配的技能</p>
        </div>
      </template>
    </div>

    <!-- Skill Detail Overlay -->
    <Transition name="slide-up">
      <div v-if="selectedSkill" class="absolute inset-0 z-50 flex flex-col bg-[var(--color-ide-surface)]">
        <div class="flex items-center justify-between px-3 py-2 border-b border-[var(--color-ide-border)] shrink-0">
          <div class="flex items-center gap-2 min-w-0">
            <button class="p-0.5 rounded-md hover:bg-[var(--color-ide-surface-hover)] text-[var(--color-ide-text-dim)]"
              @click="closeDetail">
              <ChevronRight :size="14" class="rotate-180" />
            </button>
            <span class="text-[11px] font-semibold text-[var(--color-ide-text)] truncate">{{ selectedSkill.name }}</span>
          </div>
          <div class="flex items-center gap-1">
            <button class="shrink-0" @click="toggleSkill(selectedSkill)"
              :class="selectedSkill.enabled ? 'text-green-400' : 'text-[var(--color-ide-text-dim)]/30'">
              <component :is="selectedSkill.enabled ? ToggleRight : ToggleLeft" :size="14" />
            </button>
          </div>
        </div>
        <div class="flex-1 overflow-y-auto p-3">
          <div v-if="skillContentLoading" class="flex items-center justify-center py-12">
            <div class="flex gap-1.5">
              <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:0ms"/>
              <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:150ms"/>
              <span class="w-1.5 h-1.5 rounded-full animate-bounce bg-[var(--color-ide-accent)]" style="animation-delay:300ms"/>
            </div>
          </div>
          <pre v-else class="text-[11px] text-[var(--color-ide-text-secondary)] leading-relaxed whitespace-pre-wrap font-mono">{{ skillContent }}</pre>
        </div>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.slide-up-enter-active, .slide-up-leave-active { transition: transform 0.2s ease, opacity 0.2s ease; }
.slide-up-enter-from, .slide-up-leave-to { transform: translateY(8px); opacity: 0; }
</style>
