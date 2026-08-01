<template>
  <div class="pm-page">
    <!-- 左侧：匹配器列表 -->
    <aside class="pm-sidebar">
      <div class="pm-sidebar-header">
        <h3>匹配器</h3>
        <button class="pm-btn pm-btn-sm pm-btn-accent" @click="openRegister">+ 自定义</button>
      </div>
      <input v-model="searchQ" class="pm-search" placeholder="搜索匹配器..." />
      <div v-for="(group, gk) in groupedMatchers" :key="gk" class="pm-group">
        <div class="pm-group-label">{{ gk === 'builtin' ? '内置' : '自定义' }}</div>
        <div
          v-for="m in group"
          :key="m.id"
          class="pm-item" :class="{ active: selected === m.id }"
          @click="selected = m.id"
        >
          <div class="pm-item-row">
            <span class="pm-item-owner">{{ m.owner }}</span>
            <span class="pm-item-mode">{{ m.mode === 'multi_line' ? '多行' : '单行' }}</span>
            <button v-if="!m.is_builtin" class="pm-item-del" title="删除" @click.stop="deleteConfirm=m">&times;</button>
          </div>
          <div class="pm-item-label">{{ m.label }}</div>
          <div class="pm-item-id">{{ m.id }}</div>
        </div>
      </div>
      <div v-if="!matchers.length" class="pm-empty">加载中...</div>
    </aside>

    <!-- 中间：输入区 -->
    <main class="pm-main">
      <div class="pm-toolbar">
        <div class="pm-toolbar-left">
          <span class="pm-toolbar-label">匹配器：</span>
          <strong v-if="cur" class="pm-toolbar-matcher">{{ cur.label }}</strong>
          <span v-if="cur" class="pm-toolbar-owner">({{ cur.owner }})</span>
          <span v-else class="pm-toolbar-none">未选择</span>
        </div>
        <div class="pm-toolbar-right">
          <button class="pm-btn pm-btn-ghost" :disabled="!content.trim()" @click="autoDetect">自动检测</button>
          <button class="pm-btn pm-btn-primary" :disabled="!selected||!content.trim()||parsing" @click="doParse">
            {{ parsing ? '解析中...' : '解析' }}
          </button>
        </div>
      </div>
      <textarea v-model="content" class="pm-textarea" placeholder="在此粘贴构建/终端输出..." spellcheck="false" />
      <div v-if="content" class="pm-meta">{{ content.split('\n').filter(l=>l.trim()).length }} 行 | {{ content.length }} 字符</div>
    </main>

    <!-- 右侧：结果区 -->
    <aside v-if="results.length" class="pm-results">
      <div class="pm-results-header">
        <h3>诊断结果 ({{ total }})</h3>
        <span class="pm-results-matcher">匹配器：{{ matcherUsed }}</span>
      </div>
      <div class="pm-stats">
        <span v-for="s in sevs" :key="s" class="pm-stat" :class="{active:filterSev===s}" @click="filterSev=filterSev===s?null:s">
          <span class="pm-stat-dot" :class="s"></span>{{ sevLabel(s) }} {{ sevCount(s) }}
        </span>
        <span v-if="filterSev" class="pm-stat-clear" @click="filterSev=null">清除</span>
      </div>
      <div class="pm-table-wrap">
        <table class="pm-table">
          <thead><tr>
            <th class="c-sev">级别</th><th class="c-file">文件</th><th class="c-loc">行:列</th><th class="c-msg">消息</th><th class="c-code">代码</th>
          </tr></thead>
          <tbody>
            <tr v-for="(r,i) in filteredResults" :key="i" class="pm-row" :class="{expanded:expanded===i}" @click="expanded=expanded===i?null:i">
              <td><span class="pm-badge" :class="'s-'+r.severity">{{ sevShort(r.severity) }}</span></td>
              <td class="td-file" :title="r.file_path">{{ basename(r.file_path) }}</td>
              <td class="td-loc">{{ r.line }}{{ r.column!=null?':'+r.column:'' }}</td>
              <td class="td-msg">{{ r.message }}</td>
              <td class="td-code"><code v-if="r.code">{{ r.code }}</code></td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="expanded!==null&&filteredResults[expanded]" class="pm-detail">
        <div class="pm-detail-head"><strong>原始行</strong><button class="pm-btn pm-btn-sm pm-btn-ghost" @click="expanded=null">关闭</button></div>
        <pre class="pm-detail-raw">{{ filteredResults[expanded].raw_line }}</pre>
        <div class="pm-detail-meta">
          <span>文件：{{ filteredResults[expanded].file_path }}</span>
          <span>来源：{{ filteredResults[expanded].source }}</span>
          <span>匹配器：{{ filteredResults[expanded].matcher }}</span>
        </div>
      </div>
    </aside>
    <aside v-else-if="parsed" class="pm-results pm-results-empty">未解析到诊断结果</aside>

    <!-- 注册弹窗 -->
    <Teleport to="body">
      <div v-if="showRegister" class="pm-overlay" @click.self="showRegister=false">
        <div class="pm-modal">
          <div class="pm-modal-header"><h3>注册自定义匹配器</h3><button class="pm-modal-close" @click="showRegister=false">&times;</button></div>
          <div class="pm-modal-body">
            <div class="pm-fs">
              <div><label class="pm-lbl">ID*</label><input v-model="custom.id" class="pm-inp" placeholder="my-custom-matcher" /></div>
              <div><label class="pm-lbl">标签*</label><input v-model="custom.label" class="pm-inp" placeholder="My Custom" /></div>
            </div>
            <div class="pm-fs">
              <div><label class="pm-lbl">所有者</label><input v-model="custom.owner" class="pm-inp" /></div>
              <div><label class="pm-lbl">来源</label><input v-model="custom.source" class="pm-inp" /></div>
              <div><label class="pm-lbl">模式</label><select v-model="custom.mode" class="pm-inp"><option value="single_line">单行</option><option value="multi_line">多行</option></select></div>
            </div>
            <div><label class="pm-lbl">正则*</label><input v-model="custom.pattern.regexp" class="pm-inp pm-inp-mono" placeholder="^(.+):(\\d+):(\\d+):\\s+(.+)$" /><span v-if="regexErr" class="pm-err">{{ regexErr }}</span></div>
            <div class="pm-fs">
              <div><label class="pm-lbl">文件组</label><input v-model.number="custom.pattern.file_group" type="number" class="pm-inp pm-inp-num" /></div>
              <div><label class="pm-lbl">行号组</label><input v-model.number="custom.pattern.line_group" type="number" class="pm-inp pm-inp-num" /></div>
              <div><label class="pm-lbl">列号组</label><input v-model.number="custom.pattern.column_group" type="number" class="pm-inp pm-inp-num" /></div>
              <div><label class="pm-lbl">消息组</label><input v-model.number="custom.pattern.message_group" type="number" class="pm-inp pm-inp-num" /></div>
              <div><label class="pm-lbl">级别组</label><input v-model.number="custom.pattern.severity_group" type="number" class="pm-inp pm-inp-num" /></div>
              <div><label class="pm-lbl">代码组</label><input v-model.number="custom.pattern.code_group" type="number" class="pm-inp pm-inp-num" /></div>
            </div>
            <div><label class="pm-lbl">测试正则</label><input v-model="regexSample" class="pm-inp pm-inp-mono" placeholder="粘贴一行输出来测试..." @input="testRegex" />
              <div v-if="regexMatches!==null" class="pm-rx-r">
                <div v-if="regexMatches.length" class="pm-rx-ok">匹配成功 <span v-for="(g,gi) in regexMatches" :key="gi" class="pm-rx-g">G{{gi+1}}:<code>{{g??'(空)'}}</code></span></div>
                <div v-else class="pm-rx-no">无匹配</div>
              </div>
            </div>
          </div>
          <div class="pm-modal-footer"><button class="pm-btn pm-btn-ghost" @click="showRegister=false">取消</button><button class="pm-btn pm-btn-primary" :disabled="!canRegister" @click="doRegister">{{registering?'注册中...':'注册'}}</button></div>
        </div>
      </div>
    </Teleport>

    <!-- 删除确认 -->
    <Teleport to="body">
      <div v-if="deleteConfirm" class="pm-overlay" @click.self="deleteConfirm=null">
        <div class="pm-modal pm-modal-sm">
          <div class="pm-modal-header"><h3>确认删除</h3><button class="pm-modal-close" @click="deleteConfirm=null">&times;</button></div>
          <div class="pm-modal-body"><p>确定删除 <strong>"{{ deleteConfirm.label }}"</strong>？不可撤销。</p></div>
          <div class="pm-modal-footer"><button class="pm-btn pm-btn-ghost" @click="deleteConfirm=null">取消</button><button class="pm-btn pm-btn-danger" @click="doDelete">删除</button></div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { listMatchers, parseOutput, registerCustomMatcher, deleteCustomMatcher, type MatcherItem, type DiagnosticItem, type SeverityLevel, type MatcherMode } from '@/api/problemMatchers'

const matchers = ref<MatcherItem[]>([])
const searchQ = ref('')
const selected = ref('')
const content = ref('')
const parsing = ref(false)
const parsed = ref(false)
const results = ref<DiagnosticItem[]>([])
const total = ref(0)
const matcherUsed = ref('')
const filterSev = ref<SeverityLevel|null>(null)
const expanded = ref<number|null>(null)
const showRegister = ref(false)
const registering = ref(false)
const deleteConfirm = ref<MatcherItem|null>(null)
const regexSample = ref('')
const regexMatches = ref<string[]|null>(null)
const regexErr = ref('')
const custom = ref({id:'',label:'',owner:'custom',source:'custom',mode:'single_line' as MatcherMode,pattern:{regexp:'',file_group:1,line_group:2,column_group:3,message_group:4,severity_group:undefined as number|undefined,code_group:undefined as number|undefined}})

const sevs: SeverityLevel[] = ['error','warning','info','hint']
const cur = computed(()=>matchers.value.find(m=>m.id===selected.value)||null)
const groupedMatchers = computed(()=>{
  const q = searchQ.value.toLowerCase().trim()
  const by = matchers.value.filter(m=>q?[m.label,m.id,m.owner].some(s=>s.toLowerCase().includes(q)):true)
  return {builtin:by.filter(m=>m.is_builtin),custom:by.filter(m=>!m.is_builtin)}
})
const filteredResults = computed(()=>filterSev.value?results.value.filter(r=>r.severity===filterSev.value):results.value)
const canRegister = computed(()=>custom.value.id.trim()&&custom.value.label.trim()&&custom.value.pattern.regexp.trim()&&!regexErr.value&&!registering.value)

const basename=(p:string)=>p.split(/[/\\]/).pop()||p
const sevLabel=(s:SeverityLevel)=>({error:'错误',warning:'警告',info:'信息',hint:'提示'} as any)[s]
const sevShort=(s:SeverityLevel)=>({error:'E',warning:'W',info:'I',hint:'H'} as any)[s]
const sevCount=(s:SeverityLevel)=>results.value.filter(r=>r.severity===s).length

async function fetchMatchers(){try{const d=await listMatchers();matchers.value=d.matchers;if(!selected.value&&d.matchers.length)selected.value=d.matchers[0].id}catch{matchers.value=[]}}

async function doParse(){if(!selected.value||!content.value.trim())return;parsing.value=true;parsed.value=false;expanded.value=null;filterSev.value=null;try{const d=await parseOutput(selected.value,content.value);results.value=d.diagnostics;total.value=d.total;matcherUsed.value=d.matcher_used;parsed.value=true}finally{parsing.value=false}}

async function autoDetect(){if(!content.value.trim())return;parsing.value=true;parsed.value=false;expanded.value=null;filterSev.value=null;try{const d=await parseOutput('auto',content.value);results.value=d.diagnostics;total.value=d.total;matcherUsed.value=d.matcher_used;if(d.matcher_used&&matchers.value.some(m=>m.id===d.matcher_used))selected.value=d.matcher_used;parsed.value=true}finally{parsing.value=false}}

function openRegister(){custom.value={id:'',label:'',owner:'custom',source:'custom',mode:'single_line',pattern:{regexp:'',file_group:1,line_group:2,column_group:3,message_group:4}};regexSample.value='';regexMatches.value=null;regexErr.value='';showRegister.value=true}

function testRegex(){regexErr.value='';regexMatches.value=null;if(!custom.value.pattern.regexp||!regexSample.value)return;try{const re=new RegExp(custom.value.pattern.regexp);const m=re.exec(regexSample.value);regexMatches.value=m?Array.from(m).slice(1):[]}catch(e:any){regexErr.value=e.message}}

async function doRegister(){if(!canRegister.value)return;registering.value=true;try{await registerCustomMatcher({id:custom.value.id,label:custom.value.label,owner:custom.value.owner,source:custom.value.source,mode:custom.value.mode,pattern:{regexp:custom.value.pattern.regexp,file_group:custom.value.pattern.file_group,line_group:custom.value.pattern.line_group,column_group:custom.value.pattern.column_group??undefined,message_group:custom.value.pattern.message_group,severity_group:custom.value.pattern.severity_group??undefined,code_group:custom.value.pattern.code_group??undefined}});showRegister.value=false;await fetchMatchers()}catch{}finally{registering.value=false}}

async function doDelete(){if(!deleteConfirm.value)return;try{await deleteCustomMatcher(deleteConfirm.value.id);if(selected.value===deleteConfirm.value.id)selected.value=matchers.value.find(m=>m.is_builtin)?.id||'';deleteConfirm.value=null;await fetchMatchers()}catch{}}

onMounted(fetchMatchers)
</script>

<style scoped>
.pm-page{display:flex;height:calc(100vh - 56px);overflow:hidden}
/* 左侧 */
.pm-sidebar{width:280px;min-width:260px;border-right:1px solid var(--color-ide-border);background:var(--color-ide-bg-secondary);display:flex;flex-direction:column;overflow:hidden}
.pm-sidebar-header{display:flex;align-items:center;justify-content:space-between;padding:16px 16px 12px}
.pm-sidebar-header h3{margin:0;font-size:15px;font-weight:600;color:var(--color-ide-text-primary)}
.pm-search{margin:0 12px 12px;padding:7px 10px;border:1px solid var(--color-ide-border);border-radius:6px;background:var(--color-ide-bg-primary);color:var(--color-ide-text-primary);font-size:13px;outline:none}
.pm-search:focus{border-color:var(--color-ide-accent)}
.pm-group{overflow-y:auto;padding:0 0 8px}
.pm-group-label{padding:8px 16px 4px;font-size:11px;font-weight:600;text-transform:uppercase;color:var(--color-ide-text-tertiary)}
.pm-item{padding:8px 16px;cursor:pointer;border-left:3px solid transparent;transition:background .15s,border-color .15s}
.pm-item:hover{background:var(--color-ide-bg-hover)}
.pm-item.active{background:var(--color-ide-bg-active);border-left-color:var(--color-ide-accent)}
.pm-item-row{display:flex;align-items:center;gap:6px;margin-bottom:2px}
.pm-item-owner{font-size:11px;color:var(--color-ide-accent);background:color-mix(in srgb,var(--color-ide-accent) 15%,transparent);padding:1px 6px;border-radius:4px}
.pm-item-mode{font-size:10px;color:var(--color-ide-text-tertiary);padding:1px 5px;border:1px solid var(--color-ide-border);border-radius:3px}
.pm-item-del{margin-left:auto;background:none;border:none;color:var(--color-ide-text-tertiary);font-size:16px;cursor:pointer;opacity:0;transition:opacity .15s,color .15s}
.pm-item:hover .pm-item-del{opacity:1}
.pm-item-del:hover{color:#e57373}
.pm-item-label{font-size:13px;font-weight:500;color:var(--color-ide-text-primary)}
.pm-item-id{font-size:11px;color:var(--color-ide-text-tertiary);font-family:monospace}
.pm-empty{padding:24px 16px;text-align:center;color:var(--color-ide-text-tertiary)}
/* 中间 */
.pm-main{flex:1;min-width:0;display:flex;flex-direction:column;padding:16px;overflow:hidden}
.pm-toolbar{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;flex-shrink:0}
.pm-toolbar-left{display:flex;align-items:center;gap:6px;font-size:13px}
.pm-toolbar-label{color:var(--color-ide-text-secondary)}
.pm-toolbar-matcher{color:var(--color-ide-text-primary)}
.pm-toolbar-owner{color:var(--color-ide-text-tertiary);font-size:12px}
.pm-toolbar-none{color:var(--color-ide-text-tertiary)}
.pm-toolbar-right{display:flex;gap:8px}
.pm-textarea{flex:1;width:100%;min-height:300px;padding:14px;border:1px solid var(--color-ide-border);border-radius:8px;background:#0d1117;color:#d2d2d2;font-family:monospace;font-size:13px;line-height:1.5;resize:none;outline:none;box-sizing:border-box}
.pm-textarea:focus{border-color:var(--color-ide-accent)}
.pm-meta{margin-top:8px;font-size:12px;color:var(--color-ide-text-tertiary);flex-shrink:0}
/* 右侧 */
.pm-results{width:420px;min-width:340px;border-left:1px solid var(--color-ide-border);background:var(--color-ide-bg-secondary);display:flex;flex-direction:column;overflow:hidden}
.pm-results-empty{display:flex;align-items:center;justify-content:center;color:var(--color-ide-text-tertiary);font-size:13px}
.pm-results-header{padding:14px 16px 10px;display:flex;align-items:center;justify-content:space-between;flex-shrink:0}
.pm-results-header h3{margin:0;font-size:14px;font-weight:600;color:var(--color-ide-text-primary)}
.pm-results-matcher{font-size:11px;color:var(--color-ide-text-tertiary);font-family:monospace}
.pm-stats{display:flex;gap:6px;padding:0 16px 10px;flex-shrink:0}
.pm-stat{display:flex;align-items:center;gap:4px;font-size:12px;padding:3px 8px;border-radius:4px;cursor:pointer;color:var(--color-ide-text-secondary);border:1px solid transparent;transition:border-color .15s,background .15s}
.pm-stat:hover{background:var(--color-ide-bg-hover)}
.pm-stat.active{border-color:var(--color-ide-accent);background:color-mix(in srgb,var(--color-ide-accent) 10%,transparent)}
.pm-stat-dot{width:8px;height:8px;border-radius:50%}
.pm-stat-dot.error{background:#e57373}
.pm-stat-dot.warning{background:#ffb74d}
.pm-stat-dot.info{background:#64b5f6}
.pm-stat-dot.hint{background:#81c784}
.pm-stat-clear{margin-left:auto;font-size:11px;color:var(--color-ide-text-tertiary);cursor:pointer}
.pm-stat-clear:hover{color:var(--color-ide-text-primary)}
.pm-table-wrap{flex:1;overflow-y:auto;padding:0 16px}
.pm-table{width:100%;border-collapse:collapse;font-size:12px}
.pm-table th{text-align:left;padding:6px 6px;font-weight:600;color:var(--color-ide-text-tertiary);font-size:11px;text-transform:uppercase;border-bottom:1px solid var(--color-ide-border);position:sticky;top:0;background:var(--color-ide-bg-secondary);z-index:1}
.pm-table td{padding:5px 6px;border-bottom:1px solid color-mix(in srgb,var(--color-ide-border) 40%,transparent)}
.pm-row{cursor:pointer;transition:background .1s}
.pm-row:hover{background:var(--color-ide-bg-hover)}
.pm-row.expanded{background:var(--color-ide-bg-active)}
.c-sev{width:50px}.c-file{width:auto}.c-loc{width:52px}.c-msg{width:auto}.c-code{width:60px}
.td-file{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:120px}.td-loc{font-family:monospace}.td-msg{font-size:12px}.td-code code{font-size:11px;padding:1px 4px;border-radius:3px;background:color-mix(in srgb,var(--color-ide-text-tertiary) 15%,transparent)}
.pm-badge{display:inline-block;padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600}
.s-error{background:#e5737340;color:#e57373}
.s-warning{background:#ffb74d40;color:#ffb74d}
.s-info{background:#64b5f640;color:#64b5f6}
.s-hint{background:#81c78440;color:#81c784}
.pm-detail{margin:0 16px 12px;padding:10px;border:1px solid var(--color-ide-border);border-radius:6px;background:var(--color-ide-bg-primary)}
.pm-detail-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}
.pm-detail-raw{margin:0;padding:8px;background:#0d1117;color:#d2d2d2;border-radius:4px;font-size:12px;overflow-x:auto;white-space:pre-wrap;word-break:break-all}
.pm-detail-meta{display:flex;gap:16px;margin-top:8px;font-size:11px;color:var(--color-ide-text-tertiary)}
/* 弹窗 */
.pm-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;z-index:1000}
.pm-modal{background:var(--color-ide-bg-primary);border:1px solid var(--color-ide-border);border-radius:12px;width:640px;max-height:80vh;display:flex;flex-direction:column;box-shadow:0 8px 32px rgba(0,0,0,.4)}
.pm-modal-sm{width:400px}
.pm-modal-header{display:flex;align-items:center;justify-content:space-between;padding:16px 20px;border-bottom:1px solid var(--color-ide-border)}
.pm-modal-header h3{margin:0;font-size:16px}
.pm-modal-close{background:none;border:none;font-size:22px;cursor:pointer;color:var(--color-ide-text-tertiary)}
.pm-modal-close:hover{color:var(--color-ide-text-primary)}
.pm-modal-body{flex:1;overflow-y:auto;padding:16px 20px;display:flex;flex-direction:column;gap:12px}
.pm-modal-footer{display:flex;justify-content:flex-end;gap:8px;padding:12px 20px;border-top:1px solid var(--color-ide-border)}
/* 表单 */
.pm-fs{display:flex;gap:10px}.pm-fs>div{flex:1;min-width:0}
.pm-lbl{display:block;font-size:12px;font-weight:500;color:var(--color-ide-text-secondary);margin-bottom:4px}
.pm-inp{width:100%;padding:6px 10px;border:1px solid var(--color-ide-border);border-radius:6px;background:var(--color-ide-bg-secondary);color:var(--color-ide-text-primary);font-size:13px;outline:none;box-sizing:border-box}
.pm-inp:focus{border-color:var(--color-ide-accent)}
.pm-inp-mono{font-family:monospace}
.pm-inp-num{width:80px}
.pm-err{display:block;font-size:11px;color:#e57373;margin-top:3px}
.req{color:#e57373}
.pm-rx-r{margin-top:4px;font-size:12px}
.pm-rx-ok{color:#81c784}.pm-rx-no{color:var(--color-ide-text-tertiary)}
.pm-rx-g{margin-left:8px;color:var(--color-ide-text-secondary)}
.pm-rx-g code{color:var(--color-ide-accent)}
/* 按钮 */
.pm-btn{padding:7px 14px;border-radius:6px;font-size:13px;font-weight:500;cursor:pointer;border:1px solid transparent;transition:background .15s,opacity .15s}
.pm-btn:disabled{opacity:.5;cursor:not-allowed}
.pm-btn-sm{padding:4px 10px;font-size:12px}
.pm-btn-primary{background:var(--color-ide-accent);color:#fff}
.pm-btn-primary:hover:not(:disabled){filter:brightness(1.1)}
.pm-btn-accent{background:color-mix(in srgb,var(--color-ide-accent) 15%,transparent);color:var(--color-ide-accent);border-color:color-mix(in srgb,var(--color-ide-accent) 30%,transparent)}
.pm-btn-accent:hover{background:color-mix(in srgb,var(--color-ide-accent) 25%,transparent)}
.pm-btn-ghost{background:transparent;color:var(--color-ide-text-secondary);border-color:var(--color-ide-border)}
.pm-btn-ghost:hover:not(:disabled){background:var(--color-ide-bg-hover);color:var(--color-ide-text-primary)}
.pm-btn-danger{background:#e57353;color:#fff}
.pm-btn-danger:hover{background:#d32f2f}
</style>
