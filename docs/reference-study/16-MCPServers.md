# MCP Servers — 官方 MCP 工具服务器集合

> **源码位置**: `D:\code\mcp-servers` | **大小**: 1.4 MB | **语言**: TypeScript + Python  
> **官网**: https://github.com/modelcontextprotocol/servers | **出品**: Anthropic / Model Context Protocol  
> **定位**: 官方提供的 MCP Server 参考实现集合

---

## 一、项目概览

MCP Servers 提供了 **各种工具的标准实现**，作为开发 MCP Server 的参考：

📁 **Filesystem Server** — 文件系统操作（读/写/搜索/监听）
🐙 **Git Server** — Git 操作（status/diff/log/commit/branch）
🗄️ **PostgreSQL Server** — 数据库查询
🌐 **Browser Server** — 浏览器自动化（截图/DOM操作/导航）
🔍 **Brave Search** — Web 搜索 API

### 与我们的关系
- 我们的后端已有 MCP Client（`backend/app/core/mcp/`）
- 这些 Server 可以直接接入我们的系统作为工具来源
- Filesystem 和 Git Server 最实用

---

## 二、可用服务器清单

```
src/
├── filesystem/              # ★★★ 文件系统 Server ⭐⭐⭐
│   ├── index.ts             #    主入口
│   ├── filesystem.ts        #    核心：文件读写搜索
│   └── utils.ts            #    工具函数
│
├── git/                     # ★★★ Git Server ⭐⭐
│   ├── index.ts
│   ├── git.ts               #    Git 操作封装
│   └── utils.ts
│
├── postgres/                # PostgreSQL 数据库
│   ├── index.ts
│   └── postgres.ts
│
├── brave-search/            # Brave 搜索 API
│   └── index.ts
│
├── puppeteer/               # 浏览器自动化
│   ├── index.ts
│   └── browser.ts
│
├── memory/                  # 内存/知识图谱存储
│   └── index.ts
│
└── fetch/                   # HTTP 请求工具
    └── index.ts
```

---

## 三、重点分析：Filesystem Server

```typescript
// src/filesystem/index.ts

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

const server = new McpServer({
    name: "filesystem",
    version: "0.1.0",
});

// 注册工具（使用 Zod Schema 定义参数）：

// 1. 列出目录内容
server.tool(
    "list_directory",
    "List directory contents",
    { path: z.string().describe("Directory path") },
    async ({ path }) => {
        const entries = await fs.readdir(path, { withFileTypes: true });
        return {
            content: [{
                type: "text" as const,
                text: JSON.stringify(entries.map(e => ({
                    name: e.name,
                    isDirectory: e.isDirectory(),
                    size: e.size,
                })), null, 2),
            }],
        };
    }
);

// 2. 读取文件
server.tool(
    "read_file", 
    "Read file contents",
    {
        path: z.string(),
        offset: z.number().optional().default(0),  // ★ 支持偏移量
        limit: z.number().optional().default(100), // ★ 支持限制行数（借鉴 SWE-agent）
    },
    async ({ path, offset, limit }) => {
        const content = await fs.readFile(path, 'utf-8');
        const lines = content.split('\n').slice(offset, offset + limit);
        return {
            content: [{ type: "text", text: lines.join('\n') }],
        };
    }
);

// 3. 写入文件
server.tool("write_file", "Write content to file",
    { path: z.string(), content: z.string() },
    async ({ path, content }) => {
        await fs.writeFile(path, content, 'utf-8');
        return { content: [{ type: "text", text: `Written ${content.length} chars to ${path}` }] };
    }
);

// 4. 编辑文件（search & replace）
server.tool("edit_file", "Edit file by replacing text",
    {
        path: z.string(),
        old_text: z.string(),       // 要替换的内容
        new_text: z.string(),       // 新内容
    },
    async ({ path, old_text, new_text }) => {
        let content = await fs.readFile(path, 'utf-8');
        if (!content.includes(old_text)) {
            throw new Error(`Old text not found in ${path}`);
        }
        content = content.replace(old_text, new_text);
        await fs.writeFile(path, content);
        return { content: [{ type: "text", text: `Replaced in ${path}` }] };
    }
);

// 5. 创建目录
server.tool("create_directory", "Create new directory",
    { path: z.string() },
    async ({ path }) => { await fs.mkdir(path, { recursive: true }); ... }
);

// 6. 移动/重命名文件
server.tool("move_file", "Move/rename file",
    { source: z.string(), destination: z.string() },
    async ({ source, destination }) => { await fs.rename(source, destination); ... }
);

// 7. 搜索文件（glob 模式）
server.tool("search_files", "Search files by glob pattern",
    {
        path: z.string(),
        pattern: z.string(),           // glob 模式如 "**/*.ts"
        exclude_pattern: z.string().optional(),
    },
    async ({ path, pattern, exclude_pattern }) => {
        const files = glob.sync(pattern, { cwd: path, ignore: exclude_pattern });
        return { content: [{ type: "text", text: JSON.stringify(files) }] };
    }
);

// 8. 获取文件信息
server.tool("get_file_info", "Get file metadata",
    { path: z.string() },
    async ({ path }) => {
        const stat = await fs.stat(path);
        return {
            content: [{ type: "text", text: JSON.stringify({
                size: stat.size,
                created: stat.birthtime,
                modified: stat.mtime,
                isDirectory: stat.isDirectory(),
                isFile: stat.isFile(),
            }, null, 2) }],
        };
    }
);

// 9. 监听目录变更
server.resource("directory_watch", "Watch for file changes",
    { uri: `file://${watchPath}`, name: "File Watcher" },
    async () => {
        // 返回当前状态
        return { contents: [...] };
    }
);
```

---

## 四、关键设计要点

### 4.1 Zod Schema 参数验证
所有工具参数用 Zod Schema 定义，自动生成 JSON Schema 给 LLM：
```typescript
{ path: z.string().describe("Description"), offset: z.number().optional().default(0) }
```

### 4.2 统一返回格式
所有工具返回 `{ content: McpContent[] }` 格式（Text/Image/Resource）

### 4.3 错误处理
- 找不到文件 → 抛异常（MCP SDK 自动转为 error response）
- 权限不足 → 返回错误文本
- 参数无效 → Zod 验证失败自动报错

### 4.4 安全考虑
- Filesystem Server 默认只访问指定根目录（不能越权）
- 敏感操作（delete）需要额外确认
- 路径遍历防护 (`../` 过滤）

---

## 五、落地建议

```
MCP Server          →  接入方式                    →  用途
─────────────────────────────────────────────────────────────
Filesystem Server   →  stdio 模式启动              →  替代部分 autocli 功能
Git Server          →  stdio 启动                 →  增强 git 操作能力
PostgreSQL Server   →  连接数据库                   →  数据查询/管理
Brave Search        →  需要 API Key                →  Web 搜索增强
Memory Server       →  持久化记忆                   →  替代/补充 MemoryStore
Fetch Server        →  HTTP 请求                   →  API 调用工具
```

---

## 六、快速入门

```bash
cd D:\code\mcp-servers
pnpm install

# 启动 filesystem server（监听当前目录）
npx @modelcontextprotocol/server-filesystem ./my-project

# 启动 git server
npx @modelcontextprotocol/server-git .
```
