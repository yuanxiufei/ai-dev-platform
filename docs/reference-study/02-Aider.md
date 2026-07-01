# Aider — Git-aware AI Coding Agent

> **源码位置**: `D:\code\aider` | **大小**: 74 MB | **语言**: Python  
> **官网**: https://aider.chat | **Stars**: ~25k+  
> **定位**: 终端 AI 编程助手，Git 原生集成，自动生成高质量 diff patch

---

## 一、项目概览

Aider 是一个 **纯终端的 AI 编程 Agent**，没有 GUI，完全在命令行工作。它的核心理念是：

> **每一次 AI 修改都通过 Git diff 来呈现和管理**

这意味着：
- ✅ 每次修改都是原子性的（一个 commit）
- ✅ 可以 `git revert` 撤销任何一次修改
- ✅ 可以 `git diff` 查看每次变更的具体内容
- ✅ 支持多文件同时编辑
- ✅ 自动处理冲突

### 核心能力
- 🔄 **Git 原生集成** — 每次操作都产生 commit
- 📝 **Multi-file Editing** — 一次性修改多个文件
- 🎯 **Repo Map** — 自动生成代码库地图作为上下文
- 💬 **Architect Mode** — 先规划再执行的分层模式
- 🗣️ **Voice Mode** — 语音输入（Whisper）
- 📊 **Cost Control** — 实时显示 token 消耗和费用

### 技术栈
```
语言: Python (纯标准库 + requests)
前端: 终端 UI (rich 库)
模型: OpenAI/Anthropic/本地/任意兼容 API
版本控制: Git（核心依赖）
```

---

## 二、目录结构

```
D:\code\aider/
├── aider/                       # ★★★ 核心包
│   ├── main.py                 #    入口
│   ├── main_loop.py            #    ★★★ Agent 主循环
│   ├── coders/                 #    编码器（不同模型的适配）
│   │   ├── base_coder.py       #    基类（定义接口规范）
│   │   ├── openai_coder.py     #    OpenAI 适配
│   │   ├── anthropic_coder.py  #    Claude 适配
│   │   ├── editblock_coder.py  #    编辑块模式
│   │   └── ...
│   ├── diffs.py                #    ★★★ Diff 引擎
│   ├── repo.py                 #    ★★ Repo 上下文加载
│   ├── repomap.py             #    ★★ 代码库地图生成
│   ├── models.py               #    模型配置与管理
│   ├── llm.py                  #    LLM 调用封装
│   ├── prompts.py              #    Prompt 模板
│   ├── scrape.py               #    网页抓取
│   ├── io.py                   #    输入/输出处理
│   ├── voice.py                #    语音输入
│   ├── history.py              #    对话历史
│   ├── watch.py                #    文件监听
│   ├── commands.py             #    斜杠命令
│   ├── format_settings.py      #    格式设置
│   └── reasoning_tags.py       #    推理标签解析
├── tests/                       # 测试套件
├── requirements/                # 依赖定义
└── scripts/                     # 辅助脚本
```

---

## 三、核心模块深度解析

### 3.1 Agent 主循环 (`aider/main_loop.py`) — ⭐⭐⭐

Aider 的主循环简洁而高效：

```python
# 伪代码
def main_loop():
    while True:
        # 1. 获取用户输入
        user_input = get_input()
        
        # 2. 加载 Repo Context（代码库地图 + 最近修改的文件）
        context = repo.get_context()
        
        # 3. 构建 Messages（System + History + Context + User Input）
        messages = build_messages(context, history, user_input)
        
        # 4. 调用 LLM
        response = llm.call(messages)
        
        # 5. 解析响应 — 提取文件修改指令
        edits = parse_edits(response)  # 返回 [(file_path, old_text, new_text), ...]
        
        # 6. 应用修改（带 git 操作）
        for (path, old, new) in edits:
            if not file_exists(path):
                git_add(path)           # 新文件 → git add
            apply_edit(path, old, new)  # 应用修改
            
        # 7. Git Commit
        git_commit(edits, message=auto_generate_commit_msg(response))
        
        # 8. 显示 Diff 给用户
        show_diff(git.diff HEAD~1..HEAD)
```

**关键设计决策**:
- 每次 AI 修改 = 一个 git commit
- 用户可以用标准 git 命令管理所有修改
- 支持 `/undo` 撤销上一次操作（git reset HEAD~1）

### 3.2 Diff 引擎 (`aider/diffs.py`) — ⭐⭐⭐

Aider 使用 **搜索-替换模式**（而非 unified diff）来表示代码修改：

```python
# Aider 的 Edit 格式：
# <<<<<<< SEARCH
# def hello():
#     print("old")
# =======
# def hello():
#     print("new")
# >>>>>>> REPLACE

# diffs.py 核心逻辑：
def apply_edits(original_text, edits):
    """
    edits: [(search_str, replace_str), ...]
    按 order 依次应用，支持 fuzzy matching（容错匹配）
    
    关键特性：
    1. Fuzzy Match — 如果 search_str 不能精确匹配，
       会尝试忽略空白差异进行匹配
    2. Conflict Detection — 如果同一个 region 被多次修改，
       会检测到冲突并报错
    3. Undo Support — 保存逆操作，支持撤销
    """
    result = original_text
    for search, replace in edits:
        result = fuzzy_replace(result, search, replace)
    return result
```

**与标准 Diff 的区别**:

| 维度 | Unified Diff | Aider Search-Replace |
|------|-------------|---------------------|
| 表示形式 | `-old` `+new` 行级 | `<<<<<<< SEARCH` 块级 |
| 精确度 | 行号敏感 | 内容匹配（fuzzy） |
| 可读性 | 需要训练 | 更自然，像 Find-Replace |
| 冲突处理 | 标准 git conflict | 自定义检测 |

### 3.3 Repo Map (`aider/repomap.py`) — ⭐⭐

自动生成 **代码库结构地图** 作为 LLM 上下文：

```python
class RepoMap:
    """生成紧凑的代码库表示，让 LLM 了解整体结构"""
    
    def generate_map(self):
        # 1. AST 分析所有文件
        trees = parse_all_source_files()
        
        # 2. 提取顶层符号（class, function, const）
        symbols = extract_symbols(trees)
        
        # 3. 构建层级结构
        tree = build_symbol_tree(symbols)
        
        # 4. 格式化为紧凑文本
        map_text = format_tree(tree)
        
        # 示例输出：
        """
        src/
        ├── main.py
        │   ├── class App
        │   │   ├── def __init__(config)
        │   │   └── async def run()
        │   └── def main()
        ├── api/
        │   ├── routes.py
        │   │   ├── def get_users()
        │   │   └── def create_user(data)
        │   └── schemas.py
        │       └── class UserSchema
        └── utils/
            └── helpers.py
                └── def format_date(d)
        """
        
        return map_text
```

**与我们的 CodebaseMemory 对照**:
```
Aider RepoMap          →  我们的 CodeGraph (codebase_memory/)
AST 提取符号            →  TreeSitterParser + PythonParser
层级树形结构            →  Node/Edge 图结构
纯文本格式              →  SQLite 持久化 + 图查询
```

### 3.4 Coder 基类 (`aider/coders/base_coder.py`)

```python
class BaseCoder:
    """所有模型适配器的基类"""
    
    def __init__(self, model, io, repo):
        self.model = model
        self.io = io          # 终端 I/O
        self.repo = repo      # Git 仓库
    
    # 核心方法（子类必须实现）:
    def send_messages(self, messages) -> str:
        """调用 LLM，返回完整响应"""
        raise NotImplementedError
    
    def parse_response(self, response) -> List[Edit]:
        """将 LLM 响应解析为编辑操作列表"""
        raise NotImplementedError
    
    def apply_edits(self, edits):
        """应用编辑操作到文件"""
        for edit in edits:
            self.apply_one_edit(edit)
            self.repo.git_add(edit.file_path)
    
    def commit(self, message=None):
        """提交所有修改"""
        if message is None:
            message = self.auto_generate_commit_message()
        self.repo.git_commit(message)
    
    def undo(self):
        """撤销上一次操作"""
        self.repo.git_reset("HEAD~1")
```

**子类实现**:
- `OpenAICoder`: 使用 OpenAI function calling / structured output
- `AnthropicClaude`: 使用 Claude 的 XML tag 格式
- `EditBlockCoder`: 通用搜索-替换模式（适用于任何模型）

---

## 四、最值得借鉴的 Top 5

### 🏆 #1 Git-Native 编辑
- **来源**: `main_loop.py` + `diffs.py`
- **核心思想**: 每次修改 = 一个 commit
- **启示**: 我们的 Agent 执行完代码修改后应自动 git commit
- **落地**: 在 `orchestrator.py` 的 `_save_to_memory()` 之后加一步 `git_auto_commit()`

### 🏆 #2 Repo Map 上下文
- **来源**: `repomap.py`
- **核心思想**: 先给 LLM 看全局结构图，再让它深入细节
- **启示**: CodebaseMemory 的 `search_graph()` 应优先返回符号树
- **落地**: 增强 indexer.py 的符号提取能力

### 🏆 #3 Fuzzy Replace Diff
- **来源**: `diffs.py`
- **核心思想**: 内容匹配代替行号匹配，容忍空白差异
- **启示**: DiffViewer 可增加 fuzzy match 模式
- **落地**: 当 AI 生成的 diff 行号不准时自动调整

### 🏆 #4 Architect 模式（先规划再执行）
- **来源**: `commands.py` (/architect)
- **核心思想**: 两步走 — Plan（只读分析）→ Implement（实际修改）
- **启示**: 对应我们的 Planner → Coder 流水线
- **落地**: `AgentPipeline.vue` 已可视化此流程

### 🏆 #5 成本透明化
- **来源**: `io.py`（实时显示费用）
- **核心思想**: 每次请求后立即显示 token 数和估算成本
- **启示**: AgentRunDashboard 应增加 Cost 卡片
- **落地**: `usage` 事件已有字段，UI 展示即可

---

## 五、快速入门

```bash
cd D:\code\aider
pip install -e .

# 启动（指定模型和目录）
aider --model gpt-4o --no-auto-commits ./my-project

# 常用选项
aider --architect          # Architect 模式（先规划再执行）
aider --voice-always       # 总是用语音输入
aider --dark-mode          # 深色终端主题
```

**推荐阅读**:
1. `aider/main_loop.py` → Agent 主循环（~200 行，非常清晰）
2. `aider/diffs.py` → Diff 引擎（fuzzy replace 核心算法）
3. `aider/repomap.py` → 代码库地图生成
4. `aider/coders/base_coder.py` → Coder 基类接口
5. `aider/prompts.py` → System Prompt 模板
