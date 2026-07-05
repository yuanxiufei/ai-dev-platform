<script setup lang="ts">
/**
 * CommentsPanel — VSCode 代码评审评论面板
 *
 * 借鉴: VSCode src/vs/workbench/contrib/comments/browser/commentsView.ts
 *
 * 显示当前文件的评论线程 (thread)，支持回复、解决、接受建议。
 */
import { ref, computed, watch } from "vue"
import {
  MessageSquare, CheckCircle, X, Reply as ReplyIcon,
  Trash2, Pin, Filter, MessageSquarePlus, ChevronDown, ChevronRight
} from "lucide-vue-next"
import { useIDEStore } from "@/stores/useIDEStore"
import { useCommentsStore, type CodeComment } from "@/stores/useCommentsStore"

const ideStore = useIDEStore()
const store = useCommentsStore()

// ── 当前活动文件的路径
const currentFilePath = computed(() => ideStore.activeTab?.filePath ?? "")

// ── 当前文件的评论
const fileComments = computed(() =>
  currentFilePath.value ? store.forFile(currentFilePath.value) : []
)

const activeComments = computed(() =>
  fileComments.value.filter(c => c.state !== "resolved")
)

const resolvedComments = computed(() =>
  fileComments.value.filter(c => c.state === "resolved")
)

// ── 过滤
const filter = ref<"all" | "active" | "resolved">("all")
const displayedComments = computed(() => {
  if (filter.value === "active") return activeComments.value
  if (filter.value === "resolved") return resolvedComments.value
  return fileComments.value
})

// ── 展开/折叠状态
const expandedThreads = ref<Set<string>>(new Set())
function toggleThread(id: string) { expandedThreads.value.has(id) ? expandedThreads.value.delete(id) : expandedThreads.value.add(id) }
function isExpanded(id: string) { return expandedThreads.value.has(id) }

// ── 新建评论
const newComment = ref("")
const newCommentLine = ref<number | null>(null)
const showNewCommentInput = ref(false)

function startNewComment() {
  newComment.value = ""
  newCommentLine.value = ideStore.cursorPosition?.line ?? 1
  showNewCommentInput.value = true
}

function submitNewComment() {
  if (!newComment.value.trim() || !newCommentLine.value) return
  store.addComment(
    currentFilePath.value,
    newCommentLine.value,
    newComment.value.trim(),
    { name: "User" },
  )
  newComment.value = ""
  showNewCommentInput.value = false
}

// ── 回复
const replyText = ref("")
const replyingTo = ref<string | null>(null)

function startReply(id: string) {
  replyingTo.value = id
  replyText.value = ""
}

function submitReply() {
  if (!replyText.value.trim() || !replyingTo.value) return
  store.addReply(replyingTo.value, replyText.value.trim(), { name: "User" })
  replyText.value = ""
  replyingTo.value = null
}

// ── 时间格式化
function timeAgo(ts: number): string {
  const diff = Date.now() - ts
  if (diff < 60000) return "刚刚"
  if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
  return new Date(ts).toLocaleDateString()
}

// 当活动文件变化时自动展开所有线程
watch(currentFilePath, () => {
  expandedThreads.value = new Set(fileComments.value.map(c => c.id))
})

// ── 标签颜色
function labelColor(label?: string): string {
  const m: Record<string, string> = {
    review: "#4EC9B0", suggestion: "#75BEFF", question: "#E2B714", issue: "#F48771",
  }
  return m[label ?? ""] ?? "#CCA700"
}

function labelText(label?: string): string {
  const m: Record<string, string> = {
    review: "评审", suggestion: "建议", question: "提问", issue: "问题",
  }
  return m[label ?? ""] ?? "评论"
}
</script>

<template>
  <div class="h-full flex flex-col text-[13px]" style="background: var(--color-ide-surface)">
    <!-- Header -->
    <div class="flex items-center justify-between shrink-0 px-3"
      style="height: 38px; border-bottom: 1px solid var(--color-ide-border);">
      <span class="text-[12px] font-semibold uppercase tracking-wider text-[var(--color-ide-text)]">
        评审评论
        <span v-if="store.unresolvedCount" class="ml-1 px-1.5 py-0.5 text-[10px] rounded-full"
          style="background: var(--color-ide-accent); color: white;">
          {{ store.unresolvedCount }}
        </span>
      </span>
      <div class="flex items-center gap-0.5">
        <button
          class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]"
          :title="'过滤: ' + { all: '全部', active: '未解决', resolved: '已解决' }[filter]"
          @click="filter = filter === 'all' ? 'active' : filter === 'active' ? 'resolved' : 'all'"
        >
          <Filter :size="12" />
        </button>
        <button
          class="w-6 h-6 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface-hover)]"
          title="添加评论"
          @click="startNewComment"
        >
          <MessageSquarePlus :size="14" />
        </button>
      </div>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto">
      <!-- 无评论 -->
      <div v-if="displayedComments.length === 0" class="flex flex-col items-center justify-center py-12 text-[var(--color-ide-text-dim)]">
        <MessageSquare :size="28" class="mb-2 opacity-25" />
        <p class="text-[12px]">暂无评论</p>
        <p class="text-[10px] opacity-50 mt-1">选择代码行添加评论</p>
        <button
          class="mt-3 px-3 py-1 text-[11px] rounded-[3px] border border-[var(--color-ide-border)] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
          @click="startNewComment"
        >
          添加首条评论
        </button>
      </div>

      <!-- 评论列表 -->
      <div v-else class="py-1">
        <div v-for="comment in displayedComments" :key="comment.id"
          class="comment-thread border-b border-[var(--color-ide-border)]/40 last:border-b-0">
          <!-- 主评论 -->
          <div
            class="px-3 py-2 hover:bg-[var(--color-ide-surface-hover)]/50 transition-colors cursor-pointer"
            :class="{ 'opacity-60': comment.resolved }"
            @click="toggleThread(comment.id)"
          >
            <div class="flex items-start gap-2">
              <div class="flex items-center gap-1 shrink-0 mt-0.5">
                <ChevronRight :size="10" class="transition-transform"
                  :class="{ 'rotate-90': isExpanded(comment.id) }" />
              </div>
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1.5 mb-0.5">
                  <span v-if="comment.label" class="text-[9px] px-1 py-px rounded-[2px] font-medium"
                    :style="{ background: labelColor(comment.label) + '20', color: labelColor(comment.label) }">
                    {{ labelText(comment.label) }}
                  </span>
                  <span class="text-[11px] font-medium text-[var(--color-ide-text)]">
                    {{ comment.author.name }}
                  </span>
                  <span class="text-[10px] text-[var(--color-ide-text-dim)] opacity-60">
                    Ln {{ comment.line }}, {{ comment.endLine ? `L${comment.endLine}, ` : '' }}{{ timeAgo(comment.createdAt) }}
                  </span>
                </div>
                <p class="text-[12px] text-[var(--color-ide-text)] whitespace-pre-wrap line-clamp-2"
                  :class="{ 'line-clamp-none': isExpanded(comment.id) }">
                  {{ comment.body }}
                </p>
                <!-- 建议代码片段 -->
                <div v-if="comment.suggestion && isExpanded(comment.id)"
                  class="mt-1 p-2 rounded-[3px] font-mono text-[11px] border"
                  style="background: var(--color-ide-bg-secondary); border-color: var(--color-ide-border);">
                  <pre class="whitespace-pre-wrap">{{ comment.suggestion }}</pre>
                </div>
              </div>
              <!-- 操作按钮 -->
              <div class="flex items-center gap-0.5 shrink-0" @click.stop>
                <button
                  class="w-5 h-5 flex items-center justify-center rounded-[2px] hover:bg-[var(--color-ide-surface)] transition-colors"
                  :class="comment.resolved ? 'text-green-400' : 'text-[var(--color-ide-text-dim)]'"
                  :title="comment.resolved ? '重新打开' : '标记为已解决'"
                  @click="store.toggleResolve(comment.id)"
                >
                  <CheckCircle :size="13" />
                </button>
                <button
                  class="w-5 h-5 flex items-center justify-center rounded-[2px] text-[var(--color-ide-text-dim)] hover:bg-[var(--color-ide-surface)] transition-colors"
                  title="回复"
                  @click="startReply(comment.id)"
                >
                  <ReplyIcon :size="12" />
                </button>
                <button
                  class="w-5 h-5 flex items-center justify-center rounded-[2px] text-[var(--color-ide-text-dim)] hover:text-red-400 hover:bg-[var(--color-ide-surface)] transition-colors"
                  title="删除"
                  @click="store.deleteComment(comment.id)"
                >
                  <Trash2 :size="12" />
                </button>
              </div>
            </div>

            <!-- 建议操作 -->
            <div v-if="comment.suggestion && isExpanded(comment.id) && !comment.resolved"
              class="flex items-center gap-1 ml-5 mt-1.5" @click.stop>
              <button
                class="text-[10px] px-2 py-0.5 rounded-[3px] bg-green-500/15 text-green-400 hover:bg-green-500/25 transition-colors"
                @click.stop="store.acceptSuggestion(comment.id)"
              >接受建议</button>
              <button
                class="text-[10px] px-2 py-0.5 rounded-[3px] bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors"
                @click.stop="store.toggleResolve(comment.id)"
              >忽略</button>
            </div>
          </div>

          <!-- 回复列表 -->
          <div v-if="isExpanded(comment.id) && comment.replies.length > 0"
            class="border-t border-[var(--color-ide-border)]/20">
            <div v-for="reply in comment.replies" :key="reply.id"
              class="px-3 py-1.5 ml-5 flex items-start gap-2 text-[12px]"
              :class="reply.resolved ? 'opacity-50' : ''">
              <div class="w-4 shrink-0 flex justify-center mt-0.5 text-[var(--color-ide-text-dim)] opacity-40">
                ↩
              </div>
              <div class="flex-1 min-w-0">
                <span class="text-[11px] font-medium text-[var(--color-ide-text)]">{{ reply.author.name }}</span>
                <span class="text-[10px] text-[var(--color-ide-text-dim)] ml-1 opacity-50">{{ timeAgo(reply.createdAt) }}</span>
                <p class="text-[var(--color-ide-text)] mt-0.5">{{ reply.body }}</p>
              </div>
              <button
                class="w-4 h-4 flex items-center justify-center rounded-[2px] text-[var(--color-ide-text-dim)] hover:text-red-400 transition-colors"
                @click.stop="store.deleteComment(reply.id)"
              >
                <X :size="10" />
              </button>
            </div>
          </div>

          <!-- 回复输入框 -->
          <div v-if="isExpanded(comment.id) && replyingTo === comment.id"
            class="px-3 pb-2 ml-5 border-t border-[var(--color-ide-border)]/20 pt-2">
            <div class="flex gap-1.5">
              <textarea
                v-model="replyText"
                rows="2"
                class="flex-1 min-w-0 bg-[var(--color-editor-bg)] border border-[var(--color-ide-border)] rounded-[3px] px-2.5 py-1.5 text-[12px] text-[var(--color-ide-text)] placeholder:text-[var(--color-ide-text-dim)]/50 resize-none outline-none focus:border-[var(--color-ide-accent)]/50"
                placeholder="输入回复..."
                @keydown.ctrl.enter="submitReply"
              />
              <div class="flex flex-col gap-1">
                <button class="w-7 h-7 flex items-center justify-center rounded-[3px] bg-[var(--color-ide-accent)] text-white text-[11px] hover:brightness-110"
                  title="回复 (Ctrl+Enter)" @click="submitReply">
                  <ReplyIcon :size="12" />
                </button>
                <button class="w-7 h-7 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]"
                  title="取消" @click="replyingTo = null">
                  <X :size="12" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 底部新建评论 -->
    <div v-if="showNewCommentInput" class="shrink-0 border-t border-[var(--color-ide-border)] p-2">
      <div class="flex items-center gap-1 mb-1 text-[11px] text-[var(--color-ide-text-dim)]">
        <Pin :size="11" />
        <span>新评论 — Ln {{ newCommentLine }}</span>
      </div>
      <div class="flex gap-1.5">
        <textarea
          v-model="newComment"
          rows="2"
          class="flex-1 min-w-0 bg-[var(--color-editor-bg)] border border-[var(--color-ide-border)] rounded-[3px] px-2.5 py-1.5 text-[12px] text-[var(--color-ide-text)] placeholder:text-[var(--color-ide-text-dim)]/50 resize-none outline-none focus:border-[var(--color-ide-accent)]/50"
          placeholder="输入评论内容..."
          @keydown.ctrl.enter="submitNewComment"
        />
        <div class="flex flex-col gap-1">
          <button class="w-7 h-7 flex items-center justify-center rounded-[3px] bg-[var(--color-ide-accent)] text-white text-[11px] hover:brightness-110"
            title="提交 (Ctrl+Enter)" @click="submitNewComment">
            <MessageSquarePlus :size="13" />
          </button>
          <button class="w-7 h-7 flex items-center justify-center rounded-[3px] text-[var(--color-ide-text-dim)] hover:text-[var(--color-ide-text)]"
            title="取消" @click="showNewCommentInput = false">
            <X :size="12" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.line-clamp-none {
  display: block;
  -webkit-line-clamp: unset;
}
</style>
