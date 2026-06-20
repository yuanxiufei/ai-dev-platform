<script setup lang="ts">
/** CodeBuddy IDE — AI Chat Panel */
import { ref, computed, nextTick } from 'vue'
import { Send, Bot, User, Sparkles, RefreshCw, Copy, ThumbsUp, ThumbsDown, Paperclip, AtSign } from 'lucide-vue-next'

const messages = ref<Array<{ role:'user'|'assistant'|'system'; content:string; timestamp:number; toolCalls?:Array<{name:string;args?:any;result?:string}> }>>([{ role:'assistant', content:'', timestamp:Date.now(), toolCalls:[] }])
const inputText = ref(''), isLoading = ref(false), mc = ref<HTMLDivElement|null>(null)
const hasMessages = computed(() => messages.value.some(m => m.content || m.toolCalls?.length))

function sb(): void { nextTick(() => { if (mc.value) mc.value.scrollTop = mc.value.scrollHeight }) }

async function sendMessage(): Promise<void> {
  const text = inputText.value.trim(); if (!text && !isLoading.value) return
  messages.value.push({ role:'user', content:text, timestamp:Date.now() }); inputText.value=''; isLoading=true; sb()
  await new Promise(r=>setTimeout(r,300))
  const am:{role:string;content:string;timestamp:number;toolCalls:any[]}={ role:'assistant', content:'', timestamp:Date.now(), toolCalls:[] }
  messages.value.push(am)
  const resp = genResponse(text)
  for(let i=0;i<=resp.length;i+=3){await new Promise(r=>setTimeout(r,15));am.content=resp.slice(0,i);sb()}
  if(text.includes('读取')||text.includes('read')) am.toolCalls=[{name:'读取 main.py L1-End',result:'+1230 -610'}]
  isLoading=false; sb()
}

function genResponse(input:string):string{
  const l=input.toLowerCase()
  if(l.includes('hello')||l.includes('hi')||l.includes('你好')) return `Hi Buddy 👋\n\n我可以帮你：\n• 📁 浏览和编辑项目文件\n• 🔧 执行命令和脚本\n• 💬 分析代码并给出建议`
  return `我理解你的请求："${input}"\n\n让我分析一下这个需求...\n\n有什么具体细节需要补充吗？`
}
</script>

<template>
  <div class="h-full flex flex-col bg-[var(--color-ide-bg)]">
    <!-- Welcome -->
    <div v-if="messages.length<=1 && !hasMessages" class="flex-1 flex flex-col items-center justify-center p-6 text-center select-none">
      <div class="mb-4"><svg width="72" height="72" viewBox="0 0 128 128" fill="none"><rect x="28" y="32" width="72" height="56" rx="16" fill="#35354a" stroke="#55557a" stroke-width="2"/><rect x="38" y="42" width="52" height="30" rx="6" fill="#1e1e2e"/><circle cx="52" cy="56" r="5" fill="#89b4fa"/><circle cx="76" cy="56" r="5" fill="#89b4fa"/><line x1="64" y1="32" x2="64" y2="18" stroke="#55557a" stroke-width="2.5"/><circle cx="64" cy="14" r="4" fill="#a6e3a1"/><rect x="40" y="88" width="48" height="24" rx="8" fill="#35354a" stroke="#55557a" stroke-width="2"/><rect x="46" y="94" width="36" height="16" rx="3" fill="#1e1e2e" stroke="#45475a" stroke-width="1"/><rect x="20" y="84" width="20" height="8" rx="4" fill="#35354a" stroke="#55557a"/><rect x="88" y="84" width="20" height="8" rx="4" fill="#35354a" stroke="#55557a"/></svg></div>
      <h3 class="text-base font-medium text-[var(--color-ide-text)] mb-1">Hi Buddy</h3><p class="text-xs text-[var(--color-ide-text-dim)] mb-4">Waiting for work...</p>
      <div class="w-full space-y-1.5">
        <button v-for="cmd in ['显示所有命令','快速打开文件','打开设置']" :key="cmd" class="w-full flex items-center gap-2 px-3 py-1.5 rounded bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] text-[11px] text-[var(--color-ide-text)] hover:border-[var(--color-ide-border-focus)]"><span>{{ cmd }}</span><kbd class="ml-auto">{{ cmd==='显示全部命令'?'Ctrl+Shift+P':'快速打开文件'===cmd?'Ctrl+P':'Ctrl+,' }}</kbd></button>
      </div>
    </div>

    <!-- Messages -->
    <div v-else ref="mc" class="flex-1 overflow-y-auto p-3 space-y-3">
      <template v-for="(msg,idx) in messages" :key="idx">
        <div v-if="!(idx===0&&msg.role==='assistant'&&!msg.content)">
          <div v-if="msg.role==='user'" class="flex gap-2 items-start">
            <div class="w-6 h-6 rounded-full bg-blue-600 flex items-center justify-center shrink-0 mt-0.5"><User :size="13" class="text-white"/></div>
            <div class="flex-1 min-w-0"><div class="text-[11px] text-[var(--color-ide-text-dim)] mb-1">用户</div><div class="text-[12px] text-[var(--color-ide-text)] whitespace-pre-wrap break-words leading-relaxed">{{ msg.content }}</div></div>
          </div>
          <div v-else-if="msg.role==='assistant'" class="flex gap-2 items-start">
            <div class="w-6 h-6 rounded-full bg-emerald-600 flex items-center justify-center shrink-0 mt-0.5"><Bot :size="13" class="text-white"/></div>
            <div class="flex-1 min-w-0">
              <div class="text-[11px] text-[var(--color-ide-text-dim)] mb-1 flex items-center gap-1"><Sparkles :size="10"/> 深度思考</div>
              <div class="text-[12px] text-[var(--color-ide-text)] whitespace-pre-wrap break-words leading-relaxed prose prose-invert prose-sm max-w-none" v-html="renderMD(msg.content)" />
              <span v-if="isLoading&&!msg.content" class="inline-flex items-center gap-1 text-[var(--color-ide-text-dim)]"><RefreshCw :size="11" class="animate-spin"/> 思考中...</span>
              <div v-if="msg.toolCalls?.length" class="mt-2 space-y-1">
                <div v-for="(tc,ti) in msg.toolCalls" :key="ti" class="flex items-center gap-1.5 text-[11px] bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded px-2 py-1"><span class="w-4 h-4 rounded bg-blue-600/20 text-blue-400 flex items-center justify-center text-[10px]">⊕</span><span>{{ tc.name }}</span><span v-if="tc.result" class="ml-auto text-green-400 text-[10px]">{{ tc.result }}</span></div>
              </div>
              <div v-if="msg.content&&idx===messages.length-1" class="mt-2 flex items-center gap-1"><button class="p-1 rounded hover:bg-white/5 text-[var(--color-ide-text-dim)]"><Copy :size="12/></button><button class="p-1 rounded hover:bg-white/5 text-[var(--color-ide-text-dim)]"><ThumbsUp :size="12/></button><button class="p-1 rounded hover:bg-white/5 text-[var(--color-ide-text-dim)]"><ThumbsDown :size="12/></button></div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Input -->
    <div class="shrink-0 border-t border-[var(--color-ide-border)] p-2">
      <div class="flex items-end gap-2 bg-[var(--color-ide-surface)] border border-[var(--color-ide-border)] rounded-lg px-3 py-2 focus-within:border-[var(--color-ide-border-focus)] transition-colors">
        <textarea v-model="inputText" rows="1" placeholder="输入消息..." class="flex-1 bg-transparent outline-none resize-none text-[12px] text-[var(--color-ide-text)] placeholder-[var(--color-ide-text-dim)] max-h-[120px]" style="min-height:24px;" @keydown.enter.exact.prevent="sendMessage" @input="$event.target.style.height='auto';$event.target.style.height=Math.min($event.target.scrollHeight,120)+'px'"/>
        <button class="p-1.5 rounded-md bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 transition-colors shrink-0" :disabled="!inputText.trim()&&!isLoading" @click="sendMessage"><Send :size="14" class="text-white"/></button>
      </div>
      <div class="mt-1 text-[10px] text-[var(--color-ide-text-dim)] text-center">内容由 AI 生成 · 仅供参考</div>
    </div>
  </div>
</template>

<script lang="ts">
function renderMD(t:string):string{return t.replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>').replace(/`([^`]+)`/g,'<code class="bg-black/30 px-1 rounded text-[11px]">$1</code>').replace(/^### (.+)$/gm,'<h4>$1</h4>').replace(/^## (.+)$/gm,'<h3>$1</h3>').replace(/^• (.+)$/gm,'<li>$1</li>')}
export{renderMD}
</script>
