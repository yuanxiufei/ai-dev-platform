<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import {
  listKnowledgeBases,
  createKnowledgeBase,
  deleteKnowledgeBase,
  uploadDocument,
  type KnowledgeBase,
  type CreateKBRequest,
} from '@/api/rag'
import { BookOpen, Plus, Trash2, Upload, Link, FileText, Loader2, X } from 'lucide-vue-next'

const kbs = ref<KnowledgeBase[]>([])
const loading = ref(true)
const error = ref('')

// 创建表单
const showCreateForm = ref(false)
const newName = ref('')
const newDesc = ref('')
const newChunkSize = ref(512)
const newChunkOverlap = ref(100)
const newChunkStrategy = ref('recursive')
const creating = ref(false)

// 上传面板
const activeKb = ref<string | null>(null)
const uploadType = ref<'file' | 'text' | 'url'>('file')
const uploadFile = ref<File | null>(null)
const uploadText = ref('')
const uploadTitle = ref('')
const uploadUrl = ref('')
const uploading = ref(false)

onMounted(() => {
  refresh()
})

const refresh = async () => {
  loading.value = true
  try {
    const res = await listKnowledgeBases()
    kbs.value = res.data.data ?? []
  } catch (e: unknown) {
    error.value = (e as Error).message || '加载失败'
  } finally {
    loading.value = false
  }
}

const handleCreate = async () => {
  if (!newName.value.trim()) return
  creating.value = true
  try {
    const data: CreateKBRequest = {
      name: newName.value,
      description: newDesc.value,
      chunk_size: newChunkSize.value,
      chunk_overlap: newChunkOverlap.value,
      chunk_strategy: newChunkStrategy.value,
    }
    await createKnowledgeBase(data)
    showCreateForm.value = false
    newName.value = ''
    newDesc.value = ''
    await refresh()
  } catch (e: unknown) {
    error.value = (e as Error).message || '创建失败'
  } finally {
    creating.value = false
  }
}

const handleDelete = async (kbId: string) => {
  if (!confirm('确定删除此知识库？所有文档和索引将被永久删除。')) return
  try {
    await deleteKnowledgeBase(kbId)
    await refresh()
  } catch (e: unknown) {
    error.value = (e as Error).message || '删除失败'
  }
}

const handleUpload = async () => {
  if (!activeKb.value || uploading.value) return
  uploading.value = true
  try {
    if (uploadType.value === 'file' && uploadFile.value) {
      await uploadDocument(activeKb.value, {
        file: uploadFile.value,
        title: uploadTitle.value || uploadFile.value.name,
      })
    } else if (uploadType.value === 'text' && uploadText.value.trim()) {
      await uploadDocument(activeKb.value, {
        text: uploadText.value,
        title: uploadTitle.value || '文本片段',
      })
    } else if (uploadType.value === 'url' && uploadUrl.value.trim()) {
      await uploadDocument(activeKb.value, {
        url: uploadUrl.value,
        title: uploadTitle.value || undefined,
      })
    }
    uploadFile.value = null
    uploadText.value = ''
    uploadTitle.value = ''
    uploadUrl.value = ''
    activeKb.value = null
    await refresh()
  } catch (e: unknown) {
    error.value = (e as Error).message || '上传失败'
  } finally {
    uploading.value = false
  }
}

const strategies = [
  { value: 'recursive', label: '递归分割（通用）' },
  { value: 'markdown', label: 'Markdown 感知' },
  { value: 'code', label: '代码感知' },
  { value: 'fixed', label: '固定长度' },
]
</script>

<template>
  <div class="space-y-6">
    <!-- 页头 -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">知识库管理</h1>
        <p class="text-sm text-gray-500 mt-1">管理 RAG 知识库、上传文档、配置检索策略</p>
      </div>
      <button
        class="flex items-center gap-2 rounded-lg bg-brand-500 hover:bg-brand-600 px-4 py-2.5 text-sm font-medium transition-colors"
        @click="showCreateForm = !showCreateForm"
      >
        <Plus class="w-4 h-4" />
        创建知识库
      </button>
    </div>

    <!-- 错误提示 -->
    <div
      v-if="error"
      class="rounded-lg bg-red-500/10 border border-red-500/20 px-4 py-3 text-sm text-red-400 flex items-center justify-between"
    >
      {{ error }}
      <button class="hover:text-red-300" @click="error = ''"><X class="w-4 h-4" /></button>
    </div>

    <!-- 创建表单 -->
    <div v-if="showCreateForm" class="rounded-xl border border-white/10 bg-surface-800 p-6 space-y-4">
      <h3 class="text-sm font-semibold text-gray-200">新建知识库</h3>
      <div class="grid gap-4 grid-cols-1 md:grid-cols-2">
        <div>
          <label class="block text-xs font-medium text-gray-400 mb-1">名称 *</label>
          <input
            v-model="newName"
            class="w-full rounded-lg border border-white/10 bg-surface-900 px-3 py-2 text-sm placeholder-gray-600 focus:border-brand-500/50 focus:outline-none"
            placeholder="例如：技术文档"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-400 mb-1">分块策略</label>
          <select
            v-model="newChunkStrategy"
            class="w-full rounded-lg border border-white/10 bg-surface-900 px-3 py-2 text-sm focus:border-brand-500/50 focus:outline-none"
          >
            <option v-for="s in strategies" :key="s.value" :value="s.value">{{ s.label }}</option>
          </select>
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-400 mb-1">分块大小</label>
          <input
            v-model.number="newChunkSize"
            type="number"
            class="w-full rounded-lg border border-white/10 bg-surface-900 px-3 py-2 text-sm focus:border-brand-500/50 focus:outline-none"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-400 mb-1">重叠长度</label>
          <input
            v-model.number="newChunkOverlap"
            type="number"
            class="w-full rounded-lg border border-white/10 bg-surface-900 px-3 py-2 text-sm focus:border-brand-500/50 focus:outline-none"
          />
        </div>
      </div>
      <div>
        <label class="block text-xs font-medium text-gray-400 mb-1">描述</label>
        <textarea
          v-model="newDesc"
          rows="2"
          class="w-full rounded-lg border border-white/10 bg-surface-900 px-3 py-2 text-sm placeholder-gray-600 focus:border-brand-500/50 focus:outline-none resize-none"
          placeholder="知识库用途说明..."
        />
      </div>
      <div class="flex gap-3">
        <button
          :disabled="creating || !newName.trim()"
          class="rounded-lg bg-brand-500 hover:bg-brand-600 disabled:opacity-50 px-4 py-2 text-sm font-medium transition-colors"
          @click="handleCreate"
        >
          <Loader2 v-if="creating" class="w-4 h-4 animate-spin inline mr-1" />
          创建
        </button>
        <button
          class="rounded-lg text-gray-500 hover:text-gray-300 px-4 py-2 text-sm transition-colors"
          @click="showCreateForm = false"
        >
          取消
        </button>
      </div>
    </div>

    <!-- 加载 -->
    <div v-if="loading" class="py-20 text-center text-gray-500">
      <Loader2 class="w-6 h-6 animate-spin mx-auto mb-2 text-brand-400" />
      加载中...
    </div>

    <!-- 空状态 -->
    <div v-else-if="!kbs.length" class="py-20 text-center">
      <BookOpen class="w-10 h-10 text-gray-600 mx-auto mb-3" />
      <p class="text-gray-400 text-sm">暂无知识库</p>
      <p class="text-gray-600 text-xs mt-1">点击上方"创建知识库"按钮开始</p>
    </div>

    <!-- 知识库列表 -->
    <div v-else class="space-y-3">
      <div
        v-for="kb in kbs"
        :key="kb.kb_id"
        class="rounded-xl border border-white/10 bg-surface-800 hover:border-white/15 transition-colors"
      >
        <div class="p-5">
          <div class="flex items-start justify-between">
            <div class="flex items-start gap-3">
              <div class="w-9 h-9 rounded-lg bg-brand-500/10 flex items-center justify-center shrink-0">
                <BookOpen class="w-4 h-4 text-brand-400" />
              </div>
              <div>
                <h3 class="text-sm font-semibold text-gray-200">{{ kb.name }}</h3>
                <p class="text-xs text-gray-500 mt-0.5">{{ kb.description || '暂无描述' }}</p>
                <div class="flex items-center gap-4 mt-2 text-xs text-gray-600">
                  <span>{{ kb.stats?.documents || 0 }} 文档</span>
                  <span>{{ kb.stats?.chunks || 0 }} 片段</span>
                  <span v-if="kb.created_at">创建于 {{ kb.created_at }}</span>
                </div>
              </div>
            </div>
            <div class="flex items-center gap-2">
              <button
                class="rounded-lg p-2 text-gray-500 hover:text-brand-400 hover:bg-brand-500/10 transition-colors"
                title="上传文档"
                @click="activeKb = kb.kb_id"
              >
                <Upload class="w-4 h-4" />
              </button>
              <button
                class="rounded-lg p-2 text-gray-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                title="删除知识库"
                @click="handleDelete(kb.kb_id)"
              >
                <Trash2 class="w-4 h-4" />
              </button>
            </div>
          </div>

          <!-- 展开的上传面板 -->
          <div v-if="activeKb === kb.kb_id" class="mt-4 pt-4 border-t border-white/8">
            <!-- 上传类型切换 -->
            <div class="flex rounded-lg bg-surface-900 border border-white/10 p-1 mb-4">
              <button
                v-for="type in (['file', 'text', 'url'] as const)"
                :key="type"
                :class="[
                  'flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition-all flex items-center justify-center gap-1.5',
                  uploadType === type
                    ? 'bg-brand-500/20 text-brand-400'
                    : 'text-gray-500 hover:text-gray-300',
                ]"
                @click="uploadType = type"
              >
                <FileText v-if="type === 'file'" class="w-3 h-3" />
                <Upload v-else-if="type === 'url'" class="w-3 h-3" />
                <Link v-else class="w-3 h-3" />
                {{ type === 'file' ? '文件' : type === 'text' ? '文本' : 'URL' }}
              </button>
            </div>

            <div class="space-y-3">
              <!-- 文件上传 -->
              <div v-if="uploadType === 'file'">
                <input
                  type="file"
                  class="block w-full text-xs text-gray-400 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:bg-brand-500/20 file:text-brand-400 hover:file:bg-brand-500/30 transition-colors"
                  @change="(e: Event) => { const t = e.target as HTMLInputElement; uploadFile = t.files?.[0] ?? null }"
                />
              </div>

              <!-- 文本输入 -->
              <div v-if="uploadType === 'text'">
                <textarea
                  v-model="uploadText"
                  rows="4"
                  class="w-full rounded-lg border border-white/10 bg-surface-900 px-3 py-2 text-sm placeholder-gray-600 focus:border-brand-500/50 focus:outline-none resize-none"
                  placeholder="粘贴文本内容..."
                />
              </div>

              <!-- URL 输入 -->
              <div v-if="uploadType === 'url'">
                <input
                  v-model="uploadUrl"
                  type="url"
                  class="w-full rounded-lg border border-white/10 bg-surface-900 px-3 py-2 text-sm placeholder-gray-600 focus:border-brand-500/50 focus:outline-none"
                  placeholder="https://..."
                />
              </div>

              <!-- 标题 -->
              <div>
                <input
                  v-model="uploadTitle"
                  class="w-full rounded-lg border border-white/10 bg-surface-900 px-3 py-2 text-sm placeholder-gray-600 focus:border-brand-500/50 focus:outline-none"
                  placeholder="文档标题（可选）"
                />
              </div>

              <!-- 操作按钮 -->
              <div class="flex gap-3">
                <button
                  :disabled="uploading"
                  class="rounded-lg bg-brand-500 hover:bg-brand-600 disabled:opacity-50 px-4 py-2 text-sm font-medium transition-colors flex items-center gap-2"
                  @click="handleUpload"
                >
                  <Loader2 v-if="uploading" class="w-4 h-4 animate-spin" />
                  <Upload v-else class="w-4 h-4" />
                  上传
                </button>
                <button
                  class="rounded-lg text-gray-500 hover:text-gray-300 px-4 py-2 text-sm transition-colors"
                  @click="activeKb = null"
                >
                  取消
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
