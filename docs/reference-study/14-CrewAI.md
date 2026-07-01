# CrewAI — 轻量 Multi-Agent 任务编排

> **源码位置**: `D:\code\crewAI` | **语言**: Python  
> **官网**: https://crewai.com | **Stars**: ~20k+  
> **定位**: 轻量级角色驱动多 Agent 协作框架，强调任务（Task）而非对话

---

## 一、项目概览

CrewAI 的核心理念与 AutoGen 不同：

| 维度 | AutoGen | CrewAI |
|------|---------|--------|
| 核心概念 | 对话 (Chat) | **任务 (Task)** |
| Agent 定义 | System Prompt | **Role + Goal + Backstory** |
| 协作方式 | 多轮 Group Chat | **任务分配 + 顺序执行** |
| 复杂度 | 较高（配置多） | **较低（直观）** |
| 适用场景 | 自由讨论型任务 | **结构化工作流** |

### 为什么研究？
我们的 Orchestrator 更接近 CrewAI 的模式 — **Planner→Coder→Reviewer 是一个结构化的任务流水线**。

---

## 二、核心用法

```python
from crewai import Agent, Task, Crew, Process

# ====== 定义 Agent (通过 Role + Goal) ======

planner = Agent(
    role="Technical Planner",
    goal="Break down complex requests into clear implementation plans",
    backstory="""You are a senior architect with 15 years of experience.
    You excel at analyzing requirements and creating structured plans.""",
    verbose=True,
    allow_delegation=True,     # 允许将任务委派给其他 Agent
    tools=[search_files, read_file],
)

coder = Agent(
    role="Senior Developer",
    goal="Write clean, efficient code following the provided plan",
    backstory="""You are a full-stack developer who writes production-quality code.""",
    verbose=True,
    allow_delegation=False,
    tools=[write_file, edit_file, execute_command],
)

reviewer = Agent(
    role="Code Reviewer",
    goal="Ensure code quality, security, and best practices",
    backstory="""You are a meticulous reviewer who catches bugs before they reach production.""",
    verbose=True,
    tools=[read_file, search_code, run_tests],
)

# ====== 定义 Task ======

task_plan = Task(
    description="Analyze requirements and create implementation plan",
    expected_output="A detailed step-by-step plan",
    agent=planner,
)

task_code = Task(
    description="Implement the feature according to the plan: {plan}",
    expected_output="Working code with tests",
    agent=coder,
    context=[task_plan],   # ★ 关键：依赖前置任务的输出
)

task_review = Task(
    description="Review code for bugs, security issues, and quality",
    expected_output="APPROVED or detailed feedback list",
    agent=reviewer,
    context=[task_code],  # ★ 审查编码任务的结果
)

# ====== 组装 Crew 并执行 ======

crew = Crew(
    agents=[planner, coder, reviewer],
    tasks=[task_plan, task_code, task_review],
    process=Process.sequential,   # 顺序执行
    # process=Process.hierarchical,  # 层级执行（Manager 分配任务）
    verbose=True,
)

result = crew.kickoff()  # 开始执行！
```

---

## 三、核心设计模式

### 3.1 Task 依赖链（Context）

```python
# Task 之间通过 context 建立数据流：
task_a = Task(description="...", agent=a)
task_b = Task(description="{task_a_output}", agent=b, context=[task_a])
task_c = Task(description="...", agent=c, context=[task_b])

# 执行顺序自动解析为 DAG：
# task_a → task_b → task_c
```

**对应**: 我们的 PipelineStage 有 `summary` 字段传递上下文

### 3.2 两种 Process 模式

```python
# Sequential — 线性流水线（我们当前的模式）
Process.sequential  
# Task1 → Task2 → Task3 → ...

# Hierarchical — Manager 分配任务
Process.hierarchical
"""
┌──────────┐
│ Manager   │ ← 高层 Agent 决定谁做什么
└─────┬────┘
      │ assigns to
 ┌────┼────┬──────┐
 ▼    ▼     ▼      ▼
Agt1 Agt2 Agt3   Agt4
(并行或串行由 Manager 决定)
"""
```

### 3.3 Tools 系统

```python
from crewai_tools import (
    FileReadTool,
    DirectorySearchTool,
    SerperDevTool,        # Web 搜索
    WebsiteSearchTool,    # 网页抓取
)

# 工具直接绑定到 Agent
agent_with_tools = Agent(
    tools=[
        FileReadTool(),          # 读取文件
        DirectorySearchTool(),   # 搜索目录
        SerperDevTool(),         # Google 搜索
    ]
)
```

---

## 四、值得借鉴的点

| 设计 | CrewAI 实现 | 我们的对应 |
|------|------------|-----------|
| Role + Goal + Backstory | 三维定义 Agent 人设 | PRESET_MODES 的 name/description/skills |
| Task context 依赖 | `context=[prev_task]` | PipelineStage 间 summary 传递 |
| Sequential 流水线 | `Process.sequential` | orchestrator.py 的固定流程 |
| allow_delegation | Agent 可委托其他 Agent | SubAgent handoff |
| expected_output | 明确的输出格式要求 | LLM response schema |

---

## 五、快速入门

```bash
cd D:\code\crewAI
pip install -e .
# 运行示例：python examples/basic.py
```
