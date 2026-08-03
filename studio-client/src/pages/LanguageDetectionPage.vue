<template>
  <div class="ld-page">
    <div class="ld-header"><h1>Language Detection</h1><p>Detect language from text using AI-powered detection models</p></div>
    <div class="ld-main">
      <div class="ld-input-panel">
        <div class="panel-header"><TypeIcon class="w-4 h-4" /><span>Text Input</span><span class="char-count">{{ inputText.length }} chars</span></div>
        <textarea v-model="inputText" placeholder="Enter text to detect its language..." class="ld-textarea" :disabled="detecting" maxlength="50000"></textarea>
        <div class="ld-actions">
          <div class="ld-opts">
            <label class="opt-label">Top-K:</label>
            <select v-model.number="topK" class="opt-select"><option v-for="k in [1,3,5,10]" :key="k" :value="k">{{ k }}</option></select>
          </div>
          <div class="ld-btns">
            <button class="btn-clear" @click="clearInput" :disabled="detecting || !inputText">Clear</button>
            <button class="btn-detect" @click="runDetection" :disabled="detecting || !inputText.trim()">
              <Loader2Icon v-if="detecting" class="w-4 h-4 animate-spin" /><SearchIcon v-else class="w-4 h-4" />
              {{ detecting ? 'Detecting...' : 'Detect Language' }}
            </button>
          </div>
        </div>
      </div>
      <div class="ld-results-panel">
        <div class="panel-header"><BarChart3Icon class="w-4 h-4" /><span>Results</span></div>
        <div v-if="!results.length && !detecting && !errorMsg" class="ld-empty">
          <LanguagesIcon class="w-12 h-12 empty-icon" /><p>Enter text and click "Detect Language"</p>
        </div>
        <div v-if="errorMsg" class="ld-error"><AlertCircleIcon class="w-4 h-4" /><span>{{ errorMsg }}</span></div>
        <div v-if="results.length" class="ld-results-list">
          <div v-for="(r, i) in results" :key="r.lang_code" class="result-item" :class="{ 'is-top': i === 0 }">
            <div class="result-rank">#{{ i + 1 }}</div>
            <div class="result-info">
              <div class="result-name">{{ r.lang_name }} <code>{{ r.lang_code }}</code></div>
              <div class="result-bar-wrap"><div class="result-bar" :style="{ width: (r.confidence * 100) + '%' }"></div></div>
            </div>
            <div class="result-pct">{{ (r.confidence * 100).toFixed(1) }}%</div>
          </div>
        </div>
        <div v-if="textLength > 0" class="ld-meta">Text length: {{ textLength }} characters</div>
      </div>
    </div>
    <div class="ld-lang-map">
      <div class="panel-header"><GlobeIcon class="w-4 h-4" /><span>Supported Languages</span><span class="lang-count">{{ langMapTotal }} languages</span></div>
      <div class="lang-tags"><span v-for="(name, code) in langMap" :key="code" class="lang-tag" :class="{ active: topCode === code }">{{ name }} <small>{{ code }}</small></span></div>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import { detectLanguage, getLanguageMap, type LanguageDetectResult, type LanguageMapResponse } from '@/api/languageDetection'
import { Search, Type, BarChart3, Languages, Globe, AlertCircle, Loader2 } from 'lucide-vue-next'
const SearchIcon=Search; const TypeIcon=Type; const BarChart3Icon=BarChart3; const LanguagesIcon=Languages; const GlobeIcon=Globe; const AlertCircleIcon=AlertCircle; const Loader2Icon=Loader2
const inputText=ref(''); const topK=ref(3); const detecting=ref(false); const results=ref<LanguageDetectResult[]>([]); const textLength=ref(0); const errorMsg=ref('')
const langMap=ref<Record<string,string>>({}); const langMapTotal=ref(0); const topCode=ref('')
async function runDetection(){if(!inputText.value.trim())return; detecting.value=true; errorMsg.value=''; try{const res=await detectLanguage({text:inputText.value,top_k:topK.value}); results.value=res.results; textLength.value=res.text_length; topCode.value=res.results[0]?.lang_code||''}catch(e:any){errorMsg.value=e?.message||'Detection failed'; results.value=[]}finally{detecting.value=false}}
function clearInput(){inputText.value=''; results.value=[]; textLength.value=0; errorMsg.value=''; topCode.value=''}
async function loadLangMap(){try{const m:LanguageMapResponse=await getLanguageMap(); langMap.value=m.languages; langMapTotal.value=m.total}catch{/**/}}
loadLangMap()
</script>
<style scoped>
.ld-page{display:flex;flex-direction:column;gap:16px;padding:24px;max-width:1200px;margin:0 auto;color:var(--color-ide-fg, #e0e0e0)}
.ld-header h1{font-size:22px;font-weight:600;margin:0 0 4px;color:var(--color-ide-fg, #e0e0e0)}
.ld-header p{font-size:13px;color:var(--color-ide-fg-muted, #999);margin:0}
.ld-main{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.panel-header{display:flex;align-items:center;gap:8px;font-size:13px;font-weight:600;color:var(--color-ide-fg-muted, #999);margin-bottom:12px}
.char-count,.lang-count{margin-left:auto;font-size:11px;color:var(--color-ide-fg-subtle, #666)}
.ld-input-panel,.ld-results-panel,.ld-lang-map{background:var(--color-ide-bg-secondary, #1e1e2e);border:1px solid var(--color-ide-border, #333);border-radius:8px;padding:16px}
.ld-textarea{width:100%;height:200px;resize:vertical;background:var(--color-ide-bg-primary, #16162a);color:var(--color-ide-fg, #e0e0e0);border:1px solid var(--color-ide-border, #333);border-radius:6px;padding:12px;font-family:monospace;font-size:13px;line-height:1.5;outline:none;transition:border-color .2s;box-sizing:border-box}
.ld-textarea:focus{border-color:var(--color-ide-accent, #6366f1)}
.ld-textarea:disabled{opacity:.5}
.ld-actions{display:flex;justify-content:space-between;align-items:center;margin-top:12px;flex-wrap:wrap;gap:8px}
.ld-opts{display:flex;align-items:center;gap:6px;font-size:12px}
.opt-select{background:var(--color-ide-bg-primary);color:var(--color-ide-fg);border:1px solid var(--color-ide-border);border-radius:4px;padding:4px 8px;font-size:12px;outline:none}
.ld-btns{display:flex;gap:8px}
.btn-clear{padding:6px 14px;background:transparent;color:var(--color-ide-fg-muted);border:1px solid var(--color-ide-border);border-radius:6px;font-size:12px;cursor:pointer}
.btn-clear:hover{color:var(--color-ide-fg);border-color:var(--color-ide-fg-muted)}
.btn-detect{display:flex;align-items:center;gap:6px;padding:6px 16px;background:var(--color-ide-accent, #6366f1);color:#fff;border:none;border-radius:6px;font-size:12px;font-weight:500;cursor:pointer;transition:opacity .2s}
.btn-detect:hover:not(:disabled){opacity:.9}
.btn-detect:disabled,.btn-clear:disabled{opacity:.4;cursor:not-allowed}
.ld-empty{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px 20px;gap:12px}.empty-icon{color:var(--color-ide-fg-subtle, #555)}.ld-empty p{font-size:13px;color:var(--color-ide-fg-subtle, #666);margin:0}
.ld-error{display:flex;align-items:center;gap:8px;padding:12px;background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.3);border-radius:6px;color:#f87171;font-size:13px}
.ld-results-list{display:flex;flex-direction:column;gap:8px}
.result-item{display:flex;align-items:center;gap:12px;padding:10px 12px;background:var(--color-ide-bg-primary, #16162a);border-radius:6px;border:1px solid transparent}
.result-item.is-top{border-color:var(--color-ide-accent, #6366f1);background:var(--color-ide-bg-primary, #1a1a30)}
.result-rank{font-size:12px;font-weight:700;color:var(--color-ide-fg-subtle, #555);min-width:24px}
.result-info{flex:1;min-width:0}.result-name{font-size:13px;font-weight:500;margin-bottom:6px}.result-name code{font-size:11px;color:var(--color-ide-fg-muted);margin-left:6px;background:var(--color-ide-bg-secondary);padding:1px 5px;border-radius:3px}
.result-bar-wrap{height:6px;background:var(--color-ide-bg-secondary, #2a2a3a);border-radius:3px;overflow:hidden}.result-bar{height:100%;background:var(--color-ide-accent, #6366f1);border-radius:3px;transition:width .4s ease}
.result-pct{font-size:14px;font-weight:600;color:var(--color-ide-accent, #6366f1);white-space:nowrap}
.ld-meta{font-size:11px;color:var(--color-ide-fg-subtle);margin-top:12px;text-align:right}
.lang-tags{display:flex;flex-wrap:wrap;gap:6px;max-height:200px;overflow-y:auto}.lang-tag{font-size:11px;padding:4px 10px;background:var(--color-ide-bg-primary);border:1px solid var(--color-ide-border);border-radius:4px;color:var(--color-ide-fg-muted)}.lang-tag small{opacity:.6}.lang-tag.active{background:var(--color-ide-accent);color:#fff;border-color:var(--color-ide-accent)}.lang-tag.active small{opacity:.8}
.animate-spin{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
@media(max-width:768px){.ld-main{grid-template-columns:1fr}}
</style>