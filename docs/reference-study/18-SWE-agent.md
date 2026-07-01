# SWE-agent — Issue→Fix 学术级 Agent

> **源码位置**: `D:\code\swe-agent` | **大小**: 34 MB | **语言**: Python  
> **官网**: https://princeton-nlp.github.io/SWE-agent/ | **出品**: Princeton NLP  
> **定位**: 将 GitHub Issue 自动转化为代码修复 Patch 的学术级 Agent 系统

---

## 一、项目概览

SWE-agent 解决了一个非常具体的问题：

> **给定一个 GitHub Issue（bug 报告），自动找到相关代码并生成修复补丁**

它在 SWE-bench（Software Engineering Benchmark）上取得了顶尖成绩。其核心创新：

🔍 **Agent-Computer Interface (ACI)** — 专门为 Agent 设计的操作接口（不是给人用的！）
📝 **上下文窗口管理** — 智能选择哪些文件内容放入 prompt（避免超出 token 限制）
🔄 **反馈循环** — Agent 操作后获得环境反馈，持续迭代直到修复成功
📊 **严格评测** — 每个 Issue 有确定的 ground truth patch

### 与我们项目的关联
SWE-agent 的 **ACI 设计** 和 **上下文窗口管理** 对我们的 CodebaseMemory 和 Agent Runner 有重要参考价值。

---

## 二、目录结构

```
D:\code\swe-agent\
├── sweagent/                   # ★★★ 核心包
│   ├── agent/                 #    ★★★ Agent 核心 ⭐⭐⭐
│   │   ├── agents.py          #       Agent 定义和主循环
│   │   ├── models.py          #       模型封装
│   │   ├── history_processors.py  # 历史处理（压缩/截断）
│   │   └── hooks.py           #       生命周期钩子
│   ├── tools/                 #    ★★★ ACI 工具集 ⭐⭐
│   │   ├── tools.py           #       工具定义
│   │   └── execution.py       #       工具执行引擎
│   ├── config/                #    ★ 配置文件（25 个 YAML）
│   │   ├── default_tools.yaml #    默认 ACI 工具定义
│   │   └── default_model.yaml #    默认模型配置
│   └── utils/                 #    工具函数
├── config/                     # 更多配置模板
├── tests/                      # 测试套件
├── tools/                      # 辅助工具（Docker 等）
└── trajectories/               # 保存的成功轨迹（可用于 replay）
```

---

## 三、核心模块

### 3.1 ACI (Agent-Computer Interface) — ⭐⭐⭐

SWE-agent 最大的贡献是设计了 **专门给 Agent 用的文件操作接口**：

```yaml
# config/default_tools.yaml 定义的 ACI 工具：
tools:
  # ====== 文件浏览 ======
  - name: search_files
    description: "Search for regex pattern in files"
    input_schema:
      path: { type: string }        # 搜索路径
      pattern: { type: string }     # 正则表达式
      file_pattern: { type: string } # 文件过滤 (*.py)

  - name: read_file
    description: "Read file contents with line numbers"
    input_schema:
      path: { type: string }        # 文件路径
      offset: { type: integer, default: 0 }  # 起始行
      limit: { type: integer, default: 100 }  # 行数限制 ⭐ 关键！

  - name: list_files
    description: "List files in directory (recursive)"
    input_schema:
      path: { type: string }

  - name: list_code_definitions
    description: "List function/class definitions in file"
    input_schema:
      path: { type: string }

  # ====== 文件编辑 ======
  - name: edit_file
    description: "Edit file using SEARCH/REPLACE blocks"
    input_schema:
      path: { type: string }
      old_string: { type: string }  # 要替换的内容
      new_string: { type: string }  # 新内容
      pattern: { type: string }     # 正则匹配（可选）

  - name: create_file
    description: "Create new file"
    input_schema:
      path: { type: string }
      content: { type: string }

  - name: delete_file
    description: "Delete file"

  # ====== 执行 ======
  - name: execute_command
    description: "Execute shell command"
    input_schema:
      command: { type: string }

  - name: submit
    description: "Submit fix and verify against tests"
```

**ACI vs 普通 CLI 的区别**:

| 维度 | 普通 CLI | ACI (SWE-agent) |
|------|---------|----------------|
| 输出格式 | 人读的文本 | 结构化 JSON |
| 文件读取 | cat（全文） | **read_file(limit=100)** — 受控！ |
| 错误处理 | 看 stderr | 结构化 error code |
| 上下文感知 | 无 | 自动截断避免 token 超限 |

### 3.2 上下文窗口管理 — ⭐⭐⭐

这是 SWE-agent 的核心技术之一：

```python
# 问题：一个 repo 可能有几千个文件，不可能全塞进 context
# 方案：分层策略

class ContextWindowManager:
    def __init__(self, max_tokens: int = 128000):
        self.max_tokens = max_tokens
        self.current_tokens = 0
        self.file_cache = {}  # 缓存已读取的文件
    
    def manage_context(self, agent_state):
        """确保总 token 数不超过限制"""
        while self.estimate_tokens(agent_state) > self.max_tokens:
            # 策略 1: 截断最早的文件读取结果
            self.truncate_oldest_file_read(agent_state)
            
            # 策略 2: 如果还不够，压缩早期历史消息
            if still_over_limit:
                self.summarize_early_history(agent_state)
                
            # 策略 3: 最后手段 — 截断工具结果
            if still_over_limit:
                self.truncate_tool_results(agent_state)
    
    def smart_read(self, path, offset=0, limit=100):
        """受控的文件读取"""
        lines = read_lines(path, offset, limit)
        
        # 重要优化：告诉 Agent 还有更多内容
        total_lines = count_lines(path)
        if offset + limit < total_lines:
            lines.append(f"\n... ({total_lines - offset - limit} more lines, use offset={offset + limit} to read more)")
        
        return "\n".join(f"{i+offset}: {line}" for i, line in enumerate(lines))
```

**关键洞察**:
- `read_file` 默认只返回 **100 行**（不是全文！）
- 末尾提示 Agent 如何获取更多内容
- 这避免了读取大文件时爆掉 context window

### 3.3 Agent 主循环

```python
# sweagent/agent/agents.py

class SWEAgent:
    def run(self, issue_description: str) -> FixResult:
        # Phase 1: Setup — 从 GitHub clone repo，checkout 到 issue 对应 commit
        env = self.setup_environment(issue_description)
        
        # Phase 2: Exploration — Agent 分析 issue，探索代码
        history = []
        history.append({"role": "system", "content": BUILD_SYSTEM_PROMPT})
        history.append({"role": "user", "content": f"Issue: {issue_description}"})
        
        for step in range(MAX_STEPS):
            # 3. 调用 LLM（含完整历史 + 工具描述）
            response = llm.chat(history, tools=ACI_TOOLS)
            
            # 4. 解析 action
            action = parse_action(response)
            
            if action.type == "submit":
                # Agent 认为修复完成了
                break
            
            # 5. 执行工具
            result = execute_action(env, action)
            
            # 6. 环境反馈（关键！）
            feedback = generate_feedback(env, action, result)
            # 例如：运行测试看看是否通过
            
            # 7. 更新历史
            history.append(tool_call_message(action, result, feedback))
            
            # 8. 上下文管理（防止超限）
            context_manager.manage_context(history)
        
        # Phase 3: 验证 — 运行测试套件检查是否真的修好了
        test_result = env.run_tests()
        
        return FixResult(patch=env.get_diff(), passed=test_result.passed)
```

### 3.4 Trajectory Replay（轨迹回放）

```python
# SWE-agent 会保存成功的修复轨迹，可以回放学习
# trajectories/*.traj 文件记录了完整的 Agent 操作序列

def save_trajectory(session_id, steps):
    """保存一次成功的修复过程"""
    trajectory = {
        "session_id": session_id,
        "issue": current_issue,
        "steps": [  # 每步包含：
            {"thought": llm_response, "action": tool_call, "result": tool_output},
            ...
        ],
        "final_patch": generated_diff,
        "test_result": "PASS",
    }
    save_json(f"trajectories/{session_id}.traj", trajectory)

def replay_trajectory(traj_path):
    """回放轨迹（用于调试和学习）"""
    traj = load_json(traj_path)
    for step in traj["steps"]:
        print(f"\n--- Step {step['index']} ---")
        print(f"Thought: {step['thought']}")
        print(f"Action: {step['action']}")
        print(f"Result: {step['result'][:200]}...")
```

---

## 四、最值得借鉴的点

### 🏆 #1 受控文件读取 (limit + offset)
- **来源**: `read_file` 工具设计
- **核心思想**: 默认只返回 100 行，末尾提示还有更多
- **落地**: CodebaseMemory 的查询结果应做同样处理

### 🏆 #2 上下文窗口自动管理
- **来源**: `ContextWindowManager`
- **核心思想**: 三层截断策略 — 旧文件→旧历史→工具结果
- **落地**: Roo Code 的 Condense + 我们 MemoryStore 结合

### 🏆 #3 环境反馈循环
- **来源**: `generate_feedback()`
- **核心思想**: 每次 Action 后自动运行相关测试，反馈给 Agent
- **落地**: orchestrator 的 Reviewer stage 就是这种机制

### 🏆 #4 Trajectory 保存与回放
- **来源**: `trajectories/`
- **核心思想**: 成功案例存档，可回放学习和调试
- **落地**: trajectory.py API 可增强为完整轨迹存储

### 🏆 #5 ACI 工具设计哲学
- **来源**: `config/default_tools.yaml`
- **核心思想**: 工具是为 Agent 设计的，不是为人设计的（结构化输出、受控返回）
- **落地**: registry.py 的 FunctionTool Schema 已遵循此原则
