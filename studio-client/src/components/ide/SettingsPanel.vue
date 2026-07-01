<template>
  <Teleport to="body">
    <Transition name="settings-panel">
      <div v-if="visible" class="fixed inset-0 z-[9998] flex" @click.self="close">
        <div class="absolute inset-0 bg-black/40 backdrop-blur-sm" />
        <div ref="panelRef" class="relative w-full max-w-4xl h-[85vh] my-auto mx-auto bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded-xl shadow-2xl shadow-black/50 overflow-hidden flex flex-col" @click.stop>
          <!-- Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-[var(--color-ide-border)] bg-[var(--color-ide-bg-secondary)]">
            <h2 class="text-lg font-semibold text-[var(--color-ide-text)] flex items-center gap-2"><LSettings :size="20"/> 设置</h2>
            <button @click="close" class="p-1.5 rounded-lg hover:bg-[var(--color-ide-hover)] text-[var(--color-ide-text-dim)]"><X :size="18"/></button>
          </div>
          <div class="flex flex-1 overflow-hidden">
            <!-- Nav -->
            <nav class="w-56 shrink-0 border-r border-[var(--color-ide-border)] py-2 overflow-y-auto bg-[var(--color-ide-bg-tertiary)]">
              <button v-for="t in tabs" :key="t.id" :class="['w-full flex items-center gap-3 px-5 py-2.5 text-sm text-left transition-colors',at===t.id?'bg-[var(--color-ide-accent)]/10 text-[var(--color-ide-accent)] font-medium border-r-2 border-[var(--color-ide-accent)]':'text-[var(--color-ide-text-secondary)] hover:bg-[var(--color-ide-hover)] hover:text-[var(--color-ide-text)]']" @click="at=t.id"><component :is="t.icon" :size="16"/>{{ t.label }}</button>
            </nav>
            <!-- Content -->
            <div class="flex-1 overflow-y-auto p-6">
              <!-- General -->
              <section v-if="at==='general'">
                <h3 class="text-base font-medium mb-6">通用</h3>
                <SG title="外观"><SI label="颜色主题"><select v-model="themeStore.active" class="ss"><option v-for="t in themeStore.themes" :key="t.id" :value="t.id">{{ t.label }}</option></select></SI>
                  <SI label="缩放级别"><div class="flex items-center gap-2"><button @click="ls.appearance.zoomLevel=Math.max(0.5,ls.appearance.zoomLevel-0.1)" class="bi"><Minus :size="14"/></button><span class="w-16 text-center text-xs font-mono">{{Math.round(ls.appearance.zoomLevel*100)}}%</span><button @click="ls.appearance.zoomLevel=Math.min(2,ls.appearance.zoomLevel+0.1)" class="bi"><Plus :size="14"/></button></div></SI>
                  <SI label="字体家族"><select v-model="ls.editor.fontFamily" class="ss min-w-[220px]"><option value="'JetBrains Mono',monospace">JetBrains Mono</option><option value="'Fira Code',monospace">Fira Code</option></select></SI>
                  <SI :label="`字号: ${ls.editor.fontSize}px`"><input v-model.number="ls.editor.fontSize" type="range" min="10" max="28" step="1" class="sl"/></SI>
                  <SI label="自动保存"><select v-model="ls.editor.autoSave" class="ss"><option value="off">关</option><option value="afterDelay">延迟后</option></select></SI>
                </SG>
              </section>
              <!-- Editor -->
              <section v-if="at==='editor'">
                <h3 class="text-base font-medium mb-6">编辑器</h3>
                <SG title="文本编辑器">
                  <SI label="制表符宽度"><div class="flex gap-1"><button v-for="n in [2,4,8]" :key="n" :class="['tb',ls.editor.tabSize===n&&'active']" @click="ls.editor.tabSize=n">{{ n }}</button></div></SI>
                  <SI label="自动换行"><select v-model="ls.editor.wordWrap" class="ss"><option value="off">关闭</option><option value="on">开启</option></select></SI>
                  <SI label="行号"><select v-model="ls.editor.lineNumbers" class="ss"><option value="on">显示</option><option value="off">隐藏</option></select></SI>
                  <SI label="小地图"><ToggleSwitch :model-value="ls.editor.minimap" @update:modelValue="ls.editor.minimap=$event"/></SI>
                  <SI label="光标闪烁样式"><select v-model="ls.editor.cursorBlinking" class="ss"><option value="smooth">平滑</option><option value="blink">闪烁</option></select></SI>
                </SG>
              </section>
              <!-- Terminal -->
              <section v-if="at==='terminal'">
                <h3 class="text-base font-medium mb-6">终端</h3>
                <SG title="终端配置">
                  <SI label="默认 Shell"><select v-model="ls.terminal.defaultProfile" class="ss"><option value="powershell">PowerShell</option><option value="bash">Bash</option></select></SI>
                  <SI :label="`字号: ${ls.terminal.fontSize}px`"><input v-model.number="ls.terminal.fontSize" type="range" min="10" max="24" step="1" class="sl"/></SI>
                  <SI label="光标闪烁"><ToggleSwitch :model-value="ls.terminal.cursorBlinking" @update:modelValue="ls.terminal.cursorBlinking=$event"/></SI>
                  <SI :label="`滚动缓冲区: ${ls.terminal.scrollback} 行`"><input v-model.number="ls.terminal.scrollback" type="range" min="500" max="50000" step="500" class="sl"/></SI>
                </SG>
              </section>
              <!-- AI -->
              <section v-if="at==='ai'">
                <h3 class="text-base font-medium mb-6">AI 助手</h3>
                <SG title="AI 配置">
                  <SI label="提供商"><select v-model="ls.ai.provider" class="ss"><option value="openai">OpenAI</option><option value="anthropic">Anthropic</option><option value="deepseek">DeepSeek</option><option value="zhipu">智谱 AI</option></select></SI>
                  <SI label="模型"><select v-model="ls.ai.model" class="ss"><optgroup label="OpenAI"><option value="gpt-4o">GPT-4o</option></optgroup><optgroup label="Anthropic"><option value="claude-sonnet-4">Claude Sonnet 4</option></optgroup></select></SI>
                  <SI label="API 密钥"><input v-model="ls.ai.apiKey" placeholder="sk-" class="si w-80"/></SI>
                  <SI :label="`Temperature: ${ls.ai.temperature}`"><input v-model.number="ls.ai.temperature" type="range" min="0" max="2" step="0.1" class="sl w-48"/></SI>
                </SG>
              </section>
              <!-- Plugins -->
              <section v-if="at==='extensions'">
                <h3 class="text-base font-medium mb-6">扩展 & 插件</h3>
                <div class="space-y-3">
                  <div v-for="p in installedPlugins" :key="p.id" class="rounded-lg border border-[var(--color-ide-border)] p-4 hover:border-[var(--color-ide-accent)]/30 transition-colors">
                    <div class="flex items-start justify-between">
                      <div class="flex items-start gap-3"><div class="w-10 h-10 rounded-lg bg-gradient-to-br from-[var(--color-ide-accent)]/20 to-purple-500/20 flex items-center justify-center shrink-0"><Puzzle :size="18" class="text-[var(--color-ide-accent)]"/></div><div><h4 class="text-sm font-medium text-[var(--color-ide-text)]">{{ p.name }}</h4><p class="text-xs text-[var(--color-ide-text-dim)] mt-0.5">{{ p.description }}</p></div></div>
                      <ToggleSwitch :model-value="p.enabled" @update:modelValue="(v:boolean)=>v?enable(p.id):disable(p.id)"/>
                    </div>
                  </div>
                </div>
              </section>
              <!-- Memory — Hermes-style -->
              <section v-if="at==='memory'">
                <h3 class="text-base font-medium mb-6">记忆管理</h3>
                <SG title="记忆配置">
                  <SI label="启用记忆"><ToggleSwitch :model-value="ls.memory.enabled" @update:modelValue="ls.memory.enabled=$event"/></SI>
                  <SI label="用户画像"><ToggleSwitch :model-value="ls.memory.userProfileEnabled" @update:modelValue="ls.memory.userProfileEnabled=$event"/></SI>
                  <SI :label="`记忆字符限制: ${ls.memory.charLimit}`"><input v-model.number="ls.memory.charLimit" type="range" min="100" max="10000" step="100" class="sl"/></SI>
                  <SI :label="`用户字符限制: ${ls.memory.userCharLimit}`"><input v-model.number="ls.memory.userCharLimit" type="range" min="100" max="10000" step="100" class="sl"/></SI>
                  <SI label="写入需审批"><ToggleSwitch :model-value="ls.memory.writeApproval" @update:modelValue="ls.memory.writeApproval=$event"/></SI>
                </SG>
              </section>
              <!-- Voice — Hermes-style -->
              <section v-if="at==='voice'">
                <h3 class="text-base font-medium mb-6">语音设置</h3>
                <SG title="文字转语音 (TTS)">
                  <SI label="TTS 引擎"><select v-model="ls.voice.ttsProvider" class="ss"><option value="edge">Microsoft Edge</option><option value="openai">OpenAI TTS</option><option value="browser">浏览器内置</option></select></SI>
                  <SI :label="`语速: ${ls.voice.ttsSpeed.toFixed(1)}x`"><input v-model.number="ls.voice.ttsSpeed" type="range" min="0.5" max="2" step="0.1" class="sl"/></SI>
                </SG>
                <SG title="语音转文字 (STT)">
                  <SI label="STT 引擎"><select v-model="ls.voice.sttProvider" class="ss"><option value="browser">浏览器内置</option><option value="openai">OpenAI Whisper</option><option value="custom">自定义</option></select></SI>
                </SG>
              </section>
              <!-- Proxy — Hermes-style -->
              <section v-if="at==='proxy'">
                <h3 class="text-base font-medium mb-6">代理设置</h3>
                <SG title="网络代理">
                  <SI label="HTTPS 代理"><input v-model="ls.proxy.httpsProxy" placeholder="http://127.0.0.1:7890" class="si w-80"/></SI>
                  <SI label="HTTP 代理"><input v-model="ls.proxy.httpProxy" placeholder="http://127.0.0.1:7890" class="si w-80"/></SI>
                  <SI label="SOCKS 代理"><input v-model="ls.proxy.allProxy" placeholder="socks5://127.0.0.1:7890" class="si w-80"/></SI>
                  <SI label="直连白名单"><input v-model="ls.proxy.noProxy" placeholder="localhost,127.0.0.1,.local" class="si w-80"/></SI>
                </SG>
              </section>
              <!-- Session — Hermes-style -->
              <section v-if="at==='session'">
                <h3 class="text-base font-medium mb-6">会话管理</h3>
                <SG title="会话配置">
                  <SI label="重置模式"><select v-model="ls.session.resetMode" class="ss"><option value="none">不重置</option><option value="idle">空闲后重置</option><option value="daily">每日重置</option><option value="both">空闲+每日</option></select></SI>
                  <SI v-if="ls.session.resetMode==='idle'||ls.session.resetMode==='both'" :label="`空闲分钟: ${ls.session.idleMinutes} 分钟`"><input v-model.number="ls.session.idleMinutes" type="range" min="10" max="10080" step="30" class="sl"/></SI>
                  <SI v-if="ls.session.resetMode==='daily'||ls.session.resetMode==='both'" :label="`重置时间: ${ls.session.resetHour}:00`"><input v-model.number="ls.session.resetHour" type="range" min="0" max="23" step="1" class="sl"/></SI>
                </SG>
              </section>
              <!-- Privacy — Hermes-style -->
              <section v-if="at==='privacy'">
                <h3 class="text-base font-medium mb-6">隐私设置</h3>
                <SG title="数据保护">
                  <SI label="脱敏 PII"><ToggleSwitch :model-value="ls.privacy.redactPii" @update:modelValue="ls.privacy.redactPii=$event"/></SI>
                </SG>
              </section>
            </div>
          </div>
          <div class="flex items-center justify-end gap-3 px-6 py-4 border-t border-[var(--color-ide-border)] bg-[var(--color-ide-bg-secondary)]">
            <button class="btn btn-ghost" @click="resetS"><RotateCcw :size="14"/> 重置为默认值</button>
            <button class="btn btn-primary" @click="apply"><Check :size="14"/> 应用</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { Bot, BrainCircuit, Check, Globe, Minus, Moon, Plus, Puzzle, RotateCcw, Settings as LSettings, Shield, Sun, TerminalSquare, Type, X } from "lucide-vue-next"
import { computed, reactive, ref } from "vue"
import { usePlugins } from "@/composables/usePlugins"
import { useThemeStore, type ThemeId } from "@/stores/useThemeStore"
import ToggleSwitch from "./ui/Toggle.vue"

const SG = {
  props: ["title"],
  template: `<div class="mb-8 last:mb-0"><h4 class="text-sm font-medium text-[var(--color-ide-text-secondary)] mb-4">{{ title }}</h4><slot/></div>`,
}
const SI = {
  props: ["label"],
  template: `<div class="flex items-center justify-between py-3 border-b border-[var(--color-ide-border)]/50 last:border-0"><span class="text-sm text-[var(--color-ide-text-secondary)]">{{ label }}</span><slot/></div>`,
}

const props = defineProps<{ visible: boolean }>()
const emit = defineEmits<(e: "update:visible", val: boolean) => void>()
const { installedPlugins, enable, disable } = usePlugins()
const themeStore = useThemeStore()
const at = ref("general")
const tabs = [
  { id: "general", label: "通用", icon: Type },
  { id: "editor", label: "编辑器", icon: Type },
  { id: "terminal", label: "终端", icon: TerminalSquare },
  { id: "ai", label: "AI 助手", icon: Bot },
  { id: "extensions", label: "扩展", icon: Puzzle },
  { id: "memory", label: "记忆", icon: BrainCircuit },
  { id: "voice", label: "语音", icon: Bot },
  { id: "proxy", label: "代理", icon: Globe },
  { id: "session", label: "会话", icon: Shield },
  { id: "privacy", label: "隐私", icon: Shield },
]
const ls = reactive({
  editor: {
    fontSize: 14,
    fontFamily: "'JetBrains Mono',monospace",
    tabSize: 4,
    insertSpaces: true,
    wordWrap: "off",
    lineNumbers: "on",
    minimap: true,
    autoSave: "afterDelay",
    formatOnSave: true,
    cursorBlinking: "smooth",
  },
  appearance: {
    theme: "codebuddy-dark",
    accentColor: "#0078D4",
    sidebarWidth: 260,
    panelHeight: 250,
    zoomLevel: 1,
  },
  terminal: {
    fontSize: 13,
    defaultProfile: "powershell",
    cursorBlinking: true,
    scrollback: 10000,
  },
  ai: {
    provider: "openai",
    model: "gpt-4o",
    apiKey: "",
    baseUrl: undefined as string | undefined,
    maxTokens: 4096,
    temperature: 0.7,
  },
  memory: {
    enabled: true,
    userProfileEnabled: true,
    charLimit: 5000,
    userCharLimit: 3000,
    writeApproval: false,
  },
  voice: {
    ttsProvider: 'edge' as string,
    ttsSpeed: 1.0,
    sttProvider: 'browser' as string,
  },
  proxy: {
    httpsProxy: '',
    httpProxy: '',
    allProxy: '',
    noProxy: 'localhost,127.0.0.1,.local',
  },
  session: {
    resetMode: 'none' as 'both' | 'idle' | 'daily' | 'none',
    idleMinutes: 30,
    resetHour: 0,
  },
  privacy: {
    redactPii: false,
  },
})
function close() {
  emit("update:visible", false)
}
function apply() {
  close()
}
function resetS() {
  // Reset settings to defaults
}
</script>

<style scoped>
.ss{padding:6px 30px 6px 10px;border-radius:6px;background:var(--color-ide-bg-tertiary);border:1px solid var(--color-ide-border);color:var(--color-ide-text);font-size:13px;outline:none;appearance:none;background-image:url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e");background-position:right 8px center;background-repeat:no-repeat;background-size:16px;cursor:pointer}
.si{padding:6px 10px;border-radius:6px;background:var(--color-ide-bg-tertiary);border:1px solid var(--color-ide-border);color:var(--color-ide-text);font-size:13px;outline:none}
.bi{display:flex;align-items:center;justify:center;width:28px;height:28px;border-radius:6px;color:var(--color-ide-text-secondary);background:var(--color-ide-bg-tertiary);border:1px solid var(--color-ide-border);cursor:pointer}
.tb{padding:4px 10px;font-size:12px;font-weight:600;border-radius:6px;color:var(--color-ide-text-secondary);background:transparent;border:1px solid transparent;cursor:pointer}
.tb:hover{background:var(--color-ide-hover)}.tb.active{background:var(--color-ide-accent);color:white;border-color:var(--color-ide-accent)}
.sl{height:4px;border-radius:2px;appearance:none;background:var(--color-ide-border);cursor:pointer}
.btn{display:inline-flex;align-items:center;gap:6px;padding:7px 14px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;border:1px solid transparent}
.btn-primary{background:var(--color-ide-accent);color:white}.btn-primary:hover{opacity:.9}
.btn-ghost{background:transparent;color:var(--color-ide-text-secondary);border-color:var(--color-ide-border)}.btn-ghost:hover{background:var(--color-ide-hover);color:var(--color-ide-text)}
.settings-panel-enter-active,.settings-panel-leave-active{transition:opacity .2s ease}.settings-panel-enter-from,.settings-panel-leave-to{opacity:0}
</style>
