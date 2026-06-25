<script setup lang="ts">
import { Brain, Hash, Layers, Sparkles, Star } from "lucide-vue-next"
import { computed, onMounted, ref } from "vue"
import { type MemoryEntry, memoryApi } from "@/api/model-features"

const memories = ref<MemoryEntry[]>([])
const loading = ref(true)
const page = ref(1)
const sizeVal = ref(20)
const total = ref(0)
const filterDomain = ref("")
const domains = ["", "general", "personal", "project", "code"]
const _domainLabels: Record<string, string> = {
  "": "全部",
  general: "通用",
  personal: "个人",
  project: "项目",
  code: "代码",
}
const _domainIcons: Record<string, any> = {
  "": Layers,
  general: Brain,
  personal: Star,
  project: Hash,
  code: Sparkles,
}

const searchQuery = ref("")
const searchResults = ref<
  {
    id: string
    domain: string
    key: string
    value: string
    similarity: number
  }[]
>([])

const editingId = ref<string | null>(null)
const editKey = ref("")
const editValue = ref("")
const editDomain = ref("general")
const editImportance = ref(0.5)

const newKey = ref("")
const newValue = ref("")
const newDomain = ref("general")
const newImportance = ref(0.5)

const loadingStats = ref(false)
const memoryStats = ref({
  total_memories: 0,
  total_accesses: 0,
  by_domain: {} as Record<string, number>,
})

const toast = ref("")
function showToast(msg: string) {
  toast.value = msg
  setTimeout(() => {
    toast.value = ""
  }, 3000)
}

async function fetchMemories() {
  loading.value = true
  try {
    const res = await memoryApi.list({
      page: page.value,
      size: sizeVal.value,
      domain: filterDomain.value || undefined,
    })
    memories.value = res.data.data || []
    total.value = res.data.total || 0
  } catch {
    /* */
  } finally {
    loading.value = false
  }
}

async function fetchStats() {
  loadingStats.value = true
  try {
    const res = await memoryApi.stats()
    memoryStats.value = res.data || {
      total_memories: 0,
      total_accesses: 0,
      by_domain: {},
    }
  } catch {
    /* */
  } finally {
    loadingStats.value = false
  }
}

async function _doSearch() {
  if (!searchQuery.value) return
  try {
    const res = await memoryApi.search(
      searchQuery.value,
      filterDomain.value || undefined,
    )
    searchResults.value = res.data.results || []
  } catch {
    /* */
  }
}

async function _addMemory() {
  if (!newKey.value || !newValue.value) return
  try {
    await memoryApi.create({
      key: newKey.value,
      value: newValue.value,
      domain: newDomain.value,
      importance: newImportance.value,
    })
    newKey.value = ""
    newValue.value = ""
    showToast("记忆已添加")
    await Promise.all([fetchMemories(), fetchStats()])
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "添加失败")
  }
}

async function _deleteMemory(id: string) {
  if (!confirm("确定删除此记忆？")) return
  try {
    await memoryApi.delete(id)
    showToast("记忆已删除")
    await Promise.all([fetchMemories(), fetchStats()])
  } catch {
    /* */
  }
}

function _startEdit(m: MemoryEntry) {
  editingId.value = m.id
  editKey.value = m.key
  editValue.value = m.value
  editDomain.value = m.domain || "general"
  editImportance.value = m.importance || 0.5
}

async function _saveEdit() {
  if (!editingId.value) return
  try {
    await memoryApi.update(editingId.value, {
      key: editKey.value,
      value: editValue.value,
      domain: editDomain.value,
      importance: editImportance.value,
    })
    editingId.value = null
    showToast("记忆已更新")
    await fetchMemories()
  } catch (e: any) {
    showToast(e?.response?.data?.detail || "更新失败")
  }
}

function _cancelEdit() {
  editingId.value = null
}

onMounted(() => {
  Promise.all([fetchMemories(), fetchStats()])
})

const _domainCounts = computed(() => {
  const map: Record<string, number> = { total: total.value }
  for (const d of domains.slice(1))
    map[d] = memoryStats.value.by_domain?.[d] || 0
  return map
})
</script>

<template>
  <div class="h-full flex flex-col">
    <Transition name="toast">
      <div v-if="toast" class="fixed top-6 left-1/2 -translate-x-1/2 z-50 px-5 py-2.5 rounded-xl text-sm font-medium bg-green-500/15 border border-green-500/25 text-green-400 backdrop-blur-xl shadow-xl">
        {{ toast }}
      </div>
    </Transition>

    <!-- Header -->
    <div class="flex items-center justify-between px-8 pt-8 pb-6 border-b border-white/5">
      <div>
        <h1 class="text-2xl font-bold text-white flex items-center gap-3">
          <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-teal-500/20 to-emerald-500/10 border border-teal-500/20 flex items-center justify-center">
            <Brain class="w-5 h-5 text-teal-400" />
          </div>
          长期记忆
        </h1>
        <p class="text-sm text-gray-500 mt-1.5 ml-[3.25rem]">让 AI 记住你的偏好和重要信息，跨对话共享</p>
      </div>
      <div class="flex items-center gap-3 text-xs text-gray-600">
        <span class="flex items-center gap-1"><Brain class="w-3 h-3" /> {{ memoryStats.total_memories }} 条记忆</span>
        <span class="flex items-center gap-1"><Clock class="w-3 h-3" /> {{ memoryStats.total_accesses }} 次访问</span>
      </div>
    </div>

    <div class="flex-1 flex overflow-hidden">
      <!-- Left sidebar -->
      <div class="w-52 shrink-0 border-r border-white/5 p-4 space-y-1 overflow-y-auto">
        <p class="text-[11px] font-medium text-gray-500 uppercase tracking-wider px-2 mb-3">作用域</p>
        <button v-for="d in domains" :key="d || '__all'" @click="filterDomain = d; page = 1; fetchMemories()"
          :class="['w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-all duration-200 text-left', filterDomain === d ? 'bg-brand-500/10 text-brand-400 font-medium' : 'text-gray-400 hover:text-gray-200 hover:bg-white/[0.04]']">
          <component :is="domainIcons[d] || Layers" class="w-4 h-4 shrink-0" /> {{ domainLabels[d] || d }}
          <span class="ml-auto text-xs text-gray-600">{{ domainCounts[d] || 0 }}</span>
        </button>
        <div class="mt-6 pt-4 border-t border-white/5">
          <p class="text-[11px] font-medium text-gray-500 uppercase tracking-wider px-2 mb-3">快速添加</p>
          <div class="space-y-2 px-2">
            <input v-model="newKey" placeholder="摘要" class="w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-teal-500/40 transition-colors" />
            <textarea v-model="newValue" rows="2" placeholder="内容..." class="w-full rounded-lg border border-white/10 bg-white/[0.02] px-3 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-teal-500/40 transition-colors resize-none"></textarea>
            <div class="flex gap-1.5">
              <select v-model="newDomain" class="flex-1 rounded-lg border border-white/10 bg-white/[0.02] px-2 py-1.5 text-xs text-white focus:outline-none focus:border-teal-500/40 transition-colors">
                <option value="general">通用</option>
                <option value="personal">个人</option>
                <option value="project">项目</option>
                <option value="code">代码</option>
              </select>
              <button @click="addMemory" :disabled="!newKey || !newValue" class="p-1.5 rounded-lg bg-teal-500/15 hover:bg-teal-500/25 text-teal-400 disabled:opacity-30 transition-colors"><Plus class="w-4 h-4" /></button>
            </div>
          </div>
        </div>
      </div>

      <!-- Main content -->
      <div class="flex-1 overflow-y-auto p-6">
        <!-- Search -->
        <div class="relative max-w-lg mb-6">
          <Search class="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-600" />
          <input v-model="searchQuery" @keyup.enter="doSearch" placeholder="语义搜索记忆..." class="w-full bg-white/[0.03] border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-brand-500/40 focus:bg-white/[0.05] transition-all" />
        </div>

        <!-- Search results -->
        <div v-if="searchResults.length" class="mb-6 space-y-2">
          <p class="text-[11px] text-gray-500 mb-3">搜索结果 ({{ searchResults.length }} 条)</p>
          <div v-for="r in searchResults" :key="r.id" class="p-3 rounded-xl bg-white/[0.02] border border-white/5">
            <div class="flex items-center gap-2 mb-1">
              <span class="text-[10px] px-1.5 py-0.5 rounded bg-teal-500/10 text-teal-400">{{ r.domain }}</span>
              <span class="text-[10px] text-green-500">{{ (r.similarity * 100).toFixed(0) }}% 匹配</span>
            </div>
            <div class="text-xs font-medium text-white">{{ r.key }}</div>
            <div class="text-[10px] text-gray-500 mt-0.5 line-clamp-2">{{ r.value }}</div>
          </div>
        </div>

        <!-- Loading -->
        <div v-if="loading" class="flex items-center justify-center py-24">
          <Loader2 class="w-8 h-8 animate-spin text-teal-400" />
        </div>

        <!-- Empty -->
        <div v-else-if="!memories.length" class="flex flex-col items-center justify-center py-24 text-gray-600">
          <Brain class="w-12 h-12 mb-4 opacity-30" />
          <p class="text-sm">还没有记忆</p>
          <p class="text-xs mt-1 opacity-70">在左侧快速添加第一条记忆</p>
        </div>

        <!-- Memory list -->
        <div v-else class="space-y-2">
          <div v-for="m in memories" :key="m.id"
            class="flex items-start gap-3 p-3.5 rounded-xl bg-white/[0.02] border border-white/5 hover:border-white/10 transition-all duration-200 group">
            <!-- Edit mode -->
            <template v-if="editingId === m.id">
              <div class="flex-1 space-y-2">
                <input v-model="editKey" placeholder="摘要" class="w-full rounded-lg border border-teal-500/30 bg-white/[0.03] px-3 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-teal-500/60 transition-all" />
                <textarea v-model="editValue" rows="2" placeholder="内容" class="w-full rounded-lg border border-teal-500/30 bg-white/[0.03] px-3 py-1.5 text-xs text-white placeholder-gray-600 focus:outline-none focus:border-teal-500/60 transition-all resize-none"></textarea>
                <div class="flex gap-1.5">
                  <select v-model="editDomain" class="rounded-lg border border-white/10 bg-white/[0.02] px-2 py-1 text-xs text-white"><option value="general">通用</option><option value="personal">个人</option><option value="project">项目</option><option value="code">代码</option></select>
                  <button @click="saveEdit" class="flex items-center gap-1 px-3 py-1 rounded-lg bg-teal-500/20 text-teal-400 text-xs font-medium hover:bg-teal-500/30 transition-colors"><Check class="w-3 h-3" />保存</button>
                  <button @click="cancelEdit" class="px-3 py-1 rounded-lg text-xs text-gray-500 hover:text-white transition-colors">取消</button>
                </div>
              </div>
            </template>

            <!-- View mode -->
            <template v-else>
              <div :class="['w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5',
                m.domain === 'code' ? 'bg-blue-500/10' : m.domain === 'project' ? 'bg-purple-500/10' : m.domain === 'personal' ? 'bg-amber-500/10' : 'bg-teal-500/10']">
                <component :is="domainIcons[m.domain] || Layers" :class="['w-4 h-4',
                  m.domain === 'code' ? 'text-blue-400' : m.domain === 'project' ? 'text-purple-400' : m.domain === 'personal' ? 'text-amber-400' : 'text-teal-400']" />
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-0.5">
                  <span class="text-xs font-medium text-white truncate">{{ m.key }}</span>
                  <span class="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.03] border border-white/5 text-gray-500 shrink-0">{{ domainLabels[m.domain] || m.domain }}</span>
                  <span class="text-[10px] text-gray-600 shrink-0">重要性 {{ (m.importance || 0).toFixed(1) }} · {{ m.access_count || 0 }} 次</span>
                </div>
                <p class="text-xs text-gray-500 line-clamp-2 leading-relaxed">{{ m.value }}</p>
              </div>
              <div class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-all duration-200 shrink-0">
                <button @click="startEdit(m)" class="p-1.5 rounded-lg text-gray-600 hover:text-gray-400 hover:bg-white/5 transition-colors"><Edit3 class="w-3.5 h-3.5" /></button>
                <button @click="deleteMemory(m.id)" class="p-1.5 rounded-lg text-gray-600 hover:text-red-400 hover:bg-red-500/10 transition-colors"><Trash2 class="w-3.5 h-3.5" /></button>
              </div>
            </template>
          </div>
        </div>

        <!-- Pagination -->
        <div v-if="total > sizeVal" class="flex items-center justify-center gap-3 pt-6 mt-6 border-t border-white/5">
          <button :disabled="page <= 1" @click="page--; fetchMemories()" class="px-3 py-1.5 rounded-lg bg-white/[0.03] text-xs text-gray-400 hover:bg-white/[0.06] disabled:opacity-30 transition-colors">&laquo;</button>
          <span class="text-xs text-gray-600">{{ page }} / {{ Math.max(1, Math.ceil(total / sizeVal)) }}</span>
          <button :disabled="page >= Math.ceil(total / sizeVal)" @click="page++; fetchMemories()" class="px-3 py-1.5 rounded-lg bg-white/[0.03] text-xs text-gray-400 hover:bg-white/[0.06] disabled:opacity-30 transition-colors">&raquo;</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.toast-enter-active, .toast-leave-active { transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1); }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateY(-12px) translateX(-50%); }
</style>
