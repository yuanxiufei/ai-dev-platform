# MCP (Model Context Protocol) — AI 工具协议标准

> **源码位置**: `D:\code\mcp-spec` | **大小**: 39 MB | **语言**: TypeScript + JSON Schema  
> **官网**: https://modelcontextprotocol.io | **出品**: Anthropic  
> **定位**: LLM 连接外部工具和数据源的标准化协议

---

## 一、项目概览

MCP 是 Anthropic 推出的 **开放协议**，解决了一个根本问题：

> **如何让 AI 模型统一地访问外部工具？**

在 MCP 之前：
- OpenAI 用 Function Calling 格式
- Claude 用 Tool Use XML 标签  
- 各家自定义格式不互通...

MCP 统一了这一切：

🔌 **标准化接口** — 任何工具都用同一套 JSON-RPC 协议通信
📋 **工具发现** — Client 自动发现 Server 上有哪些工具
🎯 **资源访问** — 除了工具，还能读取 Server 上的数据（文件、数据库行等）
📝 **Prompt 模板** — Server 可以提供 Prompt 给 Client 使用
🚀 **多传输** — 支持 Stdio / HTTP(SSE) / Streamable HTTP 三种传输层

### 核心架构
```
┌─────────────┐    MCP 协议    ┌─────────────┐    MCP 协议    ┌─────────────┐
│   Host App  │ ◄────────────► │  MCP Server  │ ◄────────────► │  MCP Server  │
│ (IDE/Chat)  │               │ (Filesystem) │               │ (Postgres)  │
└─────────────┘               └─────────────┘               └─────────────┘
     ↑                              ↑                              ↑
  Client                         Tools/Resources                Tools/Resources
```

---

## 二、目录结构

```
D:\code\mcp-spec\
├── schema/                      # ★★★ JSON Schema 定义 ⭐⭐⭐
│   ├── 2025-03-26/              #    最新版本 schema
│   │   ├── schema.json         #    ★★★ 完整协议定义
│   │   ├── mcp.json            #    核心类型
│   │   └── types/              #    子类型分解
│   └── ... (其他版本)
├── seps/                        # SEPs (MCP Enhancement Proposals)
│   ├── sep-1-streamable-http.md #    Streamable HTTP 传输
│   ├── sep-2-sampling.md        #    采样协议
│   ├── sep-3-resource-references.md  # 资源引用
│   └── ...
├── docs/                        # 文档（284 页 MDX）
├── tools/                       # 工具脚本
│   └── generate-schema.ts       #    Schema 生成器
└── blog/                        # 博客文章
```

---

## 三、核心协议详解

### 3.1 JSON-RPC 2.0 基础

MCP 基于 JSON-RPC 2.0：

```json
// 请求格式
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}

// 成功响应
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "tools": [
      {
        "name": "read_file",
        "description": "Read file contents",
        "inputSchema": {
          "type": "object",
          "properties": {
            "path": { "type": "string" }
          },
          "required": ["path"]
        }
      }
    ]
  }
}

// 错误响应
{
  "jsonrpc": "2.0",
  "id": null,
  "error": {
    "code": -32602,
    "message": "Invalid params: path is required"
  }
}
```

### 3.2 核心方法（Protocol Methods）

```typescript
// ======== 工具相关 ========
// 1. 列出所有可用工具
{ method: "tools/list" } 
// → 返回 { tools: [{name, description, inputSchema}] }

// 2. 调用工具
{ method: "tools/call", params: { name: "read_file", arguments: {path: "/tmp/x"} }}
// → 返回 { content: [{ type: "text", text: "...file content..." }] }

// ======== 资源相关 ========
// 3. 列出可用资源（数据源）
{ method: "resources/list" }
// → 返回 { resources: [{uri, name, mimeType, description}] }

// 4. 读取资源内容
{ method: "resources/read", params: { uri: "file:///tmp/x.txt" }}
// → 返回 { contents: [{ uri, mimeType, text }] }

// 5. 订阅资源更新（实时推送变化）
{ method: "resources/subscribe", params: { uri: "file:///tmp/x.txt" }}

// ======== Prompt 相关 ========
// 6. 列出 Server 提供的 Prompt 模板
{ method: "prompts/list" }
// → 返回 { prompts: [{name, description, arguments}] }

// 7. 获取填充后的 Prompt
{ method: "prompts/get", params: { name: "code-review", arguments: {filePath: "/src/main.js"}}}
// → 返回 { description: "Review this code", messages: [{role: "user", content: "..."}] }

// ======== 其他 ========
// 8. 初始化握手
{ method: "initialize", params: { protocolVersion: "2025-03-26", capabilities: {}, clientInfo: {...} }}
// → 返回 { protocolVersion, capabilities, serverInfo }

// 9. 通知 Server 已初始化完成
{ method: "notifications/initialized" }

// 10. Ping 心跳
{ method: "ping" }
```

### 3.3 传输层

```typescript
// === 1. stdio (标准输入输出) ===
// 最简单的方式，适合本地进程间通信
// Client 启动子进程，通过 stdin/stdout 发送 JSON-RPC
const process = spawn("npx", ["@modelcontextprotocol/server-filesystem", "/tmp"]);
process.stdin.write(JSON.stringify(request));
process.stdout.on("data", (data) => parseResponse(data));

// === 2. SSE (Server-Sent Events) ===
// 适合远程连接，单向流
// POST /mcp (发送请求)
// GET /mcp?session=xxx (SSE 流接收通知/推送)
// 我们的后端 SSE 就可以用这个！

// === 3. Streamable HTTP (新标准) ===
// SEP-1 定义的增强版 HTTP
// 支持双向流、流式响应
const response = fetch("/mcp", {
  method: "POST",
  headers: { "Content-Type": "application/json", Accept: "application/stream+json"},
  body: JSON.stringify({ jsonrpc: "2.0", method: "tools/call", ... }),
});
// 响应是 application/stream+json，逐个返回结果
```

### 3.4 Content Types（工具返回值的统一格式）

```typescript
type McpContent =
  | TextContent       // 纯文本
  | ImageContent      // 图片 (base64)
  | EmbeddedResource  // 嵌入的资源引用

interface TextContent {
  type: "text";
  text: string;
  annotations?: { auditLogCompleted?: boolean }; // 元数据
}

interface ImageContent {
  type: "image";
  data: string;       // base64 编码
  mimeType: string;   // "image/png" | "image/jpeg" ...
}

interface EmbeddedResource {
  type: "resource";
  uri: string;        // 资源 URI
  mimeType?: string;
  description?: string;
}
```

---

## 四、与我们系统的映射

```
MCP 概念              ↔  我们的实现
─────────────────────────────────────────────────
MCP Client            ↔  backend/app/core/mcp/MCPClient
MCP Server            ↔  自建 MCP Servers 或社区 Servers
Tools (工具)          ↔  backend/app/core/tools/registry.py
Resources (资源)      ↔  CodebaseMemory 的查询结果
Prompts (Prompt)      ↔  skills/ 中的技能 Prompt
stdio 传输            ↔  当前使用的方式
SSE 传输              ↔  可用于远程 MCP 连接
JSON-RPC 2.0         ↔  底层通信协议（我们用 SSE 包了一层）
```

---

## 五、最值得借鉴的点

### 🏆 #1 统一工具接口
- 所有工具都有统一的 `name + inputSchema + description` 格式
- **落地**: 我们的 `FunctionTool` / `ToolSchema` 已对齐此格式

### 🏆 #2 工具发现机制
- Client 不需要预先知道有哪些工具，运行时动态发现
- **落地**: MCPManager 的 `list_tools()` 已实现

### 🏆 #3 资源与工具分离
- Resource 是只读的数据源（文件内容、数据库行）
- Tool 是可写的操作（写文件、执行 SQL）
- **落地**: CodebaseMemory 的查询 = Resources，AutoCLI = Tools

### 🏆 #4 多传输层支持
- 同一协议可以在 stdio/HTTP/SSE 下工作
- **落地**: 我们目前只用 SSE，可扩展 HTTP 模式

### 🏆 #5 Prompt Templates
- Server 可以给 Client 提供 Prompt 模板
- **落地**: SkillManager 的 prompt 生成功能

---

## 六、快速入门

```bash
cd D:\code\mcp-spec
npm install

# 查看 Schema（核心协议定义）
cat schema/2025-03-26/schema.json | python -m json.tool

# 查看文档
npm run docs-dev
```

**推荐阅读**:
1. `schema/2025-03-26/schema.json` — 完整协议定义（最重要！）
2. `seps/sep-1-streamable-http.md` — Streamable HTTP 传输规范
3. `seps/sep-3-resource-references.md` — 资源引用规范
4. `docs/` — 完整教程文档
