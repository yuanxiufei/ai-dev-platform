<script setup lang="ts">
/**
 * OnboardingTips — VSCode Welcome / Getting Started Tips
 *
 * 对标 VSCode Welcome Page + Walkthrough:
 *   - 首次打开欢迎弹窗，引导用户了解核心功能
 *   - 从 localStorage 读取 seen 状态，已阅则直接显示提示气泡
 *   - 键盘快捷键提示卡片
 *   - 可重复启用（重置引导）
 */
import { ref, computed, onMounted } from "vue"
import { X, ChevronRight, ChevronLeft, Check, RotateCw, Zap, Keyboard, FolderOpen, MessageSquare, Terminal, Search } from "lucide-vue-next"

const STORAGE_KEY = "onboarding_seen_v1"
const visible = ref(false)
const currentStep = ref(0)

interface TipStep {
  icon: any
  title: string
  description: string
  shortcuts: string[]
}

const steps: TipStep[] = [
  {
    icon: FolderOpen,
    title: "打开项目文件夹",
    description: "选择一个包含代码的文件夹，即可开始使用 AI Studio 的全栈开发能力。点击左侧资源管理器或使用快捷键打开文件。",
    shortcuts: ["Ctrl+O → 打开文件", "Ctrl+K Ctrl+O → 打开文件夹"],
  },
  {
    icon: MessageSquare,
    title: "AI 智能编程助手",
    description: "使用内联对话 (Ctrl+I) 在光标处与 AI 对话，实时修改代码。或打开右侧 AI 对话面板进行自由问答。",
    shortcuts: ["Ctrl+I → 内联对话", "Ctrl+L → AI 面板"],
  },
  {
    icon: Terminal,
    title: "任务与终端",
    description: "配置任务 (Ctrl+Shift+B) 自动化构建、测试、部署流程。终端支持 Bash / Zsh / PowerShell / Cmd 多种 Shell。",
    shortcuts: ["Ctrl+Shift+B → 运行任务", "Ctrl+` → 切换终端"],
  },
  {
    icon: Search,
    title: "全局搜索与替换",
    description: "在项目中快速搜索文件、符号和代码。支持正则表达式、大小写匹配、全字匹配等多种搜索方式。",
    shortcuts: ["Ctrl+P → 快速打开文件", "Ctrl+Shift+F → 全局搜索"],
  },
  {
    icon: Keyboard,
    title: "键盘快捷键",
    description: "所有功能皆可通过键盘快捷键快速访问。可按 Ctrl+K Ctrl+S 打开快捷键管理页面自定义绑定。",
    shortcuts: ["Ctrl+Shift+P → 命令面板", "Ctrl+K Ctrl+S → 快捷键设置"],
  },
]

const totalSteps = computed(() => steps.length)
const isLastStep = computed(() => currentStep.value === totalSteps.value - 1)
const isFirstStep = computed(() => currentStep.value === 0)

// ── 显示/隐藏控制 ──
function showTips(): void {
  visible.value = true
  currentStep.value = 0
}

function hideTips(): void {
  visible.value = false
  try { localStorage.setItem(STORAGE_KEY, "true") } catch { /* ignore */ }
}

function nextStep(): void {
  if (isLastStep.value) {
    hideTips()
  } else {
    currentStep.value++
  }
}

function prevStep(): void {
  if (!isFirstStep.value) {
    currentStep.value--
  }
}

function resetOnboarding(): void {
  try { localStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }
  showTips()
}

// ── 初始状态 ──
onMounted(() => {
  try {
    const seen = localStorage.getItem(STORAGE_KEY)
    if (!seen) {
      visible.value = true
    }
  } catch { /* ignore */ }
})

// ── 暴露给外部使用 ──
defineExpose({ showTips, hideTips, resetOnboarding })
</script>

<template>
  <Teleport to="body">
    <!-- ═══ 遮罩层 ═══ -->
    <Transition name="onboard-fade">
      <div
        v-if="visible"
        class="fixed inset-0 z-[600] flex items-center justify-center"
        style="background: rgba(0,0,0,0.55);"
        @click.self="hideTips"
      >
        <!-- ═══ 卡片 ═══ -->
        <div
          class="w-[520px] max-h-[80vh] rounded-xl shadow-2xl overflow-hidden flex flex-col"
          :style="{
            background: 'var(--color-ide-surface)',
            border: '1px solid var(--color-ide-border)',
          }"
          @click.stop
        >
          <!-- Header -->
          <div class="flex items-center justify-between px-5 py-3 shrink-0"
            :style="{ borderBottom: '1px solid var(--color-ide-border)' }"
          >
            <div class="flex items-center gap-2">
              <Zap :size="16" style="color: var(--color-ide-accent);" />
              <span class="text-[14px] font-bold" style="color: var(--color-ide-text);">快速入门</span>
            </div>
            <button
              class="w-7 h-7 flex items-center justify-center rounded-[3px] hover:bg-[var(--color-ide-surface-hover)] transition-colors"
              style="color: var(--color-ide-text-dim);"
              @click="hideTips"
            >
              <X :size="14" />
            </button>
          </div>

          <!-- Steps indicator -->
          <div class="flex items-center gap-1.5 px-5 py-2.5 shrink-0">
            <button
              v-for="(step, idx) in steps"
              :key="idx"
              class="h-1 rounded-full transition-all duration-200 flex-1"
              :class="idx === currentStep ? '' : ''"
              :style="{
                background: idx === currentStep ? 'var(--color-ide-accent)' :
                  idx < currentStep ? 'var(--color-ide-success)' : 'var(--color-ide-border)',
                opacity: idx === currentStep ? 1 : 0.5,
              }"
              @click="currentStep = idx"
            />
          </div>

          <!-- Content -->
          <div class="flex-1 overflow-y-auto p-5 min-h-0">
            <div class="flex items-start gap-3 mb-4">
              <div class="shrink-0 w-10 h-10 rounded-lg flex items-center justify-center"
                :style="{ background: 'var(--color-ide-surface-active)' }"
              >
                <component :is="steps[currentStep].icon" :size="18" style="color: var(--color-ide-accent);" />
              </div>
              <div>
                <h3 class="text-[14px] font-bold mb-1" style="color: var(--color-ide-text);">
                  {{ steps[currentStep].title }}
                </h3>
                <p class="text-[12px] leading-relaxed" style="color: var(--color-ide-text-dim);">
                  {{ steps[currentStep].description }}
                </p>
              </div>
            </div>

            <!-- 快捷键列表 -->
            <div class="space-y-1.5 mt-4">
              <div
                v-for="sc in steps[currentStep].shortcuts"
                :key="sc"
                class="flex items-center gap-3 px-3 py-2 rounded-md text-[12px]"
                :style="{ background: 'var(--color-ide-bg)' }"
              >
                <kbd class="shrink-0 px-2 py-0.5 rounded text-[11px] font-mono font-bold"
                  :style="{
                    background: 'var(--color-ide-surface-active)',
                    color: 'var(--color-ide-accent)',
                    border: '1px solid var(--color-ide-border)',
                  }"
                >
                  {{ sc.split(" → ")[0] }}
                </kbd>
                <span class="text-[11px]" style="color: var(--color-ide-text-dim);">{{ sc.split(" → ")[1] || sc }}</span>
              </div>
            </div>
          </div>

          <!-- Footer -->
          <div class="flex items-center justify-between px-5 py-3 shrink-0"
            :style="{ borderTop: '1px solid var(--color-ide-border)' }"
          >
            <button
              class="flex items-center gap-1 text-[11px] transition-colors"
              style="color: var(--color-ide-text-dim);"
              @click="resetOnboarding"
              title="重新开始引导"
            >
              <RotateCw :size="11" /> 重置引导
            </button>

            <div class="flex items-center gap-2">
              <span class="text-[11px]" style="color: var(--color-ide-text-dim);">
                {{ currentStep + 1 }} / {{ totalSteps }}
              </span>

              <button
                v-if="!isFirstStep"
                class="flex items-center gap-1 px-3 h-7 rounded-[4px] text-[11px] font-medium transition-colors"
                :style="{ color: 'var(--color-ide-text-dim)', border: '1px solid var(--color-ide-border)' }"
                @click="prevStep"
              >
                <ChevronLeft :size="12" /> 上一步
              </button>

              <button
                class="flex items-center gap-1 px-3 h-7 rounded-[4px] text-[11px] font-medium transition-colors"
                :style="{
                  background: 'var(--color-ide-accent)',
                  color: '#fff',
                }"
                @click="nextStep"
              >
                <template v-if="isLastStep">
                  <Check :size="12" /> 开始使用
                </template>
                <template v-else>
                  下一步 <ChevronRight :size="12" />
                </template>
              </button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.onboard-fade-enter-active,
.onboard-fade-leave-active {
  transition: opacity 0.2s ease;
}
.onboard-fade-enter-from,
.onboard-fade-leave-to {
  opacity: 0;
}
</style>
