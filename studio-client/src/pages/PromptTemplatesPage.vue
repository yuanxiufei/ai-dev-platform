<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue"
import { Loader2, Plus, Search, Trash2 } from "lucide-vue-next"
import {
  type PromptTemplateData,
  promptTemplateApi,
  type TemplateVariableDef,
} from "@/api/prompt-templates"

const templates = ref<PromptTemplateData[]>([])
const categories = ref<{ name: string; count: number }[]>([])
const selectedCategory = ref("")
const searchQuery = ref("")
const loading = ref(false)
const showModal = ref(false)
const showResolve = ref(false)
const resolvedResult = ref("")
const editingId = ref<string | null>(null)

const form = reactive({
  command: "",
  title: "",
  prompt: "",
  icon: "",
  category: "general",
  description: "",
  variables: {} as Record<string, TemplateVariableDef>,
})
const newVarName = ref("")
const newVarType = ref("string")
const newVarDesc = ref("")
const resolveValues = ref<Record<string, string | number | boolean>>({})

const filtered = computed(() => {
  let list = templates.value
  if (selectedCategory.value)
    list = list.filter((t) => t.category === selectedCategory.value)
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    list = list.filter(
      (t) =>
        t.command.toLowerCase().includes(q) ||
        t.title.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q),
    )
  }
  return list
})

async function loadTemplates() {
  loading.value = true
  try {
    const [tRes, cRes] = await Promise.all([
      promptTemplateApi.list(),
      promptTemplateApi.categories(),
    ])
    templates.value = tRes.templates
    categories.value = cRes.categories
  } finally {
    loading.value = false
  }
}

function openCreate() {
  editingId.value = null
  resetForm()
  showModal.value = true
}

function addVariable() {
  const name = newVarName.value.trim()
  if (!name || form.variables[name]) return
  form.variables[name] = {
    type: newVarType.value,
    default: "",
    description: newVarDesc.value,
    required: false,
    options: [],
  }
  newVarName.value = ""
  newVarDesc.value = ""
}

function removeVariable(name: string) {
  delete form.variables[name]
}

async function saveTemplate() {
  if (!form.command || !form.title || !form.prompt) return
  await promptTemplateApi.create({
    command: form.command,
    title: form.title,
    prompt: form.prompt,
    variables: form.variables,
    icon: form.icon,
    category: form.category,
    description: form.description,
  })
  showModal.value = false
  resetForm()
  loadTemplates()
}

async function deleteTemplate(id: string) {
  if (!confirm("删除此模板？")) return
  await promptTemplateApi.delete(id)
  await loadTemplates()
}

async function resolveTemplate(tpl: PromptTemplateData) {
  resolveValues.value = {}
  for (const name of Object.keys(tpl.variables)) {
    resolveValues.value[name] = String(tpl.variables[name].default || "")
  }
  editingId.value = tpl.id
  resolvedResult.value = ""
  showResolve.value = true
}

async function doResolve() {
  const res = await promptTemplateApi.resolve(
    editingId.value!,
    resolveValues.value,
  )
  resolvedResult.value = res.resolved_prompt
}

function useAsPrompt(text: string) {
  // 复制到剪贴板并提示可用在对话中
  navigator.clipboard.writeText(text)
}

function resetForm() {
  form.command = ""
  form.title = ""
  form.prompt = ""
  form.icon = ""
  form.category = "general"
  form.description = ""
  form.variables = {}
}

onMounted(loadTemplates)
</script>

<template>
  <div class="p-6">
    <header class="flex items-center justify-between mb-6">
      <div>
        <h1 class="text-2xl font-bold text-white flex items-center gap-2">
          <Wand2 class="w-6 h-6 text-brand-400" />
          Prompt 模板
        </h1>
        <p class="text-sm text-[var(--color-ide-text-dim)] mt-1">
          斜杠命令模板 — 填入变量快速生成 Prompt，可复制到对话中使用
        </p>
      </div>
      <button
        @click="openCreate"
        class="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 transition text-white text-sm font-medium"
      >
        <Plus class="w-4 h-4" /> 创建模板
      </button>
    </header>

    <!-- 搜索/过滤 -->
    <div class="flex items-center gap-3 mb-6">
      <div class="relative flex-1 max-w-sm">
        <Search
          class="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--color-ide-text-dim)]"
        />
        <input
          v-model="searchQuery"
          placeholder="搜索命令或标题..."
          class="w-full pl-9 pr-3 py-2 bg-surface-800 border border-[var(--color-ide-border)] rounded-lg text-sm text-white placeholder-[var(--color-ide-text-dim)] focus:outline-none focus:border-brand-500"
        />
      </div>
      <select
        v-model="selectedCategory"
        class="px-3 py-2 bg-surface-800 border border-[var(--color-ide-border)] rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
      >
        <option value="">全部分类</option>
        <option
          v-for="c in categories"
          :key="c.name"
          :value="c.name"
        >
          {{ c.name }} ({{ c.count }})
        </option>
      </select>
    </div>

    <!-- 加载 -->
    <div
      v-if="loading"
      class="flex items-center justify-center py-12"
    >
      <RefreshCw class="w-6 h-6 animate-spin text-[var(--color-ide-text-dim)]" />
    </div>

    <!-- 空状态 -->
    <div
      v-else-if="filtered.length === 0"
      class="text-center py-16"
    >
      <div
        class="w-16 h-16 mx-auto mb-4 rounded-2xl bg-surface-800 flex items-center justify-center"
      >
        <Wand2 class="w-8 h-8 text-[var(--color-ide-text-dim)]" />
      </div>
      <p class="text-[var(--color-ide-text-dim)] mb-1">暂无 Prompt 模板</p>
      <p class="text-sm text-[var(--color-ide-text-dim)] mb-4">
        创建模板后可在对话中使用斜杠命令快速填充
      </p>
      <div class="grid grid-cols-2 gap-3 max-w-md mx-auto text-left">
        <div class="p-3 rounded-xl bg-surface-800/50 border border-[var(--color-ide-border)]">
          <div class="text-xs font-mono text-brand-400 mb-1">/gen-api</div>
          <div class="text-xs text-[var(--color-ide-text-dim)]">生成 REST API 端点代码</div>
        </div>
        <div class="p-3 rounded-xl bg-surface-800/50 border border-[var(--color-ide-border)]">
          <div class="text-xs font-mono text-brand-400 mb-1">/code-review</div>
          <div class="text-xs text-[var(--color-ide-text-dim)]">全面代码审查分析</div>
        </div>
      </div>
    </div>

    <!-- 模板列表 -->
    <div v-else class="grid gap-3">
      <div
        v-for="tpl in filtered"
        :key="tpl.id"
        class="flex items-start gap-4 p-4 rounded-xl bg-surface-800/60 border border-[var(--color-ide-border)] hover:border-brand-500/30 transition group"
      >
        <div
          class="text-xl shrink-0 w-10 h-10 flex items-center justify-center rounded-lg bg-brand-500/10"
        >
          {{ tpl.icon || '📝' }}
        </div>
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <code class="text-sm font-mono text-brand-400">{{ tpl.command }}</code>
            <span class="text-sm font-medium text-white">{{ tpl.title }}</span>
            <span
              class="text-xs px-1.5 py-0.5 rounded bg-surface-700 text-[var(--color-ide-text-dim)]"
            >
              {{ tpl.category }}
            </span>
          </div>
          <p class="text-sm text-[var(--color-ide-text-dim)] mb-1.5 line-clamp-2">
            {{ tpl.description || tpl.prompt.substring(0, 100) }}
          </p>
          <div class="flex items-center gap-1.5 flex-wrap">
            <span
              v-for="(v, k) in tpl.variables"
              :key="k"
              class="text-[11px] px-1.5 py-0.5 rounded bg-orange-500/10 text-orange-400 font-mono"
            >
              &#123;&#123;{{ k }}&#125;&#125;
            </span>
          </div>
        </div>
        <div
          class="flex items-center gap-1.5 shrink-0 opacity-0 group-hover:opacity-100 transition"
        >
          <button
            @click="resolveTemplate(tpl)"
            title="填充变量生成 Prompt"
            class="p-1.5 rounded-lg hover:bg-green-500/20 transition"
          >
            <Zap class="w-4 h-4 text-green-400" />
          </button>
          <button
            @click="navigator.clipboard.writeText(tpl.prompt);"
            title="复制模板文本"
            class="p-1.5 rounded-lg hover:bg-surface-700 transition"
          >
            <Copy class="w-4 h-4 text-[var(--color-ide-text-dim)]" />
          </button>
          <button
            @click="deleteTemplate(tpl.id)"
            class="p-1.5 rounded-lg hover:bg-red-500/20 transition"
          >
            <X class="w-4 h-4 text-red-400" />
          </button>
        </div>
      </div>
    </div>

    <!-- 创建弹窗 -->
    <Teleport to="body">
      <div
        v-if="showModal"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
        @click.self="showModal = false"
      >
        <div
          class="bg-surface-900 rounded-xl border border-[var(--color-ide-border)] w-[680px] max-h-[85vh] flex flex-col shadow-2xl"
        >
          <div
            class="flex items-center justify-between p-4 border-b border-[var(--color-ide-border)]"
          >
            <h3 class="font-medium text-white">创建个人模板</h3>
            <button
              @click="showModal = false"
              class="p-1.5 rounded-lg hover:bg-surface-700 text-[var(--color-ide-text-dim)] transition"
            >
              <X class="w-4 h-4" />
            </button>
          </div>
          <div class="flex-1 overflow-auto p-4 space-y-3">
            <div class="grid grid-cols-3 gap-3">
              <div class="col-span-2">
                <label class="block text-xs text-[var(--color-ide-text-dim)] mb-1">
                  命令 <span class="text-red-400">*</span>
                </label>
                <input
                  v-model="form.command"
                  placeholder="/gen-api"
                  class="w-full px-3 py-2 bg-surface-800 border border-[var(--color-ide-border)] rounded-lg text-sm font-mono text-brand-400 focus:outline-none focus:border-brand-500"
                />
              </div>
              <div>
                <label class="block text-xs text-[var(--color-ide-text-dim)] mb-1">图标</label>
                <input
                  v-model="form.icon"
                  placeholder="⚡"
                  class="w-full px-3 py-2 bg-surface-800 border border-[var(--color-ide-border)] rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
                />
              </div>
            </div>
            <div class="grid grid-cols-2 gap-3">
              <div>
                <label class="block text-xs text-[var(--color-ide-text-dim)] mb-1">
                  标题 <span class="text-red-400">*</span>
                </label>
                <input
                  v-model="form.title"
                  placeholder="生成 API 端点"
                  class="w-full px-3 py-2 bg-surface-800 border border-[var(--color-ide-border)] rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
                />
              </div>
              <div>
                <label class="block text-xs text-[var(--color-ide-text-dim)] mb-1">分类</label>
                <input
                  v-model="form.category"
                  placeholder="studio"
                  class="w-full px-3 py-2 bg-surface-800 border border-[var(--color-ide-border)] rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
                />
              </div>
            </div>
            <div>
              <label class="block text-xs text-[var(--color-ide-text-dim)] mb-1">描述</label>
              <input
                v-model="form.description"
                placeholder="简要说明这个模板的用途"
                class="w-full px-3 py-2 bg-surface-800 border border-[var(--color-ide-border)] rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
              />
            </div>
            <div>
              <label class="block text-xs text-[var(--color-ide-text-dim)] mb-1">
                Prompt 模板 <span class="text-red-400">*</span>
                <span class="text-[var(--color-ide-text-dim)]">（使用 {'{{'} variable {'}}'} 标记变量）</span>
              </label>
              <textarea
                v-model="form.prompt"
                rows="4"
                placeholder="你是一个 {{ role }}，请为以下代码生成 {{ output_type }}..."
                class="w-full px-3 py-2 bg-surface-800 border border-[var(--color-ide-border)] rounded-lg text-sm text-white font-mono focus:outline-none focus:border-brand-500 resize-none"
              />
            </div>
            <!-- 变量 -->
            <div>
              <label class="block text-xs text-[var(--color-ide-text-dim)] mb-1.5">变量</label>
              <div class="flex gap-2 mb-2">
                <input
                  v-model="newVarName"
                  placeholder="变量名"
                  class="flex-1 px-3 py-1.5 bg-surface-800 border border-[var(--color-ide-border)] rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
                />
                <select
                  v-model="newVarType"
                  class="px-3 py-1.5 bg-surface-800 border border-[var(--color-ide-border)] rounded-lg text-sm text-white"
                >
                  <option value="string">string</option>
                  <option value="number">number</option>
                  <option value="boolean">boolean</option>
                  <option value="select">select</option>
                </select>
                <input
                  v-model="newVarDesc"
                  placeholder="说明"
                  class="flex-1 px-3 py-1.5 bg-surface-800 border border-[var(--color-ide-border)] rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
                />
                <button
                  @click="addVariable"
                  class="px-3 py-1.5 rounded-lg bg-brand-500 text-white text-sm font-medium"
                >
                  添加
                </button>
              </div>
              <div class="flex flex-wrap gap-1.5">
                <span
                  v-for="(v, k) in form.variables"
                  :key="k"
                  class="flex items-center gap-1 text-xs px-2 py-1 rounded bg-surface-700 text-[var(--color-ide-text)]"
                >
                  {{ k }} ({{ v.type }})
                  <button
                    @click="removeVariable(k)"
                    class="text-red-400 hover:text-red-300"
                  >
                    <X class="w-3 h-3" />
                  </button>
                </span>
              </div>
            </div>
          </div>
          <div class="flex gap-2 justify-end p-4 border-t border-[var(--color-ide-border)]">
            <button
              @click="showModal = false"
              class="px-4 py-2 rounded-lg bg-surface-800 hover:bg-surface-700 text-sm text-[var(--color-ide-text)] transition"
            >
              取消
            </button>
            <button
              @click="saveTemplate"
              :disabled="!form.command || !form.title || !form.prompt"
              class="px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed transition text-white text-sm font-medium"
            >
              创建
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- 填充变量弹窗 -->
    <Teleport to="body">
      <div
        v-if="showResolve"
        class="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
        @click.self="showResolve = false; resolvedResult = ''"
      >
        <div
          class="bg-surface-900 rounded-xl border border-[var(--color-ide-border)] w-[560px] max-h-[80vh] flex flex-col shadow-2xl"
        >
          <div
            class="flex items-center justify-between p-4 border-b border-[var(--color-ide-border)]"
          >
            <h3 class="font-medium text-white">填充变量</h3>
            <button
              @click="showResolve = false; resolvedResult = ''"
              class="p-1.5 rounded-lg hover:bg-surface-700 text-[var(--color-ide-text-dim)] transition"
            >
              <X class="w-4 h-4" />
            </button>
          </div>
          <div class="p-4 space-y-3 overflow-auto flex-1">
            <div
              v-for="(v, k) in editingId
                ? templates.find((t) => t.id === editingId)?.variables || {}
                : {}"
              :key="k"
              class="mb-2"
            >
              <label class="block text-xs text-[var(--color-ide-text-dim)] mb-1">
                {{ k }}
                <span class="text-[var(--color-ide-text-dim)]">({{ v.type }})</span>
                <span v-if="v.description" class="text-[var(--color-ide-text-dim)]">
                  — {{ v.description }}
                </span>
              </label>
              <input
                v-model="resolveValues[k]"
                :placeholder="String(v.default || '')"
                class="w-full px-3 py-1.5 bg-surface-800 border border-[var(--color-ide-border)] rounded-lg text-sm text-white focus:outline-none focus:border-brand-500"
              />
            </div>
            <p
              v-if="!Object.keys(editingId ? templates.find(t => t.id === editingId)?.variables || {} : {}).length"
              class="text-sm text-[var(--color-ide-text-dim)]"
            >
              此模板没有变量，将直接使用原始 Prompt。
            </p>
            <button
              @click="doResolve"
              class="w-full px-4 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium transition"
            >
              填充解析
            </button>
            <div v-if="resolvedResult" class="relative">
              <pre
                class="p-3 bg-surface-800 rounded-lg text-sm text-[var(--color-ide-text)] whitespace-pre-wrap font-mono leading-relaxed"
              >{{ resolvedResult }}</pre>
              <button
                @click="navigator.clipboard.writeText(resolvedResult)"
                class="absolute top-2 right-2 p-1.5 rounded-lg bg-surface-700 hover:bg-surface-600 transition"
                title="复制到对话中使用"
              >
                <Copy class="w-4 h-4 text-[var(--color-ide-text-dim)]" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
