<script setup lang="ts">
import { ref } from 'vue'
import { structuredOutputApi, type GBNFConvertResult, type ResponseFormatPreviewResult } from '@/api/model-features'
import { Code, Braces } from 'lucide-vue-next'

const schemaText = ref('')
const convertResult = ref<GBNFConvertResult | null>(null)
const converting = ref(false)
const error = ref('')

const previewSchema = ref('{"type":"object","properties":{"name":{"type":"string"},"age":{"type":"integer"}}}')
const previewProvider = ref('openai')
const previewResult = ref<ResponseFormatPreviewResult | null>(null)
const previewing = ref(false)

const tab = ref<'convert' | 'preview'>('convert')

const sampleSchemas = [
  { label: '用户对象', json: { type: 'object', properties: { name: { type: 'string' }, email: { type: 'string' }, age: { type: 'integer' } }, required: ['name', 'email'] } },
  { label: '产品列表', json: { type: 'array', items: { type: 'object', properties: { id: { type: 'integer' }, title: { type: 'string' }, price: { type: 'number' } } } } },
  { label: '工具调用', json: { type: 'object', properties: { name: { type: 'string' }, arguments: { type: 'object' } }, required: ['name', 'arguments'] } },
]

async function doConvert() {
  if (!schemaText.value.trim()) return
  converting.value = true; error.value = ''
  try {
    convertResult.value = (await structuredOutputApi.schemaToGbnf(JSON.parse(schemaText.value))).data
  } catch (e: any) { error.value = e?.message || '转换失败' }
  finally { converting.value = false }
}

function loadSample(s: typeof sampleSchemas[0]) {
  schemaText.value = JSON.stringify(s.json, null, 2); error.value = ''; convertResult.value = null
}

async function doPreview() {
  previewing.value = true
  try {
    const schema = JSON.parse(previewSchema.value)
    previewResult.value = (await structuredOutputApi.previewResponseFormat({ type: 'json_schema', json_schema: { name: 'response', schema, strict: true } }, previewProvider.value)).data
  } catch {}
  finally { previewing.value = false }
}
</script>

<template>
  <div class="p-6 max-w-5xl mx-auto space-y-6">
    <header>
      <h1 class="text-3xl font-bold text-white">结构化输出</h1>
      <p class="text-gray-400 mt-2">JSON Schema → GBNF 语法 · 多 Provider 格式适配</p>
    </header>

    <div class="flex gap-1 bg-gray-800/50 rounded-xl p-1 w-fit">
      <button v-for="t in [{ k: 'convert', l: 'Schema→GBNF' }, { k: 'preview', l: 'Provider 预览' }]" :key="t.k" @click="tab = t.k as typeof tab" :class="['px-4 py-2 rounded-lg text-sm font-medium transition', tab === t.k ? 'bg-brand-500 text-white' : 'text-gray-400 hover:text-white']">{{ t.l }}</button>
    </div>

    <div v-if="tab === 'convert'" class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div class="bg-gray-900/50 rounded-2xl p-6 border border-gray-800/50 space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="font-semibold text-white">JSON Schema 输入</h3>
          <div class="flex gap-1.5">
            <button v-for="s in sampleSchemas" :key="s.label" @click="loadSample(s)" class="px-2.5 py-1 rounded-lg text-xs bg-gray-800 hover:bg-gray-700 text-gray-300 transition">{{ s.label }}</button>
          </div>
        </div>
        <textarea v-model="schemaText" rows="12" class="w-full bg-gray-800 border border-gray-700/50 rounded-xl p-3 text-sm text-gray-200 font-mono outline-none focus:border-brand-500/50 resize-none" placeholder='{"type":"object","properties":{"name":{"type":"string"}}}' />
        <button @click="doConvert" :disabled="converting || !schemaText.trim()" class="w-full py-3 rounded-xl bg-gradient-to-r from-brand-500 to-purple-500 text-white font-medium disabled:opacity-50">{{ converting ? '转换中...' : '转换为 GBNF' }}</button>
        <p v-if="error" class="text-red-400 text-sm">{{ error }}</p>
      </div>
      <div class="bg-gray-900/50 rounded-2xl p-6 border border-gray-800/50 space-y-3">
        <h3 class="font-semibold text-white">GBNF 输出</h3>
        <div v-if="convertResult" class="space-y-3">
          <span :class="['px-2 py-0.5 rounded text-xs', convertResult.valid ? 'bg-green-500/20 text-green-400' : 'bg-red-500/20 text-red-400']">{{ convertResult.valid ? '✓ 合法' : '✗ 不合法' }}</span>
          <span class="ml-2 text-xs text-gray-400">{{ convertResult.rules_count }} 条规则</span>
          <pre class="bg-gray-800 rounded-xl p-4 text-xs text-green-400 font-mono overflow-auto max-h-96 whitespace-pre-wrap">{{ convertResult.gbnf }}</pre>
        </div>
        <div v-else class="text-gray-500 text-sm py-8 text-center">输入 JSON Schema 并点击转换</div>
      </div>
    </div>

    <div v-if="tab === 'preview'" class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div class="bg-gray-900/50 rounded-2xl p-6 border border-gray-800/50 space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="font-semibold text-white">JSON Schema</h3>
          <select v-model="previewProvider" class="bg-gray-800 border border-gray-700/50 rounded-xl px-3 py-1.5 text-xs text-gray-200 outline-none">
            <option value="openai">OpenAI (原生)</option>
            <option value="deepseek">DeepSeek</option>
            <option value="anthropic">Claude</option>
          </select>
        </div>
        <textarea v-model="previewSchema" rows="8" class="w-full bg-gray-800 border border-gray-700/50 rounded-xl p-3 text-sm text-gray-200 font-mono outline-none resize-none" />
        <button @click="doPreview" :disabled="previewing" class="w-full py-3 rounded-xl bg-gradient-to-r from-brand-500 to-purple-500 text-white font-medium disabled:opacity-50">{{ previewing ? '预览中...' : '预览适配结果' }}</button>
      </div>
      <div class="bg-gray-900/50 rounded-2xl p-6 border border-gray-800/50 space-y-3">
        <h3 class="font-semibold text-white">适配结果 ({{ previewResult?.provider_name || '-' }})</h3>
        <div v-if="previewResult" class="space-y-4">
          <pre class="bg-gray-800 rounded-xl p-3 text-xs text-blue-300 font-mono overflow-auto max-h-48">{{ JSON.stringify(previewResult.openai_format, null, 2) }}</pre>
          <div v-if="previewResult.gbnf_grammar">
            <p class="text-xs text-gray-400 mb-1">GBNF 语法</p>
            <pre class="bg-gray-800 rounded-xl p-3 text-xs text-green-400 font-mono overflow-auto max-h-32">{{ previewResult.gbnf_grammar }}</pre>
          </div>
        </div>
        <div v-else class="text-gray-500 text-sm py-8 text-center">选择 Provider 并点击预览</div>
      </div>
    </div>
  </div>
</template>
