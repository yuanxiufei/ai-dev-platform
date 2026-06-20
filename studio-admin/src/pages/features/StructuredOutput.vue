<script setup lang="ts">
import { ref, computed } from 'vue'
import { structuredOutputApi, type GBNFConvertResult, type ResponseFormatPreviewResult } from '@/api/model-features'

const tab = ref<'convert' | 'templates' | 'preview'>('convert')
const schemaText = ref('')
const convertResult = ref<GBNFConvertResult | null>(null)
const convertError = ref('')
const converting = ref(false)

const templates = ref<Record<string, string>>({})
const selectedTemplate = ref('')

const previewSchema = ref('{"type":"object","properties":{"name":{"type":"string"},"age":{"type":"integer"}}}')
const previewProvider = ref('openai')
const previewResult = ref<ResponseFormatPreviewResult | null>(null)
const previewing = ref(false)

const sampleSchemas = [
  {
    label: '用户对象',
    json: { type: 'object', properties: { name: { type: 'string' }, email: { type: 'string' }, age: { type: 'integer' } }, required: ['name', 'email'] },
  },
  {
    label: '产品列表',
    json: { type: 'array', items: { type: 'object', properties: { id: { type: 'integer' }, title: { type: 'string' }, price: { type: 'number' } }, required: ['id', 'title'] } },
  },
  {
    label: '工具调用',
    json: { type: 'object', properties: { name: { type: 'string' }, arguments: { type: 'object' } }, required: ['name', 'arguments'] },
  },
]

const providers = [
  { value: 'openai', label: 'OpenAI (原生)' },
  { value: 'deepseek', label: 'DeepSeek (原生)' },
  { value: 'llama_cpp', label: 'llama.cpp (GBNF)' },
  { value: 'ollama', label: 'Ollama (GBNF)' },
  { value: 'anthropic', label: 'Claude (提示)' },
]

async function doConvert() {
  if (!schemaText.value.trim()) return
  converting.value = true
  convertError.value = ''
  convertResult.value = null
  try {
    const schema = JSON.parse(schemaText.value)
    convertResult.value = (await structuredOutputApi.schemaToGbnf(schema)).data
  } catch (e: any) {
    convertError.value = e?.message || '转换失败'
  } finally {
    converting.value = false
  }
}

function loadSample(sample: typeof sampleSchemas[0]) {
  schemaText.value = JSON.stringify(sample.json, null, 2)
  convertError.value = ''
  convertResult.value = null
}

async function loadTemplates() {
  const { data } = await structuredOutputApi.listTemplates()
  templates.value = data.templates
  const keys = Object.keys(data.templates)
  if (keys.length) selectedTemplate.value = keys[0]
}

async function doPreview() {
  previewing.value = true
  previewResult.value = null
  try {
    const schema = JSON.parse(previewSchema.value)
    previewResult.value = (await structuredOutputApi.previewResponseFormat(
      { type: 'json_schema', json_schema: { name: 'response', schema, strict: true } },
      previewProvider.value,
    )).data
  } catch (e) {
  } finally {
    previewing.value = false
  }
}

const selectedSample = ref<typeof sampleSchemas[0] | null>(null)
function selectSample(s: typeof sampleSchemas[0]) {
  selectedSample.value = s
  loadSample(s)
}
</script>

<template>
  <div class="p-6 max-w-6xl mx-auto space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-bold text-white">结构化输出</h1>
        <p class="text-sm text-gray-400 mt-1">JSON Schema → GBNF 语法 | OpenAI response_format 兼容</p>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 bg-white/5 rounded-lg p-1 w-fit">
      <button v-for="t in [
        { key: 'convert', label: 'Schema→GBNF' },
        { key: 'preview', label: 'Provider 预览' },
        { key: 'templates', label: '内置模板' },
      ]" :key="t.key" @click="tab = t.key" :class="[
          'px-4 py-2 rounded-md text-sm font-medium transition-colors',
          tab === t.key ? 'bg-brand-600 text-white' : 'text-gray-400 hover:text-white',
        ]">
        {{ t.label }}
      </button>
    </div>

    <!-- Convert Tab -->
    <div v-if="tab === 'convert'" class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div class="bg-white/5 rounded-xl p-5 border border-white/10 space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-semibold text-white">JSON Schema 输入</h3>
          <div class="flex gap-2">
            <button v-for="s in sampleSchemas" :key="s.label" @click="selectSample(s)"
              :class="['px-3 py-1 rounded text-xs transition-colors', selectedSample?.label === s.label ? 'bg-brand-600 text-white' : 'bg-white/10 text-gray-300 hover:bg-white/20']">
              {{ s.label }}
            </button>
          </div>
        </div>
        <textarea v-model="schemaText" rows="12"
          class="w-full bg-black/30 border border-white/10 rounded-lg p-3 text-sm text-gray-200 font-mono focus:outline-none focus:border-brand-500 resize-none"
          placeholder='{"type":"object","properties":{"name":{"type":"string"}},"required":["name"]}'></textarea>
        <button @click="doConvert" :disabled="converting || !schemaText.trim()"
          class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed">
          {{ converting ? '转换中...' : '转换为 GBNF' }}
        </button>
        <p v-if="convertError" class="text-red-400 text-sm">{{ convertError }}</p>
      </div>

      <div class="bg-white/5 rounded-xl p-5 border border-white/10 space-y-3">
        <h3 class="text-sm font-semibold text-white">GBNF 输出</h3>
        <div v-if="convertResult" class="space-y-3">
          <div class="flex gap-3 text-xs">
            <span :class="['px-2 py-0.5 rounded', convertResult.valid ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400']">
              {{ convertResult.valid ? '✓ 合法' : '✗ 不合法' }}
            </span>
            <span class="bg-white/10 text-gray-300 px-2 py-0.5 rounded">{{ convertResult.rules_count }} 条规则</span>
          </div>
          <pre class="bg-black/40 rounded-lg p-4 text-xs text-green-400 font-mono overflow-auto max-h-96 whitespace-pre-wrap">{{ convertResult.gbnf }}</pre>
        </div>
        <div v-else class="text-gray-500 text-sm py-8 text-center">输入 JSON Schema 并点击转换</div>
      </div>
    </div>

    <!-- Templates Tab -->
    <div v-if="tab === 'templates'" class="bg-white/5 rounded-xl p-5 border border-white/10 space-y-4">
      <div class="flex items-center gap-3">
        <span class="text-sm font-semibold text-white">选择模板:</span>
        <select v-model="selectedTemplate"
          class="bg-white/10 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-brand-500">
          <option v-for="(_, k) in templates" :key="k" :value="k">{{ k }}</option>
        </select>
        <button @click="loadTemplates" class="px-3 py-2 rounded-lg bg-white/10 hover:bg-white/20 text-sm text-gray-300 transition-colors">刷新</button>
      </div>
      <pre v-if="templates[selectedTemplate]" class="bg-black/40 rounded-lg p-4 text-xs text-green-400 font-mono overflow-auto max-h-96 whitespace-pre-wrap">{{ templates[selectedTemplate] }}</pre>
      <p v-else class="text-gray-500 text-sm">点击刷新加载模板</p>
    </div>

    <!-- Preview Tab -->
    <div v-if="tab === 'preview'" class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div class="bg-white/5 rounded-xl p-5 border border-white/10 space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-semibold text-white">JSON Schema</h3>
          <select v-model="previewProvider"
            class="bg-white/10 border border-white/10 rounded-lg px-3 py-1.5 text-xs text-gray-200 focus:outline-none">
            <option v-for="p in providers" :key="p.value" :value="p.value">{{ p.label }}</option>
          </select>
        </div>
        <textarea v-model="previewSchema" rows="8"
          class="w-full bg-black/30 border border-white/10 rounded-lg p-3 text-sm text-gray-200 font-mono focus:outline-none focus:border-brand-500 resize-none"></textarea>
        <button @click="doPreview" :disabled="previewing"
          class="w-full py-2.5 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium text-sm transition-colors disabled:opacity-50">
          {{ previewing ? '预览中...' : '预览适配结果' }}
        </button>
      </div>

      <div class="bg-white/5 rounded-xl p-5 border border-white/10 space-y-3">
        <h3 class="text-sm font-semibold text-white">适配结果 ({{ previewResult?.provider_name || '-' }})</h3>
        <div v-if="previewResult" class="space-y-4">
          <div>
            <p class="text-xs text-gray-400 mb-1">OpenAI 格式</p>
            <pre class="bg-black/40 rounded-lg p-3 text-xs text-blue-300 font-mono overflow-auto max-h-32">{{ JSON.stringify(previewResult.openai_format, null, 2) }}</pre>
          </div>
          <div v-if="previewResult.gbnf_grammar">
            <p class="text-xs text-gray-400 mb-1">GBNF 语法</p>
            <pre class="bg-black/40 rounded-lg p-3 text-xs text-green-400 font-mono overflow-auto max-h-32">{{ previewResult.gbnf_grammar }}</pre>
          </div>
          <div v-if="previewResult.system_prompt_hint">
            <p class="text-xs text-gray-400 mb-1">System Prompt 提示</p>
            <pre class="bg-black/40 rounded-lg p-3 text-xs text-yellow-300 font-mono overflow-auto max-h-24 whitespace-pre-wrap">{{ previewResult.system_prompt_hint }}</pre>
          </div>
        </div>
        <div v-else class="text-gray-500 text-sm py-8 text-center">选择 Provider 并点击预览</div>
      </div>
    </div>
  </div>
</template>
