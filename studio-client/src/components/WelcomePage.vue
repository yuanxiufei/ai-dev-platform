<script setup lang="ts">
import { Brain, Code2, Layers, Palette, Rocket, Zap } from "lucide-vue-next"

const emit = defineEmits<{
  (e: "start"): void
  (e: "quickPrompt", prompt: string): void
}>()

const features = [
  {
    icon: Code2,
    title: "Vibe 编程",
    desc: "用自然语言描述想法，AI 自动生成全栈项目代码",
    gradient: "from-blue-500/20 to-cyan-500/10",
    iconColor: "text-blue-400",
  },
  {
    icon: Brain,
    title: "知识库驱动",
    desc: "接入项目文档和代码库，让 AI 理解你的项目上下文",
    gradient: "from-purple-500/20 to-pink-500/10",
    iconColor: "text-purple-400",
  },
  {
    icon: Layers,
    title: "多模型调度",
    desc: "自动选择最优模型，本地+云端无缝切换",
    gradient: "from-amber-500/20 to-orange-500/10",
    iconColor: "text-amber-400",
  },
  {
    icon: Palette,
    title: "截图转代码",
    desc: "上传设计稿截图，一键生成可运行的前端代码",
    gradient: "from-emerald-500/20 to-teal-500/10",
    iconColor: "text-emerald-400",
  },
  {
    icon: Rocket,
    title: "一键部署",
    desc: "生成的项目可直接部署到云端，即刻上线",
    gradient: "from-rose-500/20 to-red-500/10",
    iconColor: "text-rose-400",
  },
  {
    icon: Zap,
    title: "工具链编排",
    desc: "连接 MCP 工具和插件，构建你自己的 AI 工作流",
    gradient: "from-indigo-500/20 to-violet-500/10",
    iconColor: "text-indigo-400",
  },
]

const quickPrompts = [
  { icon: Code2, text: "帮我创建一个 React 待办事项应用" },
  { icon: Palette, text: "生成一个现代化的登录页面设计" },
  { icon: Brain, text: "分析这个项目的架构并给出优化建议" },
  { icon: Zap, text: "为我的 API 编写单元测试" },
]
</script>

<template>
  <div class="flex flex-col items-center justify-center min-h-full py-12 px-6">
    <!-- Robot 图标区 -->
    <div class="relative mb-8">
      <div class="absolute inset-0 bg-gradient-to-br from-brand-500/20 via-purple-500/10 to-transparent blur-3xl rounded-full scale-150" />
      <div class="relative w-24 h-24 rounded-3xl bg-gradient-to-br from-brand-400 via-purple-500 to-pink-500 shadow-2xl shadow-brand-500/30 flex items-center justify-center animate-float">
        <Sparkles class="w-10 h-10 text-white" />
      </div>
    </div>

    <!-- 标题 -->
    <h1 class="text-3xl md:text-4xl font-bold text-center mb-3">
      <span class="bg-gradient-to-r from-white via-gray-200 to-gray-400 bg-clip-text text-transparent">
        让想法成为现实
      </span>
    </h1>
    <p class="text-gray-400 text-sm md:text-base text-center max-w-lg mb-10">
      AI Studio 是你的全能 AI 编程伙伴。用自然语言描述需求，让 AI 帮你构建、优化和部署项目。
    </p>

    <!-- 开始按钮 -->
    <button
      class="flex items-center gap-2 px-8 py-3 rounded-2xl bg-gradient-to-r from-brand-500 to-purple-500 text-white font-semibold text-base hover:shadow-xl hover:shadow-brand-500/25 hover:scale-105 active:scale-95 transition-all duration-300 mb-12"
      @click="emit('start')"
    >
      <MessageCircle class="w-5 h-5" />
      开始对话
      <ArrowRight class="w-4 h-4" />
    </button>

    <!-- 功能特点 -->
    <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 w-full max-w-3xl mb-12">
      <div
        v-for="(feat, idx) in features"
        :key="idx"
        class="group relative rounded-2xl border border-white/8 bg-surface-800/50 hover:bg-surface-800 hover:border-white/12 transition-all duration-300 p-5 cursor-default"
      >
        <div :class="['w-10 h-10 rounded-xl bg-gradient-to-br flex items-center justify-center mb-3', feat.gradient]">
          <component :is="feat.icon" :class="['w-5 h-5', feat.iconColor]" />
        </div>
        <h3 class="text-sm font-semibold text-gray-200 mb-1.5">{{ feat.title }}</h3>
        <p class="text-xs text-gray-500 leading-relaxed">{{ feat.desc }}</p>
      </div>
    </div>

    <!-- 快捷提示 -->
    <div class="w-full max-w-2xl">
      <p class="text-xs font-medium text-gray-500 mb-3 text-center">试试这些</p>
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
        <button
          v-for="(qp, idx) in quickPrompts"
          :key="idx"
          class="flex items-center gap-3 rounded-xl border border-white/8 bg-white/3 hover:bg-white/8 hover:border-brand-500/20 px-4 py-3 text-left text-sm text-gray-300 transition-all duration-200 group"
          @click="emit('quickPrompt', qp.text)"
        >
          <component :is="qp.icon" class="w-4 h-4 text-gray-500 group-hover:text-brand-400 shrink-0 transition-colors" />
          <span class="truncate">{{ qp.text }}</span>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
@keyframes float {
  0%, 100% { transform: translateY(0px); }
  50% { transform: translateY(-8px); }
}
.animate-float {
  animation: float 3s ease-in-out infinite;
}
</style>
