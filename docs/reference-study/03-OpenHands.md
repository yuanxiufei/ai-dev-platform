# OpenHands — AI 软件工程机器人（Sandbox 执行）

> **源码位置**: `D:\code\openhands` | **大小**: 18 MB | **语言**: Python + React/TypeScript  
> **官网**: https://www.all-hands-ai.net/openhands | **Stars**: ~40k+  
> **定位**: 端到端 AI 软件工程师 Agent，带安全沙箱执行环境

---

## 一、项目概览

OpenHands（原名 OpenDevin）是一个 **完整的 AI SE（软件工程）Agent 平台**。它的目标是让 AI 像人类开发者一样操作：

- 💻 在真实环境中执行代码（不是模拟）
- 🌐 使用浏览器进行 Web 操作
- 📦 安装依赖、运行测试、调试错误
- 🔧 编辑文件、提交 Git、创建 PR
- 🛡️ 所有操作在沙箱中隔离执行

### 核心能力
- 🏗️ **Sandbox 环境** — Docker/E2B 安全隔离
- 🤖 **多 Agent 架构** — BrowserAgent, CodeAgent, BashAgent 等
- 🔄 **事件驱动** — 完整的操作日志和回放
- 🖥️ **Web UI** — React 前端实时展示 Agent 行为
- 📊 **评测系统** — SWE-bench 验证修复效果

### 技术栈
```
后端: Python (FastAPI) + LangChain
前端: React + TypeScript + TailwindCSS
执行: Docker / E2B Sandbox
评测: SWE-bench (GitHub Issues → Fix)
存储: SQLite + 文件系统
```

---

## 二、目录结构

```
D:\code\openhands/
├── openhands/                   # ★★★ 核心后端包
│   ├── app_server/              #    ★★ FastAPI 应用服务器 ⭐⭐⭐
│   │   ├── app.py               #    FastAPI 主应用
│   │   ├── sandbox/             #    ★★★ 沙箱管理 ⭐⭐⭐
│   │   │   └── local_sandbox.py #    Docker 沙箱实现
│   │   ├── integrations/        #    第三方集成（92 个！）
│   │   │   ├── github.py        #    GitHub API 集成
│   │   │   └── ...
│   │   ├── mcp/                 #    MCP 工具集成
│   │   ├── event_callback/      #    事件回调
│   │   └── conversation/        #    对话会话管理
│   ├── analytics/               #    数据分析
│   ├── db/                      #    数据库层
│   └── server/                  #    通用服务
├── frontend/                    # ★★★ React 前端
│   ├── src/
│   │   ├── components/          #    组件
│   │   ├── pages/               #    页面
│   │   └── hooks/               #    Hooks
├── openhands-ui/                # 备用 UI
├── tests/                       # 测试套件（112 个）
├── skills/                      # 技能定义（27 个 MD）
├── config.template.toml         # 配置模板
└── docker-compose.yml           # Docker 编排
```

---

## 三、核心模块深度解析

### 3.1 沙箱执行环境 (`openhands/app_server/sandbox/`) — ⭐⭐⭐

这是 OpenHands 最核心的安全设计：

```python
# 沙箱抽象接口：
class Sandbox:
    """安全的代码执行环境"""
    
    async def execute(self, command: str) -> ExecutionResult:
        """在沙箱中执行命令"""
        raise NotImplementedError
    
    async def read_file(self, path: str) -> str:
        """读取沙箱中的文件"""
        raise NotImplementedError
    
    async def write_file(self, path: str, content: str):
        """写入文件到沙箱"""
        raise NotImplementedError
    
    async def get_timeout(self) -> int:
        """获取命令超时时间（秒）"""
        return 300  # 默认 5 分钟超时


# Docker 沙箱实现：
class DockerSandbox(Sandbox):
    """基于 Docker 容器的沙箱实现"""
    
    def __init__(self, image: str = "openhands/sandbox"):
        self.container = None
        self.image = image
    
    async def start(self):
        """启动容器"""
        self.container = await docker.containers.run(
            self.image,
            detach=True,
            # 关键安全限制：
            security_opt=["no-new-privileges"],  # 不能提权
            mem_limit="4gb",                    # 内存限制
            pids_limit=1000,                    # 进程数限制
            network_mode="bridge",              # 网络隔离
            read_only=False,                     # 可写文件系统
            # 但挂载了工作区目录
            volumes={self.workspace: {"bind": "/workspace", "mode": "rw"}}
        )
    
    async def execute(self, command: str) -> ExecutionResult:
        exec_id = await self.container.exec_create(
            cmd=f"bash -c {shlex.quote(command)}",
            timeout=self.get_timeout()
        )
        stream = await self.container.exec_start(exec_id, detach=False)
        
        output = await stream.read()
        exit_code = await exec_inspect(exec_id)
        
        return ExecutionResult(
            output=output,
            exit_code=exit_code["ExitCode"],
            timed_out=(exit_code["ExitCode"] == 137),  # SIGKILL = timeout
        )
```

**安全策略对比（vs 我们的 AutoCLI）**:

| 维度 | OpenHands Sandbox | 我们 AutoCLI |
|------|-------------------|--------------|
| 隔离级别 | Docker 容器级隔离 | 进程级白名单 |
| 资源限制 | CPU/Memory/PID 限制 | 无 |
| 网络隔离 | Bridge 网络 | 无 |
| 文件系统 | 只限工作区目录 | 全盘可读 |
| 适用场景 | 远程不可信代码 | 本地可信 Agent |

### 3.2 Agent 系统 (`openhands/resolver/`)

OpenHands 的 Agent 架构：

```python
# Agent 类型：
class AgentType(Enum):
    BROWSER = "browser-agent"     # 浏览器操作 Agent
    CODE = "code-agent"          # 代码编辑 Agent  
    BASH = "bash-agent"          # Shell 命令 Agent
    MONITOR = "monitor-agent"    # 监控 Agent（检测死循环等）

# Agent 基类：
class BaseAgent:
    name: str
    description: str
    tools: List[Tool]             # 可用工具列表
    max_iterations: int           # 最大迭代次数
    llm_config: LLMConfig         # LLM 配置
    
    async def run(self, task: Task) -> AgentOutput:
        """主循环：思考→行动→观察→思考..."""
        history = []
        
        for i in range(self.max_iterations):
            # 1. 构建 prompt（包含历史 + 任务 + 工具描述）
            prompt = self.build_prompt(task, history)
            
            # 2. 调用 LLM
            response = await self.llm.complete(prompt)
            
            # 3. 解析 action
            action = self.parse_action(response)
            
            if action.type == "finish":
                return AgentOutput(answer=action.answer)
            
            # 4. 执行工具
            result = await self.execute_action(action)
            
            # 5. 记录到历史
            history.append(Message(
                role="assistant", content=response,
                tool_result=result
            ))
            
            # 6. 死循环检测
            if self.detect_loop(history):
                break
        
        return AgentOutput(error="Max iterations reached")
```

### 3.3 事件系统 (`openhands/app_server/event_callback/`)

完整的操作审计追踪：

```python
# 事件类型：
class EventAction(Enum):
    MESSAGE = "message"              # 用户/AI 消息
    TOOL_CALL = "tool_call"          # 工具调用开始
    TOOL_RESULT = "tool_result"      # 工具调用结果
    FILE_READ = "file_read"          # 文件读取
    FILE_WRITE = "file_write"        # 文件写入
    BASH_EXECUTE = "bash_execute"     # 命令执行
    BROWSER_ACTION = "browser_action"# 浏览器操作
    ERROR = "error"                  # 错误事件
    STATE_CHANGE = "state_change"    # 状态变更

class Event:
    id: str
    session_id: str                 # 会话 ID
    timestamp: datetime
    action: EventAction
    source: str                     # 触发源（user/agent/system）
    data: dict                      # 事件数据
```

### 3.4 前端 UI (`frontend/`)

React 前端组件：

```
frontend/src/components/
├── ChatPanel.tsx                   # ★★★ 主聊天面板
│   ├── MessageList.tsx            #    消息列表（含工具调用展示）
│   ├── InputArea.tsx              #    输入区域
│   └── StatusBar.tsx              #    状态栏（连接状态、模型信息）
├── FileExplorer.tsx                # 文件浏览器（类似 VS Code）
├── TerminalEmulator.tsx            # 终端模拟器
├── AgentTraceViewer.tsx            # ★★★ Agent 追踪查看器
│   └── 展示完整的事件时间线
└── SettingsPanel.tsx               # 设置面板
```

---

## 四、最值得借鉴的 Top 5

### 🏆 #1 Docker Sandbox 安全隔离
- **来源**: `app_server/sandbox/local_sandbox.py`
- **核心思想**: Agent 所有操作都在独立 Docker 容器中执行
- **启示**: AutoCLI 可以增加可选的 Docker 模式
- **落地**: 后端增加 `sandbox_mode: "docker"` 配置项

### 🏆 #2 事件驱动的完整审计
- **来源**: `event_callback/`
- **核心思想**: 每个 Agent 操作都记录为结构化事件，支持回放和调试
- **启示**: 我们的 trajectory API 应记录更细粒度的事件
- **落地**: 增强 `backend/app/api/routes/agent/trajectory.py`

### 🏆 #3 多 Agent 协作模式
- **来源**: `resolver/` (BrowserAgent + CodeAgent + BashAgent)
- **核心思想**: 不同类型的任务由专门的 Agent 处理
- **启示**: 对应我们的 orchestrator (Planner→Coder→Reviewer)
- **已落地**: ✅ AgentPipeline.vue

### 🏆 #4 死循环检测
- **来源**: `BaseAgent.detect_loop()`
- **核心思想**: 检测重复的工具调用序列，自动中断
- **启示**: middleware.py 的 LoopDetection 已有此功能

### 🏆 #5 Skills 定义系统
- **来源**: `skills/` (27 个 Markdown 技能定义)
- **核心思想**: 用自然语言定义 Agent 能力，动态加载
- **启示**: 对应我们的 SkillManager + skills/

---

## 五、快速入门

```bash
cd D:\code\openhands

# 启动后端（需要 Docker）
make build
make start-backend

# 启动前端
cd frontend && npm install && npm run dev

# 访问 http://localhost:3000
```

**推荐阅读**:
1. `openhands/app_server/sandbox/` — 沙箱安全设计
2. `openhands/resolver/` — Agent 系统
3. `openhands/app_server/event_callback/` — 事件系统
4. `frontend/src/components/ChatPanel.tsx` — 聊天 UI
5. `skills/` — 技能定义格式参考
