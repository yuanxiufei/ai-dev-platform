<script setup lang="ts">
import { ref, computed, onMounted } from "vue"
import { RefreshCw, Play, Clock, CheckCircle2, XCircle, AlertTriangle, Terminal, BarChart3, ChevronRight, Trash2, FileJson } from "lucide-vue-next"
import { type TrajectoryFile, type TrajectoryReplay, trajectoryApi } from "@/api/model-features"

const loading = ref(false); const replaying = ref(false); const error = ref("")
const files = ref<TrajectoryFile[]>([]); const replay = ref<TrajectoryReplay | null>(null)
const selectedFile = ref(""); const agentFilter = ref("")

async function fetchList() {
  loading.value = true; error.value = ""
  try { const r = await trajectoryApi.list(agentFilter.value || undefined); files.value = r.data.trajectories || [] }
  catch (e: any) { error.value = e?.response?.data?.detail || e?.message || "加载失败" }
  finally { loading.value = false }
}

async function doReplay(filename: string) {
  replaying.value = true; replay.value = null; selectedFile.value = filename; error.value = ""
  const agentId = filename.split("__")[0] || filename.replace(/\.(json|jsonl)$/, "")
  const sid = filename.match(/__(.+)\.(json|jsonl)$/)?.[1]
  try { replay.value = (await trajectoryApi.replay(agentId, sid || undefined)).data }
  catch (e: any) { error.value = e?.response?.data?.detail || e?.message || "回放失败" }
  finally { replaying.value = false }
}

async function doDelete(filename: string) {
  if (!confirm(`确定删除轨迹 "${filename}"？`)) return
  const agentId = filename.split("__")[0] || filename.replace(/\.(json|jsonl)$/, "")
  const sid = filename.match(/__(.+)\.(json|jsonl)$/)?.[1]
  try { await trajectoryApi.delete(agentId, sid || undefined); files.value = files.value.filter(f => f.filename !== filename); selectedFile.value = ""; replay.value = null }
  catch (e: any) { error.value = e?.response?.data?.detail || e?.message || "删除失败" }
}

function stepIcon(type: string): { icon: any; color: string; label: string } {
  const t = type.toLowerCase()
  if (t.includes("tool") || t.includes("execut")) return { icon: Terminal, color: "#f59e0b", label: "工具" }
  if (t.includes("think") || t.includes("reason")) return { icon: BarChart3, color: "#8b5cf6", label: "推理" }
  if (t.includes("error") || t.includes("fail")) return { icon: XCircle, color: "#ef4444", label: "错误" }
  if (t.includes("plan") || t.includes("decide")) return { icon: BarChart3, color: "#3b82f6", label: "计划" }
  if (t.includes("complete") || t.includes("done") || t.includes("finish")) return { icon: CheckCircle2, color: "#10b981", label: "完成" }
  return { icon: ChevronRight, color: "#6b7280", label: type || "步骤" }
}

const successRate = computed(() => {
  if (!replay.value?.steps?.length) return 0
  return Math.round((replay.value.steps.filter(s => !s.error).length / replay.value.steps.length) * 100)
})
const totalTime = computed(() => {
  const ms = replay.value?.summary?.total_time_ms; if (!ms) return "—"
  if (ms < 1000) return ms + "ms"; if (ms < 60000) return (ms / 1000).toFixed(1) + "s"
  return (ms / 60000).toFixed(1) + "min"
})
function formatTime(mtime: number) {
  if (!mtime) return "—"
  return new Date(mtime * 1000).toLocaleString("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
}
function formatBytes(b: number): string {
  if (b < 1024) return b + "B"; if (b < 1048576) return (b / 1024).toFixed(1) + "KB"
  return (b / 1048576).toFixed(1) + "MB"
}
function truncate(s: string, max: number): string { return s.length > max ? s.slice(0, max) + "…" : s }

onMounted(fetchList)
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto space-y-6">
    <!-- Header -->
    <header class="flex items-center justify-between flex-wrap gap-3">
      <div>
        <h1 class="text-3xl font-bold text-white">Agent 轨迹回放</h1>
        <p class="text-gray-400 mt-1 text-sm">查看 Agent 历史执行步骤 · 时间线回放</p>
      </div>
      <button @click="fetchList" :disabled="loading" class="p-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-gray-300 transition disabled:opacity-50" title="刷新">
        <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': loading }" />
      </button>
    </header>

    <!-- Error -->
    <div v-if="error" class="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-center gap-2">
      <XCircle class="w-4 h-4 shrink-0" />{{ error }}
      <button @click="error = ''" class="ml-auto text-red-300 hover:text-red-200">&times;</button>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Left: File list -->
      <aside class="lg:col-span-1 space-y-3">
        <div class="bg-gray-900/50 rounded-xl p-4 border border-gray-800/50">
          <h3 class="text-sm font-semibold text-white mb-3">轨迹文件</h3>
          <input v-model="agentFilter" @keyup.enter="fetchList" placeholder="筛选 Agent ID…" class="w-full bg-gray-800 border border-gray-700/50 rounded-lg px-3 py-1.5 text-xs text-gray-200 outline-none mb-3 focus:border-brand-500/50" />

          <!-- Loading -->
          <div v-if="loading" class="text-center py-8 text-gray-500 text-sm">加载中…</div>

          <!-- Empty -->
          <div v-else-if="!files.length" class="text-center py-12 text-gray-500">
            <FileJson class="w-10 h-10 mx-auto mb-2 text-gray-600" />
            <p class="font-medium">暂无轨迹数据</p>
            <p class="text-xs mt-1">Agent 运行后会自动生成轨迹文件</p>
          </div>

          <!-- List -->
          <div v-else class="space-y-1.5 max-h-[60vh] overflow-y-auto pr-1">
            <div
              v-for="f in files"
              :key="f.filename"
              @click="doReplay(f.filename)"
              class="flex items-center gap-2 p-2.5 rounded-lg cursor-pointer transition text-sm border"
              :class="selectedFile === f.filename ? 'bg-brand-500/10 border-brand-500/30 text-white' : 'bg-gray-800/50 border-transparent hover:bg-gray-800 text-gray-300 hover:text-gray-200'"
            >
              <Play class="w-3.5 h-3.5 shrink-0" :class="selectedFile === f.filename ? 'text-brand-400' : 'text-gray-500'" />
              <div class="flex-1 min-w-0">
                <div class="text-xs font-mono truncate" :title="f.filename">{{ f.filename }}</div>
                <div class="text-[10px] text-gray-500 mt-0.5">{{ formatTime(f.modified_at) }} · {{ formatBytes(f.size_bytes) }}</div>
              </div>
              <button @click.stop="doDelete(f.filename)" class="p-0.5 text-gray-600 hover:text-red-400 transition shrink-0" title="删除">
                <Trash2 class="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
      </aside>

      <!-- Right: Replay -->
      <main class="lg:col-span-2 space-y-4">
        <!-- No selection -->
        <div v-if="!replay && !replaying" class="bg-gray-900/50 rounded-2xl p-6 border border-gray-800/50 text-center py-24">
          <Play class="w-12 h-12 mx-auto mb-3 text-gray-600" />
          <p class="text-gray-400 font-medium">选择左侧的轨迹文件进行回放</p>
          <p class="text-sm text-gray-500 mt-1">查看 Agent 每一步的执行过程和时间线</p>
        </div>

        <!-- Replaying spinner -->
        <div v-if="replaying" class="bg-gray-900/50 rounded-2xl p-6 border border-gray-800/50 text-center py-20">
          <div class="w-8 h-8 border-2 border-brand-400 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
          <p class="text-gray-400 text-sm">加载轨迹回放…</p>
        </div>

        <!-- Replay result -->
        <div v-if="replay" class="space-y-4">
          <!-- Summary cards -->
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div class="p-3 rounded-xl bg-gray-900/50 border border-gray-800/50 text-center">
              <span class="block text-xl font-bold" :class="replay.summary.success ? 'text-green-400' : 'text-red-400'">{{ replay.summary.success ? '✓' : '✗' }}</span>
              <span class="text-xs text-gray-500">{{ replay.summary.success ? '成功' : '失败' }}</span>
            </div>
            <div class="p-3 rounded-xl bg-gray-900/50 border border-gray-800/50 text-center">
              <span class="block text-xl font-bold text-brand-400">{{ replay.summary.total_steps }}</span>
              <span class="text-xs text-gray-500">总步骤</span>
            </div>
            <div class="p-3 rounded-xl bg-gray-900/50 border border-gray-800/50 text-center">
              <span class="block text-xl font-bold text-amber-400">{{ totalTime }}</span>
              <span class="text-xs text-gray-500">总耗时</span>
            </div>
            <div class="p-3 rounded-xl bg-gray-900/50 border border-gray-800/50 text-center">
              <span class="block text-xl font-bold" :class="successRate >= 80 ? 'text-green-400' : successRate >= 50 ? 'text-amber-400' : 'text-red-400'">{{ successRate }}%</span>
              <span class="text-xs text-gray-500">成功率</span>
            </div>
          </div>

          <!-- Meta info -->
          <div class="bg-gray-900/50 rounded-xl p-4 border border-gray-800/50 flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-400">
            <span>Agent: <span class="text-gray-300 font-mono">{{ replay.summary.agent_id }}</span></span>
            <span v-if="replay.summary.session_id">Session: <span class="text-gray-300 font-mono">{{ replay.summary.session_id }}</span></span>
            <span v-if="replay.summary.started_at">开始: <span class="text-gray-300">{{ new Date(replay.summary.started_at).toLocaleString("zh-CN") }}</span></span>
            <span class="text-gray-500 font-mono text-[10px]">{{ replay._filename }}</span>
          </div>

          <!-- Error banner -->
          <div v-if="replay.summary.error" class="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-sm flex items-start gap-2">
            <AlertTriangle class="w-4 h-4 shrink-0 mt-0.5" />
            <span>{{ replay.summary.error }}</span>
          </div>

          <!-- Final answer -->
          <div v-if="replay.summary.final_answer" class="bg-gray-900/50 rounded-xl p-4 border border-gray-800/50">
            <h3 class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">最终回答</h3>
            <div class="text-sm text-gray-200 whitespace-pre-wrap leading-relaxed">{{ replay.summary.final_answer }}</div>
          </div>

          <!-- Steps timeline -->
          <div v-if="replay.steps?.length" class="bg-gray-900/50 rounded-xl p-5 border border-gray-800/50">
            <h3 class="text-sm font-semibold text-white mb-4">执行时间线 ({{ replay.steps.length }} 步)</h3>
            <div class="relative pl-8 space-y-0">
              <!-- Timeline line -->
              <div class="absolute left-[13px] top-2 bottom-2 w-0.5 bg-gray-700/50" />

              <div
                v-for="(s, i) in replay.steps"
                :key="i"
                class="relative pb-5 last:pb-0"
              >
                <!-- Dot -->
                <div
                  class="absolute left-[-21px] top-1 w-3 h-3 rounded-full border-2 z-10"
                  :style="{ background: s.error ? '#ef444420' : stepIcon(s.type).color + '20', borderColor: stepIcon(s.type).color }"
                />
                <!-- Card -->
                <div
                  class="rounded-xl p-3.5 border transition"
                  :class="s.error ? 'bg-red-500/5 border-red-500/20' : 'bg-gray-800/30 border-gray-800/50 hover:border-gray-700/50'"
                >
                  <div class="flex items-center gap-2 mb-1.5">
                    <component :is="stepIcon(s.type).icon" class="w-3.5 h-3.5" :style="{ color: stepIcon(s.type).color }" />
                    <span class="text-xs font-semibold text-gray-300">Step {{ s.step }}</span>
                    <span class="text-[10px] px-1.5 py-0.5 rounded-md font-medium" :style="{ background: stepIcon(s.type).color + '15', color: stepIcon(s.type).color }">{{ stepIcon(s.type).label }}</span>
                    <span v-if="s.elapsed_ms" class="ml-auto text-[10px] text-gray-500 flex items-center gap-1"><Clock class="w-3 h-3" />{{ s.elapsed_ms }}ms</span>
                  </div>
                  <div v-if="s.action" class="text-xs text-gray-400 mb-1 font-mono">{{ s.action }}</div>
                  <div v-if="s.error" class="text-xs text-red-400 bg-red-500/5 rounded-lg p-2 mt-1 whitespace-pre-wrap">{{ s.error }}</div>
                  <div v-else-if="s.output" class="text-xs text-gray-400 bg-gray-800/50 rounded-lg p-2 mt-1 whitespace-pre-wrap max-h-32 overflow-y-auto">{{ truncate(s.output, 400) }}</div>
                </div>
              </div>
            </div>
          </div>

          <!-- No steps -->
          <div v-else class="bg-gray-900/50 rounded-xl p-6 border border-gray-800/50 text-center py-12">
            <p class="text-gray-500 text-sm">该轨迹没有执行步骤数据</p>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>
