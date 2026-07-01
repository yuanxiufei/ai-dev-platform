# Cline — Cursor 风格 Agent UI

> **源码位置**: `D:\code\cline` | **大小**: 58 MB | **语言**: TypeScript (Monorepo)  
> **官网**: https://cline.ai | **Stars**: ~40k+  
> **定位**: VS Code AI 编程插件，以精美的 Agent UI 和推理步骤展示著称

---

## 一、项目概览

Cline 是当前 **最流行的开源 AI 编程助手之一**，其 UI 设计质量在所有同类项目中首屈一指。特别是：

- 🧠 **推理步骤可视化** — 展示 AI 的思考过程（thinking/planning/analysis）
- 🔧 **工具调用 UI** — 精美的 tool use/result 展示
- 📝 **Diff Preview** — 行内代码变更预览
- 🔄 **Execution Trace** — 完整的任务执行追踪
- 💬 **多轮对话** — 保留完整上下文的历史对话

### 技术栈
```
框架: Monorepo (Turborepo)
前端: React + TypeScript + TailwindCSS
UI: Radix UI + Lucide Icons
构建: Vite + esbuild
测试: Vitest + Playwright
SDK: 独立的 SDK 包（可脱离 VS Code 使用）
```

---

## 二、目录结构

```
D:\code\cline/
├── apps/
│   ├── vscode/                  # ★★★ VS Code 扩展（主要产品）
│   │   ├── src/                 #    扩展源码
│   │   │   ├── integrations/    #    VS Code 集成
│   │   │   │   └── vscode/      #    VS Code API 封装
│   │   │   └── extension-ui/    #    WebView UI ⭐⭐⭐
│   │   │       ├── components/  #    所有 UI 组件
│   │   │       │   ├── chat/   #    聊天界面（核心！）
│   │   │       │   ├── agent/  #    Agent 相关 UI
│   │   │       │   └── tools/  #    工具调用组件
│   │   │       └── utils/      #    工具函数
│   │   └── package.json
│   ├── cli/                     # CLI 版本（独立运行）
│   ├── cline-hub/               # Cline Hub（分享平台 UI）
│   └── examples/                # 示例项目
├── sdk/                         # ★★ 核心 SDK（Agent 引擎）
│   ├── src/
│   │   ├── agent/               #    Agent 循环 ⭐⭐⭐
│   │   ├── tools/               #    工具系统
│   │   ├── mcp/                 #    MCP 集成
│   │   └── prompts/             #    Prompt 模板
│   └── ...
├── docs/                        # 文档（109 MDX 页面）
└── evals/                       # 评测套件
```

---

## 三、核心模块深度解析

### 3.1 Agent 循环 (`sdk/src/agent/`) — ⭐⭐⭐ 最核心

Cline 的 Agent 是一个标准的 **ReAct 循环**（Reason + Act）：

```
┌─────────────────────────────────────┐
│           Agent Loop                 │
│                                     │
│  1. 接收用户消息 + 历史 + 上下文      │
│  2. 构建 System Prompt（含工具描述）  │
│  3. 调用 LLM → 获取响应              │
│  4. 解析响应：                       │
│     ├─ 纯文本 → 返回给用户           │
│     ├─ tool_use → 执行工具           │
│     ├─ reasoning → 展示推理过程      │
│     └─ code_edit → 生成 Diff         │
│  5. 将工具结果追加到历史              │
│  6. 回到 Step 3（直到完成）           │
│                                     │
└─────────────────────────────────────┘
```

**关键文件**:
```
sdk/src/agent/
├── agent.ts              # Agent 主循环（核心状态机）
├── types.ts              # Agent 消息类型定义
└── prompts/              # System Prompt 模板
    └── system-prompt.ts  # ★★★ Prompt 工程（非常详细！）
```

### 3.2 推理步骤 UI (`apps/vscode/src/extension-ui/components/agent/`) — ⭐⭐⭐

这是 Cline 最标志性的 UI 特性！

**组件结构**:
```
components/agent/
├── ReasoningSteps.tsx        # ★★★ 推理步骤容器
│   └── 每个步骤包含：
│       ├── step.type          # thinking | planning | analysis | decision
│       ├── step.content       # 步骤文本内容
│       ├── step.status        # pending | in_progress | completed | error
│       └── 图标/颜色编码       # 不同类型不同视觉
├── ThinkingIndicator.tsx     # 思考中动画（脉冲圆点）
└── ExecutionTracePanel.tsx   # 完整执行追踪面板
```

**推理步骤类型与图标映射**:
| 类型 | 含义 | 图标 | 颜色 |
|------|------|------|------|
| `thinking` | 思考中... | 💡 Lightbulb | Blue |
| `planning` | 制定计划 | 📋 ClipboardList | Purple |
| `analysis` | 分析代码 | 🔍 Search | Cyan |
| `decision` | 做决策 | 🚦 GitBranch | Amber |
| `execution` | 执行动作 | ▶️ Play | Green |
| `observation` | 观察结果 | 👁️ Eye | Gray |

**我们的对应**: `AgentReasoningSteps.vue` 已实现此功能！

### 3.3 工具调用组件 (`apps/vscode/src/extension-ui/components/tools/`)

```
components/tools/
├── ToolUseBlock.tsx           # 工具调用展示
│   ├── 工具名称 + 参数折叠     │
│   ├── 进度动画 (spinner)      │
│   ├── 结果展开/折叠            │
│   └── 错误状态 (红色警告)      │
├── ToolResultContent.tsx      # 工具结果渲染
│   ├── 文本内容 (markdown)      │
│   ├── 图片 (截图)              │
│   ├── 代码块 (语法高亮)        │
│   └── 错误信息 (红色)          │
└── ToolApprovalBar.tsx        # ★★★ 工具审批栏
    ├── 工具名称 + 目标文件       │
    ├── Allow / Deny 按钮        │
    ├── "Always allow" 选项      │
    └── 危险操作高亮提示          │
```

**ToolApprovalBar 设计细节**:
```
┌─────────────────────────────────────────────┐
│ ⚠️  Cline wants to write to file:           │
│    src/utils/helpers.ts                     │
│                                             │
│ [Allow]  [Deny]  [☑ Always allow writes]    │
└─────────────────────────────────────────────┘
```

**我们的对应**: `AgentChat.vue` 的工具审批区域（已实现基础版）

### 3.4 Diff Preview 系统

Cline 使用自定义 Diff 渲染（非 Monaco DiffEditor）：

```typescript
// 关键特性：
// 1. 行内 Diff（不是并排双栏）— 更紧凑
// 2. 绿色新增 / 红色删除 — 直观
// 3. 可逐个 Accept/Deny 每个 hunk
// 4. 支持 "Accept All" / "Reject All"
// 5. 点击行号跳转到原文件

// 组件位置：
apps/vscode/src/extension-ui/components/diff/
├── DiffViewer.tsx          # 主 Diff 展示组件
├── DiffLine.tsx            # 单行 Diff 元素
└── DiffHunkActions.tsx     # Hunk 操作按钮
```

### 3.5 消息类型系统 (`sdk/src/agent/types.ts`)

```typescript
// Cline 定义了完整的消息类型体系：
type Message =
  | { role: "user"; content: string }
  | { role: "assistant"; content: string }
  | { type: "reasoning"; reasoning: ReasoningStep[] }    // 推理链
  | { type: "tool_use"; tool_name: string; input: any }  // 工具调用
  | { type: "tool_result"; output: string; error?: bool } // 工具返回
  | { type: "code_edit"; file_path: string; diff: string } // 代码编辑
  | { type: "command"; command: string }                    // 命令
  | { type: "system"; message: string };                    // 系统消息
```

---

## 四、SSE / 事件流处理

Cline 使用 **Server-Sent Events** 进行流式传输：

```
事件流顺序示例：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
message_start { id, type: "assistant" }
content_block_start { type: "thinking" }     ← 推理开始
content_block_delta { type: "thinking", ... } ← 推理内容流
content_block_stop                            ← 推理结束
content_block_start { type: "tool_use" }      ← 工具调用开始
input_json_delta { partial_json: "..." }      ← 工具参数流
content_block_stop                            ← 工具调用结束
tool_result { tool_use_id, output: "..." }    ← 工具返回结果
content_block_start { type: "text" }          ← 文本开始
content_block_delta { text: "..." }           ← 文本流
content_block_stop                            ← 文本结束
message_end { usage: {...} }                  ← 消息结束
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

**与我们 SSEEventType 的对照**:
```
Cline Event              →  我们的 Type
───────────────────────────────────────────
message_start            →  (隐式)
content_block(thinking)  →  reasoning, thinking
tool_use/start           →  tool_approval_required
tool_result              →  chunk (工具结果)
content_block(text)      →  chunk
message_end + usage      →  summary + usage
```

---

## 五、最值得借鉴的 Top 5

### 🏆 #1 推理步骤可视化
- **来源**: `ReasoningSteps.tsx`
- **亮点**: 分类图标 + 状态动画 + 可折叠
- **我们的落地**: `AgentReasoningSteps.vue` ✅ 已完成

### 🏆 #2 工具审批栏
- **来源**: `ToolApprovalBar.tsx`
- **亮点**: 危险操作高亮 + Always allow 记忆
- **我们的落地**: `AgentChat.vue` approveTool/rejectTool ✅ 已完成

### 🏆 #3 紧凑型 Diff Preview
- **来源**: `DiffViewer.tsx` (行内模式)
- **亮点**: 非 Monaco，更轻量，支持逐 hunk 操作
- **我们的落地**: `DiffViewer.vue` (使用 Monaco 并排模式)

### 🏆 #4 SDK 独立性
- **来源**: `sdk/` 包
- **亮点**: Agent 逻辑与 UI 完全分离，可复用
- **启示**: 我们的 backend agent 也可以抽成独立 SDK

### 🏆 #5 Prompt 工程
- **来源**: `prompts/system-prompt.ts`
- **亮点**: 非常详细的 system prompt（~500 行），包含角色设定、工具说明、格式要求
- **启示**: 后端 orchestrator 的 prompt 可以更结构化

---

## 六、快速入门

```bash
cd D:\code\cline
pnpm install
pnpm build

# 启动 VS Code 扩展（开发模式）
cd apps/vscode && pnpm dev

# 或启动 CLI 模式
cd apps/cli && pnpm start
```

**推荐阅读路径**:
1. `sdk/src/agent/agent.ts` → Agent 核心循环
2. `apps/vscode/src/extension-ui/components/agent/ReasoningSteps.tsx` → 推理 UI
3. `sdk/src/prompts/system-prompt.ts` → Prompt 模板
4. `apps/vscode/src/extension-ui/components/tools/ToolApprovalBar.tsx` → 工具审批
5. `sdk/src/tools/` → 工具系统实现
