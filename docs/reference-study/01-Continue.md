# Continue — AI IDE 标准实现

> **源码位置**: `D:\code\continue` | **大小**: 271 MB | **语言**: TypeScript  
> **官网**: https://continue.dev | **Stars**: ~20k+  
> **定位**: VS Code / JetBrains AI 编程助手扩展，AI IDE 领域的事实标准

---

## 一、项目概览

Continue 是目前最成熟的 **开源 AI IDE 扩展**，支持 VS Code 和 JetBrains 全家桶。它的架构设计成为了后续所有 AI IDE 项目的参考模板。

### 核心能力
- 🤖 多模型支持（OpenAI/Claude/本地/Ollama）
- 💬 Chat + Inline Edit 双模式
- 📚 RAG 上下文管理（文件/目录/代码库级）
- 🔍 自动补全（Tab 补全）
- 🔌 MCP 工具协议集成

### 技术栈
```
前端: React + TypeScript + TailwindCSS
后端: Python (FastAPI) + TypeScript (Node)
通信: JSON-RPC (IDE ↔ Server) + SSE/Streaming
向量: Embeddings (本地/远程)
```

---

## 二、目录结构详解

```
D:\code\continue/
├── core/                        # ★★★ 核心共享库（最重要！）
│   ├── context/                 #    上下文管理系统（RAG 核心）
│   │   ├── contextProviders.ts  #    Context Provider 注册表
│   │   ├── index/              #    代码索引（Tree-sitter/AST）
│   │   └── embed.ts            #    Embedding 向量化
│   ├── llm/                     #    LLM 调用层
│   │   ├── modelRouter.ts      #    模型路由器 ⭐
│   │   └── chat.ts             #    对话流式处理
│   ├── tools/                   #    内置工具集（78 个工具）
│   ├── edit/                    #    代码编辑引擎（Diff 应用）
│   ├── diff/                    #    Diff 计算与展示
│   ├── indexing/                #    文件索引系统
│   ├── autocomplete/            #    Tab 自动补全
│   ├── config/                  #    配置管理
│   └── continueServer/          #    后端服务
├── extensions/                  # VS Code / JetBrains 扩展入口
├── gui/                         # Web UI（Chat 界面）
│   ├── src/                     # React 组件
│   │   ├── components/chat/     # 聊天组件 ⭐⭐⭐
│   │   ├── context-providers/   # 上下文选择 UI
│   │   └── settings/           # 设置面板
├── packages/                    # 共享包（SDK 等）
├── docs/                        # 文档（152 个 MDX）
├── skills/                      # 自定义技能
└── sync/                        # 同步服务（Rust）
```

---

## 三、核心模块深度解析

### 3.1 上下文管理系统 (`core/context/`) — ⭐⭐⭐ 最值得借鉴

这是 Continue 最核心的设计。Context 决定了发送给 LLM 的"背景信息"。

**关键文件**:
```typescript
// D:\code\continue\core\context\ContextProvider.ts
// ContextProvider 接口定义 — 所有上下文源的抽象基类
interface ContextProvider {
  id: string;                  // 唯一标识
  description: string;        // 描述（显示给用户）
  getContextItems(query?: string): Promise<ContextItem[]>;
  // query: 用户搜索关键词 → 返回相关代码片段
}

// D:\code\continue\core\context\contextProviders.ts
// 内置 Provider 列表：
// - OpenFilesContextProvider    → 当前打开的文件
// - DirectoryContextProvider    → 整个目录（按需加载）
// - CodebaseIndex              → 全代码库搜索
// - GitContextProvider         → Git diff/stage/untracked
// - URLContextProvider         → 网页内容抓取
// - TerminalContextProvider    → 终端输出
// - DiffContextProvider        → 当前 Diff 变更
// - SearchContextProvider      → 全局搜索结果
// - MCPContextProvider         → MCP 工具返回的内容
```

**可借鉴点**:
- ✅ `@` 触发上下文选择面板（我们已实现的 @-mention 来源）
- ✅ 分层加载策略：打开文件 > 目录 > 全库（避免 token 浪费）
- ✅ 每个 ContextItem 有独立的 title + content + path

**我们的映射**:
```
Continue ContextProvider  →  我们的 ContextPanel.vue + ReferencedFile 类型
@file:main.ts            →  addFileContext() 函数
@dir:src/components/     →  目录批量添加
@search:useState hook    →  全局语义搜索
```

### 3.2 模型路由器 (`core/llm/modelRouter.ts`) — ⭐⭐

```typescript
// 核心逻辑：
class ModelRouter {
  // 1. 支持多 Provider：OpenAI, Anthropic, Ollama, LM Studio, Local
  // 2. 每个模型有独立的配置：
  interface ModelConfig {
    title: string;           // 显示名称
    provider: string;        // "openai" | "anthropic" | "ollama" ...
    apiBase?: string;        // 自定义 API 端点
    model: string;           // 具体模型名
    auth?: string;          // API Key
    completionOptions;       // temperature, maxTokens...
  }
  // 3. 自动选择最佳可用模型
  // 4. Fallback 链：主模型不可用时切换到备用
}
```

**与我们的 ModelRouter 对比**:

| 能力 | Continue | 我们 |
|------|----------|------|
| 多 Provider | ✅ 8+ | ✅ 7+ (api_gateway.py) |
| Fallback | 简单链式 | ⭐ 5层回退 (fallback_chain.py) |
| 本地模型 | Ollama/LM Studio | ⭐ DynamicScore 评分 |
| 流式输出 | ✅ SSE | ✅ SSE |

### 3.3 聊天 UI 组件 (`gui/src/components/chat/`) — ⭐⭐⭐

**关键组件**:
```
gui/src/components/chat/
├── ChatView.tsx              # 主聊天视图（消息列表 + 输入框）
├── MessageContainer.tsx      # 单条消息容器（支持多种类型）
├── CodeBlock.tsx             # 代码块渲染（带复制/运行按钮）
├── ContextChip.tsx           # 上下文标签（@引用的小芯片）
├── SuggestionChip.tsx        # 建议操作按钮（Apply/Edit/Insert）
├── ToolCallBlock.tsx         # 工具调用展示块
├── ThinkingAnimation.tsx     # 思考动画（流式中的 loading 态）
├── FileEditPreview.tsx       # 文件编辑预览（Diff 展示）
└── AtMentionPopover.tsx      # @-mention 弹出选择面板 ⭐
```

**AtMentionPopover 的交互设计**（最精巧的细节）:
```
用户输入 "@" 
  → 弹出面板，列出所有 ContextProvider
  → 可继续输入过滤（如 "@use" 过滤出 useState 相关文件）
  → 选择后插入 <file:path> 标记到输入框
  → 发送时自动替换为实际文件内容
```

**我们的对应**: `AgentChat.vue` 的 `onInput()` + `showAtMenu` 已部分实现

### 3.4 工具系统 (`core/tools/`) — ⭐⭐

78 个内置工具，分类如下：
```
📁 文件操作: Read, Write, Edit, Glob, Grep, LSP
🔍 代码理解: ListCodeSymbols, ListDefinitions
🐙 版本控制: GitStatus, GitDiff, GitLog
🖥️ 终端执行: Terminal, Bash
🌐 网络: HTTP Request, Fetch
📦 包管理: NPM, Pip, Cargo
🔌 扩展: Custom Commands, MCP Tools
```

**工具注册模式**:
```typescript
// 每个工具实现统一的 Tool 接口
interface Tool {
  name: string;
  description: string;
  parameters: Schema;         // JSON Schema
  execute(params): Promise<ToolResult>;
}
```

**对比**: 我们的 AutoCLI 有类似的 5 级安全策略 + 白名单机制。

### 3.5 代码编辑引擎 (`core/edit/`)

```typescript
// Continue 使用两种编辑方式：
// 1. ApplyPatchEdit: 基于 Unified Diff 格式的精确修改
//    → 适合大范围重构、多行替换
// 2. StreamEdit: Token-by-token 的流式编辑
//    → 实时展示 AI 正在写什么
//    → 类似 Cursor 的 inline edit 效果

// 关键文件：
// applyEdits.ts        — 将 Edit 操作应用到文件
// streamEdit.ts        — 流式编辑状态机
// resolveConflict.ts   — 冲突解决（当文件已被外部修改时）
```

---

## 四、SSE / 流式事件系统

Continue 使用自定义的 JSON-RPC over SSE 协议：

```
客户端 ←──SSE──── 服务端
  ↓
{ type: "text", text: "Hello" }           ← 文本流片段
{ type: "reasoning", reasoning: "..."}     ← 推理过程
{ type: "tool_use", tool_name: "Read", ... }  ← 开始工具调用
{ type: "tool_result", output: "..." }     ← 工具返回
{ type: "code_edit", file_path, diff }     ← 代码修改建议
{ type: "command", command: "/edit" }      ← 斜杠命令
{ type: "done", usage: { tokens, cost } }  ← 完成 + 用量统计
```

**我们的 SSE 事件对齐**（已在 studio.ts 中定义）:
```
Continue 事件          →  我们的 SSEEventType
─────────────────────────────────────────
text/reasoning        →  thinking, chunk
tool_use/tool_result  →  tool_approval_required, tool_error
code_edit             →  (通过 DiffViewer 展示)
done + usage          →  summary, usage
```

---

## 五、最值得借鉴的 Top 5 设计

### 🏆 #1 分层 Context 管理
**问题**: 发送给 LLM 的信息太多会浪费 token，太少会导致回答不准确。
**方案**: 三层策略 — 打开文件(即时) → 目录(按需) → 全库(搜索)
**落地**: 参考 `core/context/ContextProvider.ts` 实现 ContextPanel

### 🏆 #2 @-mention 交互
**问题**: 用户如何告诉 AI "看这个文件"？
**方案**: 输入 `@` 触发面板，模糊搜索选择，插入为可视化标签
**落地**: AgentChat.vue 的 onInput() 已有基础实现

### 🏆 #3 流式代码编辑
**问题**: 用户想实时看到 AI 在改什么，而不是等它写完才显示。
**方案**: StreamEdit 状态机 — 逐 token 渲染到 Monaco Editor
**落地**: DiffViewer.vue + inline edit 模式

### 🏆 #4 多模型统一路由
**问题**: 不同任务适合不同模型（快/便宜 vs 慢/聪明）。
**方案**: ModelRouter + per-model config + fallback
**落地**: 我们的 model_router.py 已经更完善（5 层回退）

### 🏆 #5 工具调用的 UI 反馈
**问题**: AI 调用工具时用户不知道它在干什么。
**方案**: ToolCallBlock 组件 — 展示名称、参数、进度、结果
**落地**: AgentRunDashboard.vue 的工具追踪面板

---

## 六、快速上手指南

```bash
# 安装依赖
cd D:\code\continue
npm install

# 启动开发服务器（GUI）
npm run dev --workspace=gui

# 启动后端服务器
npm run dev --workspace=core/continueServer

# 在 VS Code 中测试扩展
npm run dev --workspace=extensions/vscode
```

**推荐阅读顺序**:
1. `core/context/ContextProvider.ts` — 理解 Context 架构
2. `gui/src/components/chat/MessageContainer.tsx` — 理解聊天 UI
3. `core/llm/modelRouter.ts` — 理解模型调度
4. `core/tools/` — 理解工具系统
5. `core/edit/streamEdit.ts` — 理解流式编辑
