# LangGraph — 有状态 Multi-Agent 工作流引擎

> **源码位置**: `D:\code\langgraph` | **大小**: 13 MB | **语言**: Python  
> **官网**: https://langchain-ai.github.io/langgraph/ | **Stars**: ~10k+  
> **定位**: LangChain 生态的有状态图工作流引擎，用于构建复杂 Agent 系统

---

## 一、项目概览

LangGraph 解决了一个关键问题：**如何编排多个 Agent 的协作流程**。它将 Agent 流程建模为 **有向图（State Graph）**，支持：

- 🔄 **循环** — Agent 可以多次调用工具直到完成
- 🔀 **分支** — 根据条件走不同路径
- 📊 **持久化** — 图的状态可以保存和恢复
- ⏸️ **暂停/恢复** — 人工审批节点
- 👥 **多人协作** — 多个用户同时交互

### 为什么研究 LangGraph？
我们的 `orchestrator.py` 已经实现了 Planner→Coder→Reviewer 流水线。LangGraph 提供了更通用的框架来：

1. **形式化定义流水线**（用 State Graph 替代硬编码 if/else）
2. **支持 Checkpointing**（断点续跑）
3. **支持分支路由**（不同任务走不同 Agent 组合）
4. **可视化调试**（Mermaid 图渲染）

### 核心概念
```
State (状态):       整个图的共享数据字典 {messages: [], files: [], ...}
Node (节点):        一个处理函数（如 planner_node, coder_node）
Edge (边):          节点之间的转移关系
Conditional Edge:   条件转移（根据 state 决定下一步去哪）
Checkpoint:         状态快照（用于暂停/恢复）
```

---

## 二、目录结构

```
D:\code\langgraph\
├── libs/
│   ├── langgraph/                 # ★★★ 核心库 ⭐⭐⭐
│   │   ├── src/langgraph/
│   │   │   ├── graph/state.py    #    StateGraph 类 ⭐⭐⭐
│   │   │   ├── graph/message.py  #    MessageGraph 类
│   │   │   ├── checkpoint/       #    ★★★ Checkpoint 系统 ⭐⭐
│   │   │   ├── preamble/         #    Preamble（预计算）
│   │   │   ├── channel/          #    通道（人机交互）
│   │   │   └── store/base.py     #    存储后端
│   │   └── tests/
│   ├── checkpoint/               # Checkpoint 接口定义
│   │   ├── sqlite/               #    SQLite 实现
│   │   └── postgres/             #    Postgres 实现
│   ├── prebuilt/                 # 预构建的 ReAct/Tool Agent
│   ├── sdk-py/                   # Python SDK
│   └── sdk-js/                   # JavaScript SDK
├── examples/                     # 示例（35 个 Jupyter Notebook）
└── docs/                         # 文档
```

---

## 三、核心模块深度解析

### 3.1 StateGraph — 核心数据结构 ⭐⭐⭐

```python
from langgraph.graph import StateGraph, END

# 1. 定义 State（共享数据）
from typing import TypedDict, Annotated
import operator

class AgentState(TypedDict):
    messages: Annotated[list, operator.add]  # 消息历史（累加）
    files_modified: list[str]                # 修改过的文件
    current_stage: str                        # 当前阶段
    reasoning_steps: list[dict]               # 推理步骤
    tool_calls: list[dict]                    # 工具调用记录
    error_count: int                          # 错误计数

# 2. 定义每个节点的处理函数
def planner_node(state: AgentState) -> dict:
    """规划阶段：分析需求，制定计划"""
    messages = state["messages"]
    plan = call_llm_for_plan(messages[-1])
    return {
        "reasoning_steps": [{"type": "planning", "content": plan}],
        "current_stage": "planning"
    }

def coder_node(state: AgentState) -> dict:
    """编码阶段：根据计划修改代码"""
    plan = get_last_reasoning(state)["content"]
    edits = call_llm_with_tools(plan, tools=[read_file, write_file, bash])
    apply_edits(edits)
    return {
        "files_modified": [e.file_path for e in edits],
        "tool_calls": [e.to_dict() for e in edits],
        "current_stage": "coding"
    }

def reviewer_node(state: AgentState) -> dict:
    """审查阶段：检查代码质量"""
    files = state["files_modified"]
    review = review_code(files)
    return {
        "reasoning_steps": [{"type": "review", "content": review}],
        "current_stage": "reviewing"
    }

# 3. 构建图
graph = StateGraph(AgentState)

# 添加节点
graph.add_node("planner", planner_node)
graph.add_node("coder", coder_node)
graph.add_node("reviewer", reviewer_node)

# 设置入口
graph.set_entry_point("planner")

# 添加边
graph.add_edge("planner", "coder")           # 规划 → 编码
graph.add_edge("coder", "reviewer")          # 编码 → 审查

# 条件边：审查通过则结束，否则回到编码
def should_continue(state: dict) -> str:
    review = state["reasoning_steps"][-1]
    if "APPROVED" in review["content"]:
        return END       # 结束
    else:
        return "coder"   # 回到编码重新修改

graph.add_conditional_edges("reviewer", should_continue)

# 4. 编译为可执行图
app = graph.compile()

# 5. 执行
result = app.invoke({
    "messages": [{"role": "user", "content": "添加用户认证功能"}],
    "files_modified": [],
    "current_stage": "",
    "reasoning_steps": [],
    "tool_calls": [],
    "error_count": 0,
})
```

**生成的流程图**:
```
         ┌─────────┐
         │ planner │
         └────┬────┘
              ▼
         ┌─────────┐
         │  coder  │◄──────────────┐
         └────┬────┘               │
              ▼                    │
         ┌──────────┐             │
         │ reviewer  │─────────────┘
         └────┬─────┘
              │ APPROVED?
              ├─ YES → END
              └─ NO ──→ coder
```

**与我们的 Orchestrator 对照**:

| 维度 | LangGraph StateGraph | 我们的 Orchestrator |
|------|---------------------|-------------------|
| 流程定义 | 声明式（图结构） | 命令式（if/else） |
| 状态管理 | 自动合并（Annotated） | 手动维护 |
| 分支 | Conditional Edges | mode 判断 |
| 暂停/恢复 | 内置 Checkpoint | ❌ 不支持 |
| 可视化 | Mermaid 图 | ❌ 无 |

### 3.2 Checkpoint 系统 (`libs/checkpoint/`) — ⭐⭐

```python
# Checkpoint 允许保存图执行的中间状态并恢复：

# 保存检查点
config = {"thread_id": "session-123"}
async for chunk in app.stream(input, config=config):
    print(chunk)

# 恢复到最后一个检查点
state = app.get_state(config)
print(state.values)  # 当时的完整 State

# 从特定检查点继续执行
app.invoke(None, config=config)  # None 表示从当前状态继续

# 回退到之前的检查点
for c in app.get_state_history(config):
    print(f"Checkpoint {c.config['checkpoint_id']}: step={c.metadata['step']}")
app.restore(c.config)  # 恢复到此点
```

**Checkpointer 实现**:

```python
# SQLite 版本（轻量，适合单机）
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

checkpointer = AsyncSqliteSaver.from_conn_string(":memory:")
app = graph.compile(checkpointer=checkpointer)

# Postgres 版本（生产环境）
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

checkpointer = AsyncPostgresSaver.from_conn_string(DATABASE_URL)
app = graph.compile(checkpointer=checkpointer)
```

### 3.3 Prebuilt Agents (`libs/prebuilt/`)

LangGraph 提供了开箱即用的 Agent 模板：

```python
from langgraph.prebuilt import create_react_agent

# 创建一个 ReAct Agent（思考→行动→观察 循环）
agent = create_react_agent(
    model="gpt-4o",
    tools=[search, calculator, weather],
)

# 直接使用
response = agent.invoke({"messages": ["今天北京天气如何？"]})
```

**内置 Agent 类型**:
- `create_react_agent` — 标准 ReAct 循环
- `create_tool_calling_agent` — Function Calling 模式
- `create_openai_functions_agent` — OpenAI 特定格式

---

## 四、最值得借鉴的 Top 5

### 🏆 #1 StateGraph 声明式流程
- **来源**: `libs/langgraph/src/langgraph/graph/state.py`
- **核心思想**: 用图结构替代 if/else，流程清晰可读
- **落地**: 重构 orchestrator.py 使用 StateGraph 模式
- **对应**: `AgentPipeline.vue` 已可视化了此流程

### 🏆 #2 Annotated State 合并
- **来源**: `operator.add` 自动合并消息列表
- **核心思想**: 每个节点只返回它负责的字段变化，框架自动 merge
- **启示**: 我们的 PipelineStage 结果也可以用此方式聚合

### 🏆 #3 Checkpoint 断点续跑
- **来源**: `libs/checkpoint/`
- **核心思想**: 保存任意中间状态，支持恢复和回滚
- **启示**: AgentRunner 可增加 checkpoint 功能

### 🏆 #4 Conditional Routing
- **来源**: `add_conditional_edges()`
- **核心思想**: 根据 State 动态决定下一步
- **启示**: agent_modes.py 的模式切换可以用此机制

### 🏆 #5 Channel 人机交互
- **来源**: `libs/langgraph/channel/`
- **核心思想`: 特殊的 `interrupt()` 节点，等待人工输入后继续
- **启示**: Tool Approval 就是这种模式的实现

---

## 五、快速入门

```bash
cd D:\code\langgraph
pip install -e ".[dev]"

# 运行示例
python examples/basic_agent.py
```

**推荐阅读**:
1. `libs/langgraph/src/langgraph/graph/state.py` — StateGraph 核心
2. `libs/checkpoint/sqlite/` — Checkpoint 实现
3. `examples/multi_agent/` — 多 Agent 协作示例
4. `libs/prebuilt/` — 预构建 Agent
