# AI IDE 参考项目清单（完整版 18 项目）

> 用于 AI Fullstack Platform 客户端（Vue + Tauri AI IDE Shell）开发参考  
> 所有源码已下载至 `D:\code`  
> 最后更新：2026-06-30

---

## Layer 1: AI IDE 核心标准

| # | 项目 | 路径 | 大小 | 描述 | 参考方向 |
|---|------|------|------|------|----------|
| 1 | **Continue** | `D:\code\continue` | 271 MB | VS Code AI 扩展 | Chat + Inline Edit、RAG/Context、Model Routing |
| 2 | **Aider** | `D:\code\aider` | 74 MB | Git-aware CLI Agent | 自动 git diff patch、多文件编辑、repo context |
| 3 | **OpenHands** | `D:\code\openhands` | 18 MB | AI 软件工程机器人 (原 OpenDevin) | Sandbox 执行环境、浏览器自动化、多 step workflow |
| 4 | **SWE-agent** | `D:\code\swe-agent` | 34 MB | 学术级 Issue→Fix 循环 | Environment feedback、evaluation system |

---

## Layer 2: IDE UI / 编辑器系统

| # | 项目 | 路径 | 大小 | 描述 | 参考方向 |
|---|------|------|------|------|----------|
| 5 | **VS Code** | `D:\code\vscode` | 220 MB | 微软开源编辑器 | Workbench 架构、Editor Group、Terminal、Extension Host |
| 6 | **Zed** | `D:\code\zed` | 75 MB | 高性能协作编辑器 (Rust) | UI Layout Engine、Buffer Rendering、Multi Panel |
| 7 | **CodeEdit** | `D:\code\codeedit` | 11 MB | 现代 IDE 框架 (Swift) | Project Navigator、Editor Tab 管理、Settings 架构 |
| 8 | **Monaco Editor** | `D:\code\monaco-editor` | 21 MB | VS Code 编辑器核心 | Diff Editor、Inline Edit、Code Highlight |

---

## Layer 3: AI UI / Agent IDE 组件

| # | 项目 | 路径 | 大小 | 描述 | 参考方向 |
|---|------|------|------|------|----------|
| 9 | **Cline** | `D:\code\cline` | 58 MB | Cursor 风格 Agent UI | Step-by-step output、Tool Calls UI、Diff Preview、Execution Trace |
| 10 | **Roo Code** | `D:\code\roocode` | 293 MB | AI Coding UI | Tool Execution Panel、Reasoning Steps UI、Diff Preview |
| 11 | **Open Interpreter** | `D:\code\open-interpreter` | 52 MB | 可执行 Agent UI (Rust+TS) | System Command Execution、Streaming Output、Tool Result |

---

## Layer 4: Workflow / Multi-Agent 编排

| # | 项目 | 路径 | 大小 | 描述 | 参考方向 |
|---|------|------|------|------|----------|
| 12 | **LangGraph** | `D:\code\langgraph` | 13 MB | LangChain 有状态多 Agent 框架 | Graph Workflow、State Machine Agent、Multi-Agent Routing |
| 13 | **AutoGen** | `D:\code\autogen` | — | 微软多 Agent 对话框架 | Multi-Agent Chat、Role System、Tool Calling |
| 14 | **CrewAI** | `D:\code\crewAI` | — | 轻量 Multi-Agent 编排 | Role-Based Agent、Task Pipeline、Tool System |

---

## Layer 5: MCP / Tool System

| # | 项目 | 路径 | 大小 | 描述 | 参考方向 |
|---|------|------|------|------|----------|
| 15 | **MCP Spec** | `D:\code\mcp-spec` | 39 MB | Anthropic MCP 协议规范 | MCP Server SDK、协议定义、传输层 |
| 16 | **MCP Servers** | `D:\code\mcp-servers` | 1.4 MB | 官方 MCP 服务器集合 | Filesystem、Git、Postgres、Browser Tools |

---

## Layer 6: AI IDE Runtime / Backend

| # | 项目 | 路径 | 大小 | 描述 | 参考方向 |
|---|------|------|------|------|----------|
| 17 | **Tabby** | `D:\code\tabby` | 29 MB | 本地代码补全系统 (Rust) | Embeddings、Completion Model、Self-host |
| 18 | **Hermes Studio** | `D:\code\hermes-studio` | — | AI Studio 全功能平台 | 登录/聊天/历史/记忆/技能/MCP/设备管理 |

---

## 技术栈映射（本项目）

```
参考层              │  本项目对应模块
────────────────────┼─────────────────────────────
Layer 1 核心标准    │  backend/app/core/agent/
                    │  studio-client/src/pages/AgentChat.vue
                    │
Layer 2 编辑器 UI   │  studio-client/src/components/editor/
                    │  Monaco Editor 集成
                    │
Layer 3 Agent UI    │  AgentReasoningSteps.vue（参考 Cline）
                    │  AgentRunDashboard.vue（参考 Roo Code）
                    │  AgentChat.vue（参考 Open Interpreter）
                    │
Layer 4 Workflow    │  AgentPipeline.vue（参考 LangGraph/AutoGen）
                    │  backend/app/core/agent/orchestrator.py
                    │  agent_modes.py（8 modes × skills）
                    │
Layer 5 MCP/Tool    │  backend/app/core/mcp/
                    │  backend/app/core/tools/
                    │  ContextPanel.vue（参考 Continue RAG）
                    │
Layer 6 Runtime     │  backend/app/core/model_router.py
                    │  backend/app/core/api_gateway.py
                    │  backend/app/core/fallback_chain.py
                    │  backend/app/core/tools/autocli.py
```

---

## 客户端已实现对照

| 特性 | 参考项目 | 实现文件 |
|------|----------|----------|
| @-mention 文件引用 | Continue | `pages/AgentChat.vue` |
| 推理步骤展示 | Cline / Roo Code | `components/agent/AgentReasoningSteps.vue` |
| 多 Agent 管线可视化 | LangGraph / AutoGen | `components/agent/AgentPipeline.vue` |
| 上下文管理面板 | Continue | `components/agent/ContextPanel.vue` |
| 执行仪表盘 | OpenInterpreter / Roo Code | `components/agent/AgentRunDashboard.vue` |
| 工具审批栏 | OpenInterpreter | `pages/AgentChat.vue` |
| 模式选择器 (8 modes) | 后端 agent_modes | `pages/AgentChat.vue` + `types/studio.ts` |
| SSE 事件 15 种类型 | Continue / OpenHands | `types/studio.ts` |

---

## 待研究特性

- [ ] **Inline Diff Preview**（Aider 风格）— 在编辑器中直接预览 AI 修改
- [ ] **Monaco Editor 深度集成** — 智能补全、诊断、悬浮提示
- [ ] **File Tree 右键菜单** — "添加到对话上下文" 快捷操作
- [ ] **VS Code / JetBrains 插件化** — 扩展市场发布
- [ ] **协作编辑**（Zed 风格）— 多人实时协作 + AI 辅助
- [ ] **WebAssembly Sandbox** — 浏览器端安全代码执行
- [ ] **MCP 市场集成** — 一键安装社区 MCP 服务器
- [ ] **Sandbox 执行环境**（OpenHands 风格）— 安全隔离的代码运行
- [ ] **Hermes Studio 全功能** — 登录/群聊/看板/用量/日志/设备管理

---

## 关键源码入口速查

### Continue (`D:\code\continue`)
- 前端核心: `core/frontend/src/`
- Context 系统: `core/shared/context/`
- RAG/Embedding: `core/server/embeddings/`
- Model Router: `core/shared/models/`

### Cline (`D:\code\cline`)
- Agent 核心: `src/core/`
- UI 组件: `src/integrations/vscode/extension/ui/`
- Tool 调用: `src/tools/`

### Roo Code (`D:\code\roocode`)
- Agent 引擎: `src/agent/`
- UI 组件: `src/ui/`
- 工具系统: `src/tool/`

### Zed (`D:\code\zed`)
- 编辑器: `crates/editor/src/`
- UI Layout: `crates/ui/src/`
- 终端: `crates/terminal/src/`

### OpenHands (`D:\code\openhands`)
- Agent 核心: `openhands/core/`
- Sandbox: `openhands/runtime/`
- 评测: `openhands/evaluation/`

### Aider (`D:\code\aider`)
- Agent Loop: `aider/main_loop.py`
- Diff Engine: `aider/diff.py`
- Repo Context: `aider/repo.py`
