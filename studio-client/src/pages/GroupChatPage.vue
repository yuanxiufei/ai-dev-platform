<template>
  <div class="group-chat-page">
    <div class="chat-layout">
      <!-- Sidebar: Room List -->
      <div class="room-sidebar">
        <div class="sidebar-header">
          <h3>群聊</h3>
          <button class="btn-icon" @click="showCreateRoom = true" title="创建房间">+</button>
        </div>
        <div class="room-list">
          <button
            v-for="room in rooms"
            :key="room.id"
            class="room-item"
            :class="{ active: activeRoom === room.id }"
            @click="activeRoom = room.id"
          >
            <div class="room-icon">{{ room.icon }}</div>
            <div class="room-info">
              <div class="room-name">{{ room.name }}</div>
              <div class="room-meta">{{ room.members.length }} 成员 · {{ room.messages.length }} 消息</div>
            </div>
          </button>
        </div>
      </div>

      <!-- Main Chat Area -->
      <div class="chat-main" v-if="currentRoom">
        <div class="chat-header">
          <span class="room-title">{{ currentRoom.icon }} {{ currentRoom.name }}</span>
          <div class="member-avatars">
            <span v-for="m in currentRoom.members" :key="m" class="avatar-dot" :style="{ background: agentColor(m) }" :title="m">{{ m[0] }}</span>
          </div>
        </div>
        <div class="chat-messages" ref="msgContainer">
          <div v-for="msg in currentRoom.messages" :key="msg.id" class="message" :class="{ 'is-agent': msg.role === 'agent' }">
            <div class="msg-avatar" :style="{ background: agentColor(msg.sender) }">{{ msg.sender[0] }}</div>
            <div class="msg-body">
              <div class="msg-sender">{{ msg.sender }} <span class="msg-time">{{ msg.time }}</span></div>
              <div class="msg-text">{{ msg.text }}</div>
            </div>
          </div>
        </div>
        <div class="chat-input-area">
          <div class="input-row">
            <select v-model="sendAs" class="agent-select">
              <option value="">以用户身份</option>
              <option v-for="m in currentRoom.members" :key="m" :value="m">{{ m }}</option>
            </select>
            <input
              v-model="newMessage"
              class="chat-input"
              placeholder="输入消息... (Enter 发送)"
              @keydown.enter="sendMessage"
            />
            <button class="btn btn-primary" @click="sendMessage" :disabled="!newMessage.trim()">发送</button>
          </div>
        </div>
      </div>

      <!-- Empty State -->
      <div v-else class="chat-empty">
        <div class="empty-icon">💬</div>
        <p>选择一个群聊房间开始对话</p>
      </div>
    </div>

    <!-- Create Room Modal -->
    <Teleport to="body">
      <div v-if="showCreateRoom" class="modal-overlay" @click.self="showCreateRoom = false">
        <div class="modal-card">
          <h3>创建群聊房间</h3>
          <form @submit.prevent="createRoom">
            <div class="field">
              <label>房间名称</label>
              <input v-model="newRoomName" class="input" placeholder="例如：代码评审小组" />
            </div>
            <div class="field">
              <label>Agent 成员（逗号分隔）</label>
              <input v-model="newRoomMembers" class="input" placeholder="Planner, Coder, Reviewer" />
            </div>
            <div class="modal-actions">
              <button type="button" class="btn btn-ghost" @click="showCreateRoom = false">取消</button>
              <button type="submit" class="btn btn-primary">创建</button>
            </div>
          </form>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'

interface ChatMessage {
  id: string
  sender: string
  role: 'user' | 'agent'
  text: string
  time: string
}

interface ChatRoom {
  id: string
  name: string
  icon: string
  members: string[]
  messages: ChatMessage[]
}

const colors = ['#3794FF', '#C586C0', '#4EC9B0', '#DCDCAA', '#CE9178', '#569CD6', '#F48771', '#B5CEA8']

function agentColor(name: string): string {
  let hash = 0
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash)
  return colors[Math.abs(hash) % colors.length]
}

const rooms = ref<ChatRoom[]>([
  {
    id: '1', name: '代码评审小组', icon: '🔍',
    members: ['Planner', 'Coder', 'Reviewer'],
    messages: [
      { id: '1', sender: 'Planner', role: 'agent', text: '收到新的代码评审请求，让我先分析一下项目结构。', time: '14:30' },
      { id: '2', sender: 'Coder', role: 'agent', text: '已读取 app/main.py，发现 3 处潜在的性能问题。', time: '14:31' },
      { id: '3', sender: 'Reviewer', role: 'agent', text: '建议将第 156 行的循环改为列表推导式，预计性能提升 40%。', time: '14:32' },
      { id: '4', sender: '用户', role: 'user', text: '好的，请直接应用这些优化。', time: '14:33' },
    ],
  },
  {
    id: '2', name: '前端开发协作', icon: '🎨',
    members: ['Designer', 'Frontend', 'Backend'],
    messages: [
      { id: '1', sender: 'Designer', role: 'agent', text: '新的 UI 设计稿已生成，位于 designs/v2。', time: '10:00' },
      { id: '2', sender: 'Frontend', role: 'agent', text: '收到，正在将设计稿转换为 Vue 组件。', time: '10:02' },
    ],
  },
  {
    id: '3', name: '部署运维小组', icon: '🚀',
    members: ['DevOps', 'Monitor', 'Security'],
    messages: [],
  },
])

const activeRoom = ref('1')
const newMessage = ref('')
const sendAs = ref('')
const msgContainer = ref<HTMLElement | null>(null)
const showCreateRoom = ref(false)
const newRoomName = ref('')
const newRoomMembers = ref('')

const currentRoom = computed(() => rooms.value.find(r => r.id === activeRoom.value) || null)

function sendMessage() {
  if (!newMessage.value.trim() || !currentRoom.value) return
  const sender = sendAs.value || '用户'
  const role = sendAs.value ? 'agent' : 'user'
  currentRoom.value.messages.push({
    id: Date.now().toString(),
    sender,
    role,
    text: newMessage.value.trim(),
    time: new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' }),
  })
  newMessage.value = ''
  sendAs.value = ''
  nextTick(() => {
    if (msgContainer.value) msgContainer.value.scrollTop = msgContainer.value.scrollHeight
  })
}

function createRoom() {
  if (!newRoomName.value.trim()) return
  const members = newRoomMembers.value.split(',').map(m => m.trim()).filter(Boolean)
  rooms.value.push({
    id: Date.now().toString(),
    name: newRoomName.value.trim(),
    icon: '💬',
    members: members.length ? members : ['Agent A', 'Agent B'],
    messages: [],
  })
  showCreateRoom.value = false
  newRoomName.value = ''
  newRoomMembers.value = ''
}
</script>

<style scoped>
.group-chat-page {
  height: 100%;
  background: var(--color-ide-bg);
  color: var(--color-ide-text);
}
.chat-layout {
  height: 100%;
  display: flex;
}
/* Sidebar */
.room-sidebar {
  width: 220px;
  flex-shrink: 0;
  background: var(--color-ide-bg-secondary);
  border-right: 1px solid var(--color-ide-border);
  display: flex;
  flex-direction: column;
}
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--color-ide-border);
}
.sidebar-header h3 { font-size: 13px; font-weight: 600; }
.btn-icon {
  width: 24px; height: 24px; font-size: 16px;
  background: transparent; border: 1px solid var(--color-ide-border);
  border-radius: 4px; color: var(--color-ide-text-dim); cursor: pointer;
  display: flex; align-items: center; justify-content: center;
}
.btn-icon:hover { background: var(--color-ide-surface-hover); }
.room-list { flex: 1; overflow-y: auto; padding: 4px 0; }
.room-item {
  display: flex; align-items: center; gap: 10px; padding: 10px 14px;
  width: 100%; border: none; background: transparent; cursor: pointer;
  text-align: left; color: var(--color-ide-text);
}
.room-item:hover { background: var(--color-ide-surface-hover); }
.room-item.active { background: var(--color-ide-surface-active); }
.room-icon { font-size: 18px; }
.room-name { font-size: 12.5px; font-weight: 600; }
.room-meta { font-size: 10.5px; color: var(--color-ide-text-dim); margin-top: 2px; }
/* Chat main */
.chat-main {
  flex: 1; display: flex; flex-direction: column; min-width: 0;
}
.chat-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 16px;
  background: var(--color-ide-bg-secondary);
  border-bottom: 1px solid var(--color-ide-border);
}
.room-title { font-size: 14px; font-weight: 600; }
.member-avatars { display: flex; gap: 4px; }
.avatar-dot {
  width: 24px; height: 24px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; color: #fff;
}
.chat-messages { flex: 1; overflow-y: auto; padding: 16px; }
.message {
  display: flex; gap: 10px; margin-bottom: 16px;
}
.message.is-agent { }
.msg-avatar {
  width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; font-weight: 700; color: #fff; flex-shrink: 0;
}
.msg-sender { font-size: 12px; font-weight: 600; margin-bottom: 4px; }
.msg-time { font-size: 10px; color: var(--color-ide-text-dim); font-weight: 400; margin-left: 8px; }
.msg-text { font-size: 13px; line-height: 1.5; color: var(--color-ide-text); }
.chat-input-area {
  padding: 10px 16px;
  border-top: 1px solid var(--color-ide-border);
}
.input-row { display: flex; gap: 8px; align-items: center; }
.agent-select {
  width: 120px; padding: 6px 8px; font-size: 12px;
  background: var(--color-chat-input-bg); border: 1px solid var(--color-ide-border);
  border-radius: 3px; color: var(--color-ide-text); outline: none;
}
.chat-input {
  flex: 1; padding: 7px 12px; font-size: 13px;
  background: var(--color-chat-input-bg); border: 1px solid var(--color-ide-border);
  border-radius: 3px; color: var(--color-ide-text); outline: none;
}
.chat-input:focus { border-color: var(--color-ide-border-focus); }
.chat-empty {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; color: var(--color-ide-text-dim);
}
.empty-icon { font-size: 48px; margin-bottom: 12px; }
/* Modal */
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(0,0,0,0.5); display: flex;
  align-items: center; justify-content: center; z-index: 300;
}
.modal-card {
  background: var(--color-ide-surface); border: 1px solid var(--color-ide-border);
  border-radius: 6px; width: 400px; max-width: 90vw; padding: 24px;
  box-shadow: var(--shadow-lg);
}
.modal-card h3 { font-size: 16px; color: var(--color-ide-text); margin-bottom: 20px; }
.field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 14px; }
.field label { font-size: 12px; color: var(--color-ide-text-dim); }
.input {
  padding: 8px 12px; font-size: 13px;
  background: var(--color-chat-input-bg); border: 1px solid var(--color-ide-border);
  border-radius: 3px; color: var(--color-ide-text); outline: none;
}
.input:focus { border-color: var(--color-ide-border-focus); }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
.btn {
  padding: 6px 16px; font-size: 12px; border-radius: 3px;
  border: none; cursor: pointer; font-weight: 600;
}
.btn-primary { background: var(--color-ide-accent); color: #fff; }
.btn-primary:hover { background: var(--color-ide-accent-hover); }
.btn-primary:disabled { opacity: 0.4; }
.btn-ghost { background: transparent; color: var(--color-ide-text); }
.btn-ghost:hover { background: rgba(255,255,255,0.06); }
</style>
