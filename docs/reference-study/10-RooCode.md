# Roo Code — AI Coding UI（执行追踪专家）

> **源码位置**: `D:\code\roocode` | **大小**: 293 MB | **语言**: TypeScript  
> **官网**: https://roocode.com | **Stars**: ~10k+  
> **定位**: VS Code AI Coding 助手，以强大的工具执行面板和推理步骤著称

---

## 一、项目概览

Roo Code 是基于 Cline 二次开发的增强版 AI 编程助手。它在 Cline 的基础上增加了：

- 🛠️ **更丰富的工具系统**（56 个工具，比 Cline 更多）
- 📊 **完整的执行仪表盘**（Turn-level 详情 + 性能指标）
- ✅ **Auto-Approval 系统**（智能自动审批安全工具）
- 📋 **Task Persistence**（任务持久化，重启不丢失）
- 🔄 **Checkpoints**（任务检查点，可回滚）
- 🧠 **Condense 系统**（长对话自动压缩上下文）

### 与 Cline 的关系
```
Cline (上游)  ──fork──→  Roo Code (下游增强版)
                          ├─ 更多工具
                          ├─ 执行追踪增强
                          ├─ Auto-Approval
                          ├─ Task Persistence
                          └─ Condense (上下文压缩)
```

---

## 二、目录结构

```
D:\code\roocode/
├── src/                         # ★★★ 核心源码
│   ├── core/                    #    核心引擎 ⭐⭐⭐
│   │   ├── task/               #    任务管理
│   │   │   ├── Task.ts         #    任务实体定义
│   │   │   └── TaskHandler.ts  #    任务处理器（主循环）
│   │   ├── tools/              #    工具系统（56 个！）
│   │   │   ├── read_file.ts
│   │   │   ├── write_file.ts
│   │   │   ├── list_code_symbols.ts
│   │   │   ├── execute_command.ts
│   │   │   ├── browser_action.ts
│   │   │   └── ... (50 more)
│   │   ├── prompts/            #    Prompt 模板（82 个 snap 快照）
│   │   ├── diff/               #    Diff 计算
│   │   ├── context-management/ #    上下文管理 ⭐
│   │   ├── auto-approval/      #    ★★★ 自动审批系统
│   │   ├── condense/           #    上下文压缩
│   │   ├── checkpoints/        #    任务检查点
│   │   ├── task-persistence/   #    任务持久化
│   │   ├── protect/            #    文件保护（防误删）
│   │   └── webview/            #    WebView 通信桥接
│   ├── api/                    #    API 层（155 个文件）
│   ├── services/               #    服务层（208 个文件）
│   ├── integration/            #    IDE 集成
│   └── shared/                 #    共享工具函数
├── webview-ui/                  # ★★★ WebView 前端（React）
│   ├── src/
│   │   ├── components/         #    所有 UI 组件
│   │   │   ├── chat/          #    聊天界面
│   │   │   ├── task/          #    任务详情 ⭐⭐⭐
│   │   │   ├── tools/         #    工具面板
│   │   │   └── settings/      #    设置页
│   │   └── hooks/             #    React Hooks
│   └── ...
├── apps/                       # 文档和发布物
└── locales/                    # 17 种语言国际化
```

---

## 三、核心模块深度解析

### 3.1 任务执行引擎 (`src/core/task/`) — ⭐⭐⭐

Roo Code 的核心是一个 **任务驱动** 的 Agent 循环：

```typescript
// Task 实体
interface Task {
  id: string;
  type: "ask" | "code" | "plan";
  status: "pending" | "running" | "completed" | "error" | "cancelled";
  messages: Message[];          // 完整消息历史
  turns: Turn[];                // 每轮详情
  context: TaskContext;         // 上下文文件列表
  metadata: {
    totalTokens: number;
    totalCost: number;
    startTime: number;
    endTime: number;
    modelUsed: string;
    toolCallsCount: number;
    toolSuccessRate: number;
  };
}

// Turn（单轮执行记录）
interface Turn {
  turnNumber: number;
  userInput: string;
  assistantMessages: AssistantMessage[];
  toolCalls: ToolCall[];
  durationMs: number;
  tokenUsage: number;
}
```

**任务生命周期**:
```
created → running → (paused?) → completed/error/cancelled
                                    ↑
                              可从 checkpoint 恢复
```

### 3.2 执行仪表盘 UI (`webview-ui/src/components/task/`) — ⭐⭐⭐

这是 Roo Code 最突出的特色！

**组件结构**:
```
webview-ui/src/components/task/
├── TaskDetailPanel.tsx          # ★★★ 任务详情主面板
│   ├── Header (状态 + 时间 + 模型)
│   ├── TurnsList (每轮折叠列表)  ← 可点击展开
│   ├── MetricsCards (性能指标卡)
│   └── Actions (重试/导出/删除)
│
├── TurnDetail.tsx               # 单轮详情
│   ├── UserMessage              # 用户输入
│   ├── AssistantResponse        # AI 回复（含工具调用）
│   ├── ToolCallTimeline         # ★★★ 工具调用时间线
│   └── TokenUsageBar            # Token 用量条
│
├── ToolCallTimeline.tsx         # 工具调用时间线
│   └── 水平排列每个工具调用：
│       [Read:main.ts]→[Write:util.js]→[Bash:npm test]
│        12ms         45ms           230ms
│
├── MetricsOverview.tsx          # 性能指标总览
│   ├── Total Tokens: 15,234
│   ├── Total Cost: $0.23
│   ├── Duration: 3m 24s
│   ├── Tool Calls: 42 (95% success)
│   └── Avg Latency: 1.2s
│
└── CheckpointTimeline.tsx       # 检查点时间线（可回滚）
```

**我们的对应**: `AgentRunDashboard.vue` ✅ 已参考此设计实现！

### 3.3 Auto-Approval 系统 (`src/core/auto-approval/`) — ⭐⭐⭐

Roo Code 的杀手级功能 — **智能决定哪些工具可以自动批准**：

```typescript
// 安全级别定义（类似我们的 SecurityLevel）
enum AutoApprovalMode {
  ALWAYS = "always",            // 总是自动批准
  SAFE_TOOLS = "safe-tools",    // 只对安全工具自动批准
  NEVER = "never",              // 从不自动批准
  CUSTOM = "custom",            // 自定义规则
}

// 工具安全分级
const TOOL_SAFETY = {
  // 🟢 SAFE — 无副作用，总是允许
  "read_file": "safe",
  "list_files": "safe",
  "search_files": "safe",
  "get_code_symbols": "safe",
  "list_code_symbols": "safe",
  
  // 🟡 MODERATE — 需要确认但风险可控
  "write_to_file": "moderate",
  "apply_diff": "moderate",
  "execute_command": "moderate",
  
  // 🔴 DANGEROUS — 必须明确授权
  "delete_file": "dangerous",
  "execute_shell": "dangerous",
  "browser_action": "dangerous",
};

// 自动审批规则引擎
function shouldAutoApprove(toolName, params, mode): boolean {
  switch(mode) {
    case "always": return true;
    case "never": return false;
    case "safe-tools": return TOOL_SAFETY[toolName] === "safe";
    case "custom":
      return checkCustomRules(toolName, params); // 用户自定义规则
  }
}
```

**与我们的 AutoCLI 对比**:

| 维度 | Roo Code | 我们 (AutoCLI) |
|------|----------|----------------|
| 分级数 | 3 级 (Safe/Moderate/Dangerous) | 5 级 |
| 规则 | 硬编码 + Custom Rules | 白名单 + 注入检测 |
| 默认行为 | Safe 工具自动批准 | SYSTEM 级默认需要确认 |
| 注入防护 | ❌ 未提及 | ✅ 正则匹配危险字符 |

### 3.4 Condense 系统 (`src/core/condense/`) — ⭐⭐

长对话的 **上下文压缩** 解决方案：

```typescript
// 问题：对话超过 token 限制怎么办？
// 方案：Condense — 将早期消息压缩为摘要

interface CondenseStrategy {
  trigger: "token_count" | "turn_count" | "manual";
  threshold: number;              // 触发阈值（如 100k tokens）
  method: "summarize" | "extract_key_facts" | "truncate";
  preserveLastN: number;          // 保留最近 N 条消息不变
}

// 压缩流程：
// 1. 检测到超限 → 触发压缩
// 2. 将 messages[0..n-threshold] 发给 LLM
// 3. 要求 LLM 生成摘要 + 关键决策记录
// 4. 替换原始消息为 [CONDENSED_SUMMARY]
// 5. 保留 recent messages 不变
```

**启示**: 我们的 MemoryStore (长期记忆) 可以借鉴此设计做短期记忆压缩。

### 3.5 Task Persistence & Checkpoints

```typescript
// 任务持久化 — 重启浏览器不丢失
interface PersistedTask {
  taskId: string;
  savedAt: timestamp;
  taskSnapshot: Task;           // 完整任务快照
  checkpointHashes: string[];   // 各阶段哈希（用于回滚）
}

// 检查点系统 — 可回退到任意阶段
interface Checkpoint {
  id: string;
  turnNumber: number;           // 第几轮
  stateSnapshot: object;        // 当时完整状态
  filesModified: string[];      // 此轮修改的文件列表
  createdAt: timestamp;
}

// 用户操作：回滚到某检查点
async function rollback(checkpointId: string) {
  const cp = await loadCheckpoint(checkpointId);
  for (const file of cp.filesModified) {
    await restoreFileVersion(file, cp.stateSnapshot.files[file]);
  }
  task.restoreState(cp.stateSnapshot);
}
```

---

## 四、最值得借鉴的 Top 5

### 🏆 #1 执行仪表盘（Turn-Level Detail）
- **来源**: `TaskDetailPanel.tsx` + `TurnDetail.tsx`
- **亮点**: 每轮独立查看、工具时间线、Token 用量条
- **落地**: `AgentRunDashboard.vue` ✅

### 🏆 #2 Auto-Approval 智能审批
- **来源**: `auto-approval/`
- **亮点**: 3 级安全分级 + 自定义规则
- **启示**: AutoCLI 可增加 CUSTOM 规则模式

### 🏆 #3 Condense 上下文压缩
- **来源**: `condense/`
- **亮点**: 超长对话自动压缩，保持关键信息
- **启示**: MemoryExtractor 可增加 condense 策略

### 🏆 #4 Task Persistence
- **来源**: `task-persistence/`
- **亮点**: 任务序列化到本地存储，刷新页面恢复
- **启示**: AgentChat 可加入任务持久化

### 🏆 #5 Checkpoint 回滚
- **来源**: `checkpoints/`
- **亮点**: 每轮保存状态快照，支持一键回滚
- **启示**: 可用于"撤销 AI 本次修改"

---

## 五、快速入门

```bash
cd D:\code\roocode
pnpm install
pnpm build

# 开发模式
pnpm dev
```

**推荐阅读**:
1. `src/core/task/TaskHandler.ts` → 任务主循环
2. `src/core/auto-approval/` → 自动审批系统
3. `webview-ui/src/components/task/TaskDetailPanel.tsx` → 仪表盘 UI
4. `src/core/condense/` → 上下文压缩
5. `src/core/checkpoints/` → 检查点回滚
