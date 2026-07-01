# AutoGen — 微软多 Agent 对话框架

> **源码位置**: `D:\code\autogen` | **语言**: Python  
> **官网**: https://github.com/microsoft/autogen | **Stars**: ~30k+  
> **定位**: 微软出品的多 Agent 对话框架，专注于 Agent 间的角色协作与工具调用

---

## 一、项目概览

AutoGen 解决的核心问题：

> **如何让多个 AI Agent 之间进行结构化对话来完成复杂任务？**

它的关键概念：
- 👥 **ConversableAgent** — 每个 Agent 有独立的 System Prompt、工具集、人设
- 💬 **多轮对话** — Agent 之间可以来回对话（不只是单向调用）
- 🔧 **工具使用 (Function Calling)** — Agent 可以调用 Python 函数作为工具
- 👨‍💻 **人类参与** — Human-in-the-loop，用户可以在任意时刻介入对话
- 📊 **代码执行** — 内置安全沙箱执行 Python 代码

### 与我们的 Orchestrator 对照

```
AutoGen                      ↔  我们的系统
───────────────────────────────────────────
ConversableAgent             ↔  Agent Mode (Planner/Coder/Reviewer)
GroupChat (多Agent 对话)      ↔  AgentPipeline
HumanProxyAgent (人工介入)   ↔  Tool Approval Bar
FunctionTool (工具调用)      ↔  AutoCLI + ToolRegistry
CodeExecutor (代码执行)      ↔  Sandbox
```

---

## 二、核心用法速览

```python
import autogen
from autogen import ConversableAgent, UserProxyAgent, GroupChat, GroupChatManager

# ====== 定义 Agent ======

# 用户代理（代表用户，可以确认/拒绝操作）
user_proxy = UserProxyAgent(
    name="user",
    human_input_mode="ALWAYS",  # 总是需要用户确认
    code_execution_config={
        "work_dir": "workspace",
        "use_docker": False,      # 不使用 Docker
    },
)

# 编码 Agent（负责写代码）
coder = ConversableAgent(
    name="coder",
    system_message="""You are an expert Python developer.
    Write clean, well-documented code.
    Always explain your approach before writing.""",
    llm_config={"config_list": [{"model": "gpt-4o", "api_key": "..."}]},
)

# Reviewer Agent（负责审查代码）
reviewer = ConversableAgent(
    name="reviewer",
    system_message="""You are a senior code reviewer.
    Check for: bugs, security issues, performance problems.
    Respond with APPROVED or specific feedback.""",
    llm_config={"config_list": [{"model": "gpt-4o", "api_key": "..."}]},
)

# ====== 多 Agent 对话 ======

# 方式 1: 两 Agent 直接对话
user_proxy.initiate_chat(
    coder,
    message="Write a function to merge two sorted lists.",
    max_turns=10,  # 限制最大轮次
)

# 方式 2: Group Chat（多 Agent 协作）
groupchat = GroupChat(
    agents=[user_proxy, coder, reviewer],
    messages=[],
    max_round=20,
    speaker_selection_method="round_robin"  # 或 "auto"
)

manager = GroupChatManager(groupchat=groupchat)

# 开始群聊
user_proxy.initiate_chat(
    manager,
    message="Build a REST API with user auth.",
)
```

---

## 三、核心设计模式

### 3.1 Agent 角色 System Prompt

AutoGen 强调通过 **System Prompt 定义 Agent 人设**：

```python
# Planner Agent
planner = ConversableAgent(
    system_message="""
You are a Planning Agent. Your role:
1. Analyze the user's request thoroughly
2. Break down into subtasks with dependencies
3. Create a step-by-step execution plan
4. Identify potential risks and edge cases
5. Output plan in structured format:
   ## Plan
   ### Step 1: [description]
   - Files to modify: [...]
   - Dependencies: [...]
   
DO NOT write any code. Only produce plans.
"""
)

# Coder Agent
coder = ConversableAgent(
    system_message="""
You are a Coding Agent. Your role:
1. Read the plan from the planner
2. Implement each step carefully
3. Write production-quality code
4. Add error handling and tests
5. Report what files were changed
"""
)

# Tester Agent  
tester = ConversableAgent(
    system_message="""
You are a Testing Agent. Your role:
1. Review the code changes
2. Write unit tests
3. Run the tests and report results
4. If tests fail, describe the bug clearly
"""
)
```

**对应**: 我们的 `agent_modes.py` 中 PRESET_MODES 的 skills + description 就是这种模式！

### 3.2 Human-in-the-Loop

```python
# 三种人机交互模式：
human_input_mode = (
    "NEVER",      # 全自动，不需要人
    "TERMINATE",  # 仅在终止时需要人确认
    "ALWAYS",     # 每一步都需要人确认  ← 最安全
)

# ALWAYS 模式的效果：
# Coder: 我准备创建一个新文件 utils/auth.py
# >>> 请确认是否继续？ [y/n]
# User: y
# Coder: 正在写入文件... 完成
# Coder: 现在运行 pip install bcrypt
# >>> 请确认是否继续？ [y/n]
# User: n  ← 用户拒绝
# Coder: 好的，我将跳过安装步骤...
```

### 3.3 工具调用 (Function Calling)

```python
# 定义工具（Python 函数）
@user_proxy.register_for_llm(description="Search for code symbols") 
def search_symbols(query: str) -> str:
    """Search codebase for classes/functions matching query."""
    results = codebase_search(query)
    return json.dumps(results)

@user_proxy.register_for_llm(description="Read file contents")  
def read_file(path: str) -> str:
    """Read and return file content."""
    with open(path) as f:
        return f.read()

@user_proxy.register_for_llm(description="Execute shell command")
def run_command(cmd: str) -> str:
    """Run a shell command and return output."""
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return result.stdout or result.stderr
```

### 3.4 对话历史与上下文

```python
# AutoGen 自动维护对话历史
# 每个 Agent 有自己的消息历史，GroupChat 有共享历史

# 获取对话摘要
summary = chat.summary  # 最后 N 条消息的摘要

# 重置对话
chat.reset()

# 代价控制（防止无限循环）
cost_guardrails = {
    "max_total_cost": 5.0,      # 最大花费 $5
    "count_tokens": True,       # 统计 token
}
```

---

## 四、值得借鉴的点

### 🏆 #1 System Prompt 定义 Agent 人设
- **落地**: 我们的 agent_modes.py PRESET_MODES 已经在做这个 ✅

### 🏆 #2 Human Input Mode 三级控制
- NEVER / TERMINATE / ALWAYS
- **落地**: Tool Approval Bar 的 auto-approve 模式

### 🏆 #3 Group Chat 轮流机制
- round_robin / auto / manual / custom
- **落地**: orchestrator.py 的流水线调度

### 🏆 #4 @register_for_llm 工具注册
- 用 Python decorator 注册工具，自动生成描述
- **落地**: registry.py 的 ToolRegistry

### 🏆 #5 Cost Guardrails
- 自动追踪 token 和费用，超限停止
- **落地**: usage SSE event
