# Hermes Studio — 全功能 AI 平台（参考蓝图）

> **源码位置**: `D:\code\hermes-studio` | **语言**: TypeScript + Vue 3  
> **定位**: 类似 ChatGPT 全功能平台但开源自托管，含登录/聊天/记忆/技能/MCP/设备管理

---

## 一、项目概览

Hermes Studio 是一个 **全功能的 AI 平台前端**，其功能列表非常全面：

✅ 用户系统（注册/登录/OAuth）
💬 聊天界面（Markdown 渲染、代码高亮、流式输出）
📚 历史记录（会话管理、搜索）
🧠 记忆系统（长期/短期记忆）
🛠️ 技能系统（自定义 Prompt/Skill）
🔌 MCP 集成
📱 设备管理
👥 群聊功能
📊 用量统计
📋 看板视图
📝 日志查看
⚙️ 平台集成设置
🔄 备份与恢复
🔒 安全策略

### 为什么重要？
这是最接近我们要构建的 **完整产品形态**的开源项目。它的 Vue 3 + TypeScript 技术栈也与我们一致！

---

## 二、目录结构

```
D:\code\hermes-studio\
├── packages/
│   ├── main-app/               # ★★★ 主应用包 ⭐⭐⭐
│   │   ├── src/
│   │   │   ├── views/          #    页面路由组件
│   │   │   │   ├── Login.vue        登录
│   │   │   │   ├── Chat.vue         聊天主页 ⭐⭐⭐
│   │   │   │   ├── History.vue      历史记录
│   │   │   │   ├── Memory.vue       记忆管理
│   │   │   │   ├── Skills.vue       技能管理
│   │   │   │   ├── Settings.vue     设置
│   │   │   │   ├── Devices.vue      设备管理
│   │   │   │   ├── Groups.vue       群聊
│   │   │   │   ├── Dashboard.vue    看板/仪表盘
│   │   │   │   ├── Usage.vue        用量统计
│   │   │   │   └── Logs.vue         日志
│   │   │   ├── components/     #    共享组件
│   │   │   │   ├── chat/         #    聊天相关组件
│   │   │   │   │   ├── MessageList.vue    消息列表
│   │   │   │   │   ├── InputArea.vue      输入区域
│   │   │   │   │   ├── MarkdownRenderer.vue Markdown 渲染
│   │   │   │   │   └── CodeBlock.vue       代码块
│   │   │   │   ├── memory/       #    记忆组件
│   │   │   │   ├── mcp/          #    MCP 组件
│   │   │   │   └── common/       #    通用组件
│   │   │   ├── stores/          #    Pinia 状态管理
│   │   │   │   ├── auth.ts       #    认证状态
│   │   │   │   ├── chat.ts       #    聊天状态
│   │   │   │   ├── memory.ts     #    记忆状态
│   │   │   │   ├── settings.ts   #    设置状态
│   │   │   │   └── devices.ts    #    设备状态
│   │   │   ├── composables/     #    组合式函数
│   │   │   ├── api/             #    API 封装
│   │   │   ├── types/           #    TypeScript 类型
│   │   │   └── router/          #    Vue Router 配置
│   │   └── ...
│   └── ...
├── docs/                        # 详细文档（122 页 MD）
├── tests/                       # 测试套件（269 个测试文件）
├── ARCHITECTURE.md              # 架构设计文档 ⭐
└── docker-compose.yml           # Docker 编排
```

---

## 三、核心架构（从 ARCHITECTURE.md）

```
Hermes Studio Architecture:
┌─────────────────────────────────────────────────────┐
│                    Frontend (Vue 3)                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────┐  │
│  │ Views     │  │ Components│  │ Stores (Pinia)    │  │
│  │ (Pages)   │→ │ (Reusable)│← │ (State Mgmt)     │  │
│  └──────────┘  └──────────┘  └────────┬─────────┘  │
│                                      │              │
└──────────────────────────────────────┼──────────────┘
                                       │ API Calls
┌──────────────────────────────────────┼──────────────┐
│                              Backend (FastAPI)       │
│  ┌──────────┐  ┌──────────┐  ┌───────▼─────────┐  │
│  │ Auth     │  │ Chat     │  │ Memory Store     │  │
│  │ Module   │  │ Module   │  │ (SQLite/PG)      │  │
│  └──────────┘  └──────────┘  ├────────┬─────────┤  │
│                                  │ MCP     │ Skills  │  │
│                                  └─────────┴────────┘  │
└──────────────────────────────────────────────────────┘
```

### 3.1 功能模块对照表

| Hermes Studio 模块 | 功能描述 | 我们的项目对应 |
|-------------------|---------|---------------|
| Auth | 登录/注册/JWT/OAuth | 待实现 |
| Chat | 聊天/流式/Markdown/代码 | ✅ AgentChat.vue |
| History | 会话列表/搜索/导出 | 部分（trajectory API） |
| Memory | 长期/短期记忆 CRUD | ✅ MemoryStore + MemoryRetriever |
| Skills | 自定义 Skill 管理 | ✅ SkillManager |
| MCP | MCP Server 连接/管理 | ✅ MCPClient + MCPManager |
| Devices | 多设备同步 | 未实现 |
| Groups | 多人群组/共享会话 | 未实现 |
| Dashboard | 统计看板 | ✅ AgentRunDashboard (基础版) |
| Usage | Token/费用统计 | ✅ usage event |
| Logs | 操作日志审计 | trajectory API (基础版) |

---

## 四、值得借鉴的设计

### 🏆 #1 完整的页面路由体系
- 从 `views/` 目录可以看到完整的产品页面规划
- **落地**: studio-client 可以逐步扩展这些页面

### 🏆 #2 Pinia 状态管理分层
- auth/chat/memory/settings/devices 各自独立 store
- **落地**: 我们的 store 结构可以参考此组织

### 🏆 #3 记忆系统 UI（Memory.vue）
- 可视化的记忆 CRUD + 搜索 + 分类
- **落地**: ContextPanel.vue 可以扩展为完整的记忆面板

### 🏆 #4 MCP 管理界面
- 添加/删除/启停 MCP Server 的 UI
- **落地**: studio-client 的 MCP 设置页面

### 🏆 #5 269 个单元测试
- 非常完善的测试覆盖
- **启示**: 我们的 client 侧也需要增加测试

---

## 五、快速入门

```bash
cd D:\code\hermes-studio
npm install
npm run dev

# 查看 API
cat docs/api/*.md

# 查看架构
cat ARCHITECTURE.md
```
