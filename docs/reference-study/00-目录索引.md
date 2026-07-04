# AI IDE 参考项目学习指南（总索引）

> **源码位置**: `D:\code\` | 共 18 个参考项目 | 总计 ~1.2 GB  
> **最后更新**: 2026-06-30  
> **使用方法**: 按层级顺序逐个阅读，每个文档包含：架构概览、核心模块、关键源码入口、可借鉴设计点

---

## 学习路径建议

```
┌─────────────────────────────────────────────────────┐
│  第一步：AI UI 组件层（最直接相关，前端重点）         │
│    03-Continue.md → 09-Cline.md → 10-RooCode.md     │
│    11-OpenInterpreter.md                            │
├─────────────────────────────────────────────────────┤
│  第二步：编辑器 UI 层                                │
│    07-VSCode.md → 05-Zed.md → 08-MonacoEditor.md   │
│    06-CodeEdit.md                                   │
├─────────────────────────────────────────────────────┤
│  第三步：Agent / Workflow 层                        │
│    12-LangGraph.md → 13-AutoGen.md → 14-CrewAI.md  │
│    02-Aider.md → 04-OpenHands.md                   │
│    18-SWE-agent.md                                 │
├─────────────────────────────────────────────────────┤
│  第四步：MCP / Runtime 层                           │
│    15-MCPSpec.md → 16-MCPServers.md                │
│    17-Tabby.md → 19-HermesStudio.md               │
└─────────────────────────────────────────────────────┘
```

---

## 项目清单

### Layer 1: AI IDE 核心标准

| # | 文档 | 项目 | 大小 | 标签 |
|---|------|------|------|------|
| 1 | [01-Continue](./01-Continue.md) | Continue (VS Code AI 扩展) | 271 MB | `RAG` `Context` `ModelRouter` `ChatUI` |
| 2 | [02-Aider](./02-Aider.md) | Aider (Git-aware Agent CLI) | 74 MB | `Diff` `Git` `AgentLoop` `MultiFile` |
| 3 | [03-OpenHands](./03-OpenHands.md) | OpenHands (AI SE Robot) | 18 MB | `Sandbox` `Browser` `Workflow` |
| 4 | [18-SWE-agent](./18-SWE-agent.md) | SWE-agent (Issue→Fix 循环) | 34 MB | `Evaluation` `Feedback` `Patch` |

### Layer 2: IDE UI / 编辑器系统

| # | 文档 | 项目 | 大小 | 标签 |
|---|------|------|------|------|
| 5 | [05-Zed](./05-Zed.md) | Zed (高性能编辑器, Rust) | 75 MB | `GPUI` `Layout` `Collab` `MultiPanel` |
| 6 | [06-CodeEdit](./06-CodeEdit.md) | CodeEdit (现代 IDE 框架) | 11 MB | `Navigator` `Settings` `SwiftUI` |
| 7 | [07-VSCode](./07-VSCode.md) | VS Code (IDE 祖师爷) | 220 MB | `Workbench` `ExtensionHost` `EditorGroup` |
| 8 | [08-MonacoEditor](./08-MonacoEditor.md) | Monaco Editor (编辑器核心) | 21 MB | `DiffEditor` `InlineEdit` `Highlight` |

### Layer 3: AI UI / Agent IDE 组件

| # | 文档 | 项目 | 大小 | 标签 |
|---|------|------|------|------|
| 9 | [09-Cline](./09-Cline.md) | Cline (Cursor 风格 Agent UI) | 58 MB | `ReasoningSteps` `ToolCalls` `DiffPreview` |
| 10 | [10-RooCode](./10-RooCode.md) | Roo Code (AI Coding UI) | 293 MB | `ToolPanel` `ExecutionTrace` `AutoApproval` |
| 11 | [11-OpenInterpreter](./11-OpenInterpreter.md) | Open Interpreter (可执行 Agent) | 52 MB | `CommandExec` `Streaming` `ToolResult` |

### Layer 4: Workflow / Multi-Agent

| # | 文档 | 项目 | 大小 | 标签 |
|---|------|------|------|------|
| 12 | [12-LangGraph](./12-LangGraph.md) | LangGraph (有状态工作流引擎) | 13 MB | `StateGraph` `Checkpointing` `Routing` |
| 13 | [13-AutoGen](./13-AutoGen.md) | AutoGen (微软多 Agent) | — | `MultiChat` `RoleSystem` `ToolCalling` |
| 14 | [14-CrewAI](./14-CrewAI.md) | CrewAI (轻量任务编排) | — | `RoleAgent` `TaskPipeline` `Tools` |

### Layer 5: MCP / Tool System

| # | 文档 | 项目 | 大小 | 标签 |
|---|------|------|------|------|
| 15 | [15-MCPSpec](./15-MCPSpec.md) | MCP 协议规范 | 39 MB | `Protocol` `SDK` `Transport` |
| 16 | [16-MCPServers](./16-MCPServers.md) | MCP 官方服务器集 | 1.4 MB | `FileSystem` `Git` `Postgres` `Browser` |

### Layer 6: AI IDE Runtime / Backend

| # | 文档 | 项目 | 大小 | 标签 |
|---|------|------|------|------|
| 17 | [17-Tabby](./17-Tabby.md) | Tabby (本地代码补全) | 29 MB | `Embeddings` `Completion` `Self-host` |
| 19 | [19-HermesStudio](./19-HermesStudio.md) | Hermes Studio (全功能平台) | — | `FullStack` `MCP` `Skills` `Device` |

---

## 本项目对应关系速查

```
你的需求                     →  参考哪个项目           →  对应文件
───────────────────────────────────────────────────────────────────
@-mention 文件引用            →  Continue              →  core/context/
推理步骤展示                 →  Cline + Roo Code       →  apps/vscode/ + src/core/
多 Agent 流水线可视化         →  LangGraph             →  libs/langgraph/
上下文管理面板               →  Continue              →  core/context/ + gui/
工具审批栏                   →  Open Interpreter      →  codex-rs/ (Rust)
执行仪表盘                   →  Roo Code              →  src/core/task/
Diff Preview 内联对比        →  Aider                 →  aider/diffs.py
Monaco 编辑器集成            →  Monaco Editor         →  monaco-editor/src/
MCP 工具系统                 →  MCP Spec + Servers    →  schema/ + src/
Sandbox 安全执行             →  OpenHands             →  app_server/sandbox/
多 Agent 编排                →  LangGraph/AutoGen     →  libs/langgraph/ + autogen/
高性能 UI 渲染               →  Zed (GPUI)           →  crates/gpui/
```
