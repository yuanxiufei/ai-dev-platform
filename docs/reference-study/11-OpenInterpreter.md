# Open Interpreter — 可执行 Agent UI（命令行执行专家）

> **源码位置**: `D:\code\open-interpreter` | **大小**: 52 MB | **语言**: Rust + TypeScript  
> **官网**: https://openinterpreter.com | **Stars**: ~50k+  
> **定位**: 让 LLM 直接控制你的电脑执行命令的自然语言接口

---

## 一、项目概览

Open Interpreter 的理念极其简单直接：

> **输入自然语言 → LLM 翻译成代码/命令 → 在本地执行 → 返回结果**

它的核心场景是：
- 💻 **系统命令执行** — "安装 numpy" → 自动运行 pip install
- 📊 **数据分析** — "画一个销售趋势图" → 生成 Python + matplotlib
- 🌐 **Web 操作** — "打开 Google 搜索 xxx" → 控制浏览器
- 📁 **文件操作** — "把所有 .py 文件移到 src/" → 执行 shell 命令

### 技术栈演变
```
v1: Python (纯 Python 实现，简单但功能有限)
v2: Rust 重写核心 (codex-rs/)     ← 当前主要代码在此！
    + TypeScript (SDK + CLI)
```

---

## 二、目录结构

```
D:\code\open-interpreter/
├── codex-rs/                    # ★★★ Rust 核心引擎 ⭐⭐⭐
│   ├── src/
│   │   ├── main.rs             #    入口
│   │   ├── interpreter/         #    ★★★ 解释器主循环 ⭐⭐⭐
│   │   │   └── mod.rs          #       ReAct 循环实现
│   │   ├── tools/               #    内置工具集
│   │   │   ├── bash.rs         #    Shell 命令执行 ⭐
│   │   │   ├── file_edit.rs    #    文件编辑
│   │   │   └── ...
│   │   ├── approval/            #    ★★★ 审批系统 ⭐⭐⭐
│   │   │   └── mod.rs          #       工具审批逻辑
│   │   └── config/              #    配置管理
│   └── ...                      #    大量 .rs 文件 (2330 个)
├── sdk/                         # TypeScript SDK
├── scripts/                     # 辅助脚本
├── tools/                       # 额外工具
└── docs/                        # 文档 (48 页)
```

---

## 三、核心模块

### 3.1 Interpreter 主循环 (`codex-rs/src/interpreter/mod.rs`) — ⭐⭐⭐

```rust
// Open Interpreter 的核心是经典的 ReAct 循环：
struct Interpreter {
    model: String,               // 模型名
    tools: Vec<Tool>,             // 可用工具列表
    messages: Vec<Message>,       // 对话历史
    approval_mode: ApprovalMode, // 审批模式
}

impl Interpreter {
    async fn chat(&mut self, user_input: &str) -> Result<String> {
        // 1. 添加用户消息
        self.messages.push(Message::user(user_input));
        
        loop {
            // 2. 调用 LLM（包含所有历史 + 工具描述）
            let response = self.call_llm(&self.messages).await?;
            
            // 3. 解析响应
            match response {
                // 纯文本回复 → 返回给用户
                Response::Text(text) => {
                    self.messages.push(Message::assistant(&text));
                    return Ok(text);
                }
                
                // 工具调用 → 执行审批流程
                Response::ToolCall(call) => {
                    // 4a. 检查是否需要审批
                    if self.needs_approval(&call) {
                        let approved = self.request_approval(&call).await?;
                        if !approved {
                            continue; // 用户拒绝 → 继续循环让 LLM 尝试其他方式
                        }
                    }
                    
                    // 4b. 执行工具
                    let result = self.execute_tool(&call).await?;
                    
                    // 5. 将结果追加到消息历史
                    self.messages.push(Message::tool_result(result));
                    
                    // 6. 继续循环（LLM 看到结果后决定下一步）
                }
            }
        }
    }
}
```

### 3.2 审批系统 (`codex-rs/src/approval/mod.rs`) — ⭐⭐⭐

这是 Open Interpreter 最关键的 UI 交互：

```rust
enum ApprovalMode {
    /// 每个工具调用都询问用户
    Ask,
    
    /// 只对危险操作询问（rm、sudo 等）
    SafeEdits,
    
    /// 不询问，全部自动执行（危险！）
    AutoRun,
    
    /// 根据工具类型智能判断
    Smart,
}

// 安全级别判定（类似我们的 AutoCLI）:
fn get_tool_risk_level(tool_name: &str) -> RiskLevel {
    match tool_name {
        // 🟢 SAFE — 只读操作，无副作用
        "read_file" | "list_dir" | "search" => RiskLevel::Safe,
        
        // 🟡 MODERATE — 有修改但可逆
        "write_file" | "edit_file" | "create_file" => RiskLevel::Moderate,
        
        // 🔴 DANGEROUS — 不可逆或影响全局
        "bash" | "execute_command" => RiskLevel::Dangerous,
        "delete_file" | "remove_directory" => RiskLevel::Dangerous,
        _ => RiskLevel::Unknown,
    }
}

// 审批请求 UI（终端展示）:
// ══════════════════════════════════════
//  Open Interpreter wants to run:
//
//  $ rm -rf node_modules/
//  
//  This is a DANGEROUS operation.
//
//  [y] Yes  [n] No  [a] Always allow rm  [x] Exit
// ══════════════════════════════════════
```

### 3.3 Bash 工具执行 (`codex-rs/src/tools/bash.rs`) — ⭐⭐

```rust
struct BashTool {
    timeout: Duration,           // 默认 120 秒超时
    allowed_commands: Vec<Regex>, // 白名单（可选）
    blocked_patterns: Vec<Regex>, // 黑名单（危险字符检测）
}

impl Tool for BashTool {
    async fn execute(&self, command: &str) -> ToolResult {
        // 1. 注入检测（类似我们的 AutoCLI）
        for pattern in &self.blocked_patterns {
            if pattern.is_match(command) {
                return Err(ToolError::Blocked(
                    "Command contains dangerous characters"
                ));
            }
        }
        
        // 2. 超时保护
        let output = tokio::time::timeout(
            self.timeout,
            Command::new("bash").arg("-c").arg(command).output()
        ).await;
        
        match output {
            Ok(Ok(output)) => ToolResult {
                stdout: String::from_utf8_lossy(&output.stdout),
                stderr: String::from_utf8_lossy(&output.stderr),
                exit_code: output.status.code(),
            },
            Ok(Err(_)) => ToolError::TimedOut(self.timeout),
            Err(_) => ToolError::Cancelled,
        }
    }
}
```

---

## 四、最值得借鉴的点

### 🏆 #1 分级审批 + Always Allow 记忆
- 用户可以对特定操作设置 "Always allow"，避免重复确认
- **我们的落地**: AgentChat.vue 已有基础 approveTool/rejectTool

### 🏆 #2 危险字符注入检测
- 正则匹配 `;|&|$()` 等危险字符
- **对应**: 我们的 AutoCLI `DANGEROUS_CHARS` 已实现 ✅

### 🏆 #3 超时保护
- 所有命令都有默认超时时间
- **启示**: AutoCLI 应增加 timeout 参数

### 🏆 #4 流式输出展示
- 命令输出实时流式显示给用户
- **落地**: SSE chunk 事件已支持

---

## 五、快速入门

```bash
cd D:\code\open-interpreter
# Python 版本（简单）
pip install open-interpreter
interpreter

# 或构建 Rust 版本
cd codex-rs && cargo build --release && cargo run
```
