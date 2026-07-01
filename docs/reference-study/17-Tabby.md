# Tabby — 本地代码补全系统

> **源码位置**: `D:\code\tabby` | **大小**: 29 MB | **语言**: Rust + TypeScript  
> **官网**: https://tabby.ml | **Stars**: ~20k+  
> **定位**: 开源的自托管 AI 代码补全引擎（类似 GitHub Copilot 但本地运行）

---

## 一、项目概览

Tabby 解决的核心问题：

> **如何在不将代码发送到云端的前提下获得 AI 代码补全？**

核心特性：
- 🏠 **完全本地运行** — 不需要发送代码到外部服务器
- 🔤 **代码补全** — 类似 Copilot 的 inline suggestion
- 💬 **聊天功能** — 可以问代码问题
- 📊 **Embeddings** — 代码语义搜索
- 🔌 **多种模型支持** — 支持加载本地 GGUF/HF 格式模型
- ☁️ **可选云端** — 也支持连接 OpenAI/Claude 等 API

### 与我们项目的关联
- Embeddings 系统 ↔ 我们的 `backend/app/core/memory/embedding.py`
- 补全 API ↔ 可集成到 studio-client 的编辑器中
- 本地模型部署 ↔ 我们的 ModelRouter 本地模型支持

---

## 二、目录结构

```
D:\code\tabby\
├── crates/                     # ★★★ Rust 核心引擎
│   ├── tabby-core/             #    核心逻辑
│   │   ├── src/
│   │   │   ├── completions.rs  #    ★★★ 代码补全引擎 ⭐⭐⭐
│   │   │   ├── chat.rs         #    聊天接口
│   │   │   ├── embeddings.rs   #    ★★ 向量嵌入生成
│   │   │   ├── repository.rs   #    代码仓库索引
│   │   │   └── http.rs         #    HTTP API 服务
│   ├── tabby-lsp/              #    Language Server Protocol
│   ├── tabby-scheduler/        #    任务调度
│   └── tabby-common/           #    共享类型和工具
├── clients/                    # 客户端 SDK
│   ├── vscode/                 #    VS Code 扩展
│   ├── jetbrains/              #    JetBrains 插件
│   ├── vim/                    #    Vim 插件
│   └── node/                   #    Node.js SDK
├── python/                     # Python 绑定
├── ee/                         # 企业版功能（UI 等）
└── website/                    # 官网
```

---

## 三、核心模块

### 3.1 补全引擎 (`crates/tabby-core/src/completions.rs`) — ⭐⭐⭐

```rust
// Tabby 的补全请求/响应格式：

struct CompletionRequest {
    file_path: String,          // 当前文件路径
    language: String,           // 语言标识
    text: String,               // 光标前的文件内容
    cursor_offset: usize,       // 光标位置
    user_prompt: Option<String>, // 用户额外提示
    max_tokens: u32,            // 最大生成长度
    suggestions_count: u32,     // 返回几个候选（默认 5）
}

struct CompletionResponse {
    choices: Vec<CompletionChoice>,
}

struct CompletionChoice {
    text: String,               // 补全的文本
    confidence: f32,            // 置信度 (0-1)
}

// 补全流程：
// 1. 接收请求（包含光标前后的代码上下文）
// 2. 构造 Prompt（文件路径+语言+代码+光标位置）
// 3. 调用本地模型（llama.cpp 或 ggml 后端）
// 4. 解析响应，提取补全文本
// 5. 返回多个候选（按置信度排序）
// 6. VS Code 显示最高置信度的候选（Tab 接受，Esc 忽略）
```

### 3.2 Embedding 系统 (`crates/tabby-core/src/embeddings.rs`) — ⭐⭐

```rust
// Tabby 使用本地模型生成代码向量化表示：

struct EmbeddingRequest {
    texts: Vec<String>,         // 要向量化的文本列表
    model: String,              // 模型名称
}

struct EmbeddingResponse {
    embeddings: Vec<Vec<f32>>,  // 每个文本对应的向量（通常 768/1024/4096 维）
}

// 用途：
// 1. 代码语义搜索 — "找到所有认证相关的函数"
// 2. 重复代码检测
// 3. 相关文件推荐（给 LLM 提供 context）
```

### 3.3 HTTP API (`crates/tabby-core/src/http.rs`)

```rust
// 主要 API 端点：
POST /v1/completions          — 代码补全（类 OpenAI 格式）
POST /v1/chat/completions     — 聊天补全
POST /v1/embeddings           — 生成向量
GET  /v1/repository/status    — 仓库索引状态
POST /v1/repository/index     — 触发索引重建
GET  /v1/health                — 健康检查
```

---

## 四、API 兼容性（OpenAI Format）

Tabby 的 API 设计兼容 OpenAI 格式：

```json
// 请求
POST /v1/completions
{
    "file_path": "/src/auth.ts",
    "language": "typescript",
    "text": "function authenticate(user) {\n  return ",
    "cursor_offset": 45,
    "max_tokens": 128,
    "suggestions_count": 3
}

// 响应
{
    "choices": [
        { "text": "verifyToken(user.token)", "confidence": 0.92 },
        { "text": "checkCredentials(user)", "confidence": 0.75 },
        { "text": "validateUserSession(user)", "confidence": 0.60 }
    ],
    "model": "tabby/starCoder-7b"
}
```

---

## 五、值得借鉴的点

### 🏆 #1 OpenAI 兼容 API 设计
- 所有端点兼容 OpenAI 格式，方便客户端切换
- **落地**: 我们的 `/api/v1/chat` 已遵循此风格 ✅

### 🏆 #2 多候选返回 + 置信度
- 不只返回一个结果，而是多个候选按置信度排序
- **落地**: Agent 的 tool 选择也可以返回多个选项

### 🏆 #3 本地优先 + 云端 fallback
- 默认用本地模型，可配置远程 API 作为备选
- **落地**: ModelRouter 的 FallbackChain 就是此模式

### 🏆 #4 仓库索引状态 API
- `/repository/status` 让客户端知道索引是否就绪
- **落地**: CodebaseMemory 的 indexer 状态可以暴露类似 API

### 🏆 #5 多客户端支持（VSCode/JetBrains/Vim/Node）
- 同一服务，多个客户端接入
- **落地**: studio-client 是我们的主客户端，未来可扩展插件
