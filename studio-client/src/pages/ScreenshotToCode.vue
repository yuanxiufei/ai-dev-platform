<script setup lang="ts">
import { computed, ref } from "vue"
import {
  type ScreenshotCodeResult,
  screenshotToCode,
} from "@/api/screenshot-code"

// 截图相关
const screenshots = ref<string[]>([]) // base64 数组
const prompt = ref("")
const framework = ref("auto")

// 结果
const generating = ref(false)
const result = ref<ScreenshotCodeResult | null>(null)
const error = ref("")

// 文件输入 ref
const _fileInputRef = ref<HTMLInputElement | null>(null)

// 拖拽/粘贴
const isDragging = ref(false)

const frameworks = [
  { value: "auto", label: "自动检测" },
  { value: "vue3", label: "Vue 3 + TypeScript" },
  { value: "react", label: "React + TypeScript" },
  { value: "html", label: "HTML + Tailwind CSS" },
  { value: "miniapp", label: "微信小程序" },
  { value: "flutter", label: "Flutter" },
]

// 提取代码块
const codeBlocks = computed(() => {
  if (!result.value) return []
  const content = result.value.content
  const blocks: { language: string; code: string }[] = []
  const regex = /```(\w+)?\n([\s\S]*?)```/g
  let match
  while ((match = regex.exec(content)) !== null) {
    blocks.push({
      language: match[1] || "text",
      code: match[2].trim(),
    })
  }
  if (blocks.length === 0) {
    blocks.push({ language: "text", code: content })
  }
  return blocks
})

const _hasCode = computed(() => codeBlocks.value.length > 0)

// 文件处理
function _handleFileSelect(e: Event) {
  const input = e.target as HTMLInputElement
  if (!input.files) return
  processFiles(input.files)
  input.value = ""
}

function _handleDrop(e: DragEvent) {
  isDragging.value = false
  if (!e.dataTransfer?.files) return
  processFiles(e.dataTransfer.files)
}

function processFiles(files: FileList) {
  for (const file of Array.from(files)) {
    if (!file.type.startsWith("image/")) continue
    const reader = new FileReader()
    reader.onload = () => {
      const base64 = (reader.result as string).split(",")[1]
      // 去重
      if (!screenshots.value.includes(base64)) {
        screenshots.value.push(base64)
      }
    }
    reader.readAsDataURL(file)
  }
}

// 粘贴截图
function _handlePaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of Array.from(items)) {
    if (!item.type.startsWith("image/")) continue
    const blob = item.getAsFile()
    if (!blob) continue
    const reader = new FileReader()
    reader.onload = () => {
      const base64 = (reader.result as string).split(",")[1]
      if (!screenshots.value.includes(base64)) {
        screenshots.value.push(base64)
      }
    }
    reader.readAsDataURL(blob)
  }
}

function _removeScreenshot(index: number) {
  screenshots.value.splice(index, 1)
}

// 生成代码
async function _doGenerate() {
  if (screenshots.value.length === 0) return
  generating.value = true
  error.value = ""
  result.value = null

  let fullPrompt = prompt.value || "请将这张UI截图转换为前端代码"
  if (framework.value !== "auto") {
    fullPrompt += `，使用${frameworks.find((f) => f.value === framework.value)?.label || framework.value}框架`
  }

  try {
    result.value = (await screenshotToCode(screenshots.value, fullPrompt))
      .data as ScreenshotCodeResult
  } catch (e: any) {
    error.value = e?.response?.data?.detail || "生成失败，请稍后重试"
  } finally {
    generating.value = false
  }
}

// 复制代码
function _copyCode(text: string) {
  navigator.clipboard.writeText(text)
}

// 下载代码
function _downloadCode(language: string, code: string) {
  const extMap: Record<string, string> = {
    vue: ".vue",
    typescript: ".ts",
    tsx: ".tsx",
    javascript: ".js",
    jsx: ".jsx",
    html: ".html",
    css: ".css",
    dart: ".dart",
    python: ".py",
  }
  const ext = extMap[language] || ".txt"
  const blob = new Blob([code], { type: "text/plain" })
  const a = document.createElement("a")
  a.href = URL.createObjectURL(blob)
  a.download = `generated-${Date.now()}${ext}`
  a.click()
  URL.revokeObjectURL(a.href)
}
</script>

<template>
  <div class="p-6 max-w-7xl mx-auto" @paste="handlePaste">
    <header class="mb-6">
      <h1 class="text-2xl font-bold text-white flex items-center gap-2">
        <Code2 class="w-6 h-6 text-brand-400" />
        截图转代码
      </h1>
      <p class="text-sm text-gray-400 mt-1">
        上传 UI 截图或设计稿，AI 自动生成前端代码 &mdash; 支持 Vue / React / 小程序 / Flutter
      </p>
    </header>

    <div class="grid grid-cols-1 lg:grid-cols-5 gap-6">
      <!-- 左侧：上传 & 配置 -->
      <div class="lg:col-span-2 space-y-4">
        <!-- 上传区域 -->
        <div
          class="relative rounded-xl border-2 border-dashed transition-colors cursor-pointer"
          :class="[
            isDragging
              ? 'border-brand-500 bg-brand-500/5'
              : 'border-white/10 hover:border-brand-500/40 bg-surface-800/40',
            screenshots.length > 0 ? 'p-2' : 'p-8',
          ]"
          @dragover.prevent="isDragging = true"
          @dragleave.prevent="isDragging = false"
          @drop.prevent="handleDrop"
          @click="screenshots.length === 0 && fileInputRef?.click()"
        >
          <input
            ref="fileInputRef"
            type="file"
            accept="image/png,image/jpeg,image/webp,image/svg+xml"
            multiple
            class="hidden"
            @change="handleFileSelect"
          />

          <!-- 已上传截图预览 -->
          <div v-if="screenshots.length > 0" class="grid grid-cols-2 gap-2">
            <div
              v-for="(img, i) in screenshots"
              :key="i"
              class="relative group rounded-lg overflow-hidden bg-black/40 border border-white/5"
            >
              <img
                :src="'data:image/png;base64,' + img"
                class="w-full aspect-video object-contain"
              />
              <button
                @click.stop="removeScreenshot(i)"
                class="absolute top-1 right-1 p-1 rounded bg-black/60 hover:bg-red-500/80 text-white opacity-0 group-hover:opacity-100 transition"
              >
                <X class="w-3 h-3" />
              </button>
            </div>
            <!-- 继续添加 -->
            <div
              class="aspect-video rounded-lg border border-dashed border-white/10 flex items-center justify-center bg-surface-800/40 hover:border-brand-500/40 cursor-pointer transition"
              @click.stop="fileInputRef?.click()"
            >
              <Plus class="w-5 h-5 text-gray-500" />
            </div>
          </div>

          <!-- 空状态 -->
          <template v-else>
            <div class="flex flex-col items-center text-center">
              <div class="w-14 h-14 rounded-2xl bg-surface-800 flex items-center justify-center mb-3">
                <Upload class="w-7 h-7 text-gray-500" />
              </div>
              <p class="text-sm text-gray-300 mb-1">拖拽截图到此处</p>
              <p class="text-xs text-gray-500">
                或点击选择文件 · 支持 Ctrl+V 粘贴
              </p>
            </div>
          </template>
        </div>

        <!-- Prompt 输入 -->
        <div class="space-y-1.5">
          <label class="text-sm text-gray-300 font-medium">
            补充说明（可选）
          </label>
          <textarea
            v-model="prompt"
            rows="3"
            class="w-full bg-surface-800/60 border border-white/10 rounded-lg p-3 text-sm text-gray-200 focus:outline-none focus:border-brand-500 resize-none placeholder:text-gray-600"
            placeholder="如：将底部按钮改为蓝色、添加 loading 状态、响应式布局..."
          />
        </div>

        <!-- 目标框架选择 -->
        <div class="space-y-1.5">
          <label class="text-sm text-gray-300 font-medium">目标框架</label>
          <select
            v-model="framework"
            class="w-full bg-surface-800/60 border border-white/10 rounded-lg px-3 py-2.5 text-sm text-gray-200 focus:outline-none focus:border-brand-500"
          >
            <option v-for="f in frameworks" :key="f.value" :value="f.value">
              {{ f.label }}
            </option>
          </select>
        </div>

        <!-- 生成按钮 -->
        <button
          @click="doGenerate"
          :disabled="generating || screenshots.length === 0"
          class="w-full py-3 rounded-lg bg-brand-500 hover:bg-brand-600 text-white font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          <RefreshCw v-if="generating" class="w-4 h-4 animate-spin" />
          <Sparkles v-else class="w-4 h-4" />
          {{ generating ? 'AI 正在生成代码...' : '生成代码' }}
        </button>

        <p v-if="error" class="text-red-400 text-sm">{{ error }}</p>

        <!-- 清空 -->
        <button
          v-if="screenshots.length > 0 && !generating"
          @click="screenshots = []; result = null"
          class="w-full py-2 rounded-lg bg-surface-800/60 hover:bg-surface-700 text-sm text-gray-400 hover:text-gray-200 transition flex items-center justify-center gap-1.5"
        >
          <Trash2 class="w-3.5 h-3.5" /> 清空重新开始
        </button>
      </div>

      <!-- 右侧：结果区域 -->
      <div class="lg:col-span-3 space-y-4">
        <!-- 空状态 -->
        <div
          v-if="!result && !generating"
          class="flex flex-col items-center justify-center h-full py-20 text-gray-500"
        >
          <div class="w-20 h-20 rounded-2xl bg-surface-800 flex items-center justify-center mb-4">
            <Code2 class="w-10 h-10 text-gray-600" />
          </div>
          <p class="mb-1">上传截图后点击「生成代码」</p>
          <p class="text-sm text-gray-600">
            支持 .png · .jpg · .webp 格式
          </p>
        </div>

        <!-- 生成中 -->
        <div
          v-if="generating"
          class="flex flex-col items-center justify-center py-20"
        >
          <RefreshCw class="w-8 h-8 text-brand-400 animate-spin mb-4" />
          <p class="text-sm text-gray-400">
            AI 正在分析截图并生成代码...
          </p>
        </div>

        <!-- 结果 -->
        <template v-if="result && hasCode">
          <!-- 元信息 -->
          <div class="flex items-center gap-4 px-1 text-xs text-gray-500">
            <span>模型: {{ result.model_used || '-' }}</span>
            <span>引擎: {{ result.provider || '-' }}</span>
            <span>耗时: {{ result.latency_ms }}ms</span>
            <span v-if="result.is_fallback" class="text-orange-400">
              (回退)
            </span>
          </div>

          <!-- 代码块 -->
          <div
            v-for="(block, i) in codeBlocks"
            :key="i"
            class="bg-surface-800/60 rounded-xl border border-white/10 overflow-hidden"
          >
            <div class="flex items-center justify-between px-4 py-2.5 border-b border-white/5 bg-surface-800/80">
              <span class="text-xs font-mono text-brand-400 uppercase">
                {{ block.language }}
              </span>
              <div class="flex items-center gap-1">
                <button
                  @click="copyCode(block.code)"
                  class="flex items-center gap-1 px-2.5 py-1 rounded-lg hover:bg-white/10 text-xs text-gray-400 hover:text-gray-200 transition"
                >
                  <Copy class="w-3 h-3" /> 复制
                </button>
                <button
                  @click="downloadCode(block.language, block.code)"
                  class="flex items-center gap-1 px-2.5 py-1 rounded-lg hover:bg-white/10 text-xs text-gray-400 hover:text-gray-200 transition"
                >
                  <Download class="w-3 h-3" /> 下载
                </button>
              </div>
            </div>
            <pre
              class="p-4 text-sm text-gray-300 overflow-auto max-h-[600px] font-mono leading-relaxed"
            ><code>{{ block.code }}</code></pre>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
