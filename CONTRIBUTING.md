# 贡献指南

感谢你有意为 AI Fullstack Platform 做贡献！🙇

## 项目概述

- **Studio**：AI 编程工具（截图→代码、自然语言→全栈项目、AI 对话）
- **Video**：AI 视频生成工具（文字→视频、UI 演示视频、视频管理）
- **System**：模型管理、GPU 监控、健康检查、远程控制

基于 FastAPI + Vue 3 / React 19，集成智能模型调度（本地优先 + 五层回退链）。

## 大改动请先讨论

对于**大改动**（新功能、架构调整、重大重构），请先发起 [GitHub Discussion](https://github.com/raymondtxw/ai-fullstack-platform/discussions) 讨论。这样可以让社区和维护者提前给出反馈，避免白费功夫。

以下小改动可以直接提 PR，无需提前讨论：

- 拼写和语法修复
- 小幅可复现的 Bug 修复
- Lint 警告或类型错误修复
- 微小的代码改进（如删除无用代码）

> 非团队成员不允许修改 `pyproject.toml` 或 `uv.lock`，防止供应链风险。
> 如需新增依赖，请发起 [Discussion](https://github.com/raymondtxw/ai-fullstack-platform/discussions) 说明原因。

## 开发环境

关于开发环境搭建、启动方式、代码检查、pre-commit 等详情，见 [开发指南](development.md)。

## Pull Request 规范

提交 PR 时请注意：

1. 确保所有测试通过后再提交。
2. 每个 PR 聚焦单一改动。
3. 如果修改了功能，请同步更新测试。
4. 在 PR 描述中引用相关 Issue。

## AI 与自动化工具的使用

我们鼓励你使用各类工具（包括 AI/LLM）高效地完成工作。但贡献中应包含有意义的人工干预和判断。

如果一次 PR 中人类投入的心力（比如写 LLM 提示词），**远小于**我们审查所需的心力，请**不要**提交。

换种说法：我们自己也能写 LLM 提示词或运行自动化工具，而且比审查外部 PR 更快。

### AI 生成 PR 的处理

如果我们发现疑似 AI 生成的 PR，会标记并关闭。

同理，请不要直接复制粘贴 LLM 生成的评论和描述。

### 人类精力 DDoS

使用自动化工具和 AI 批量提交 PR 或评论，相当于对我们的人工审查实施 [拒绝服务攻击 (DDoS)](https://zh.wikipedia.org/wiki/拒绝服务攻击)。

提交者只需要一条 LLM 提示词，审查者却要花大量时间仔细看代码。

请不要这样做。我们会封禁重复提交自动化 PR 或评论的账号。

### 善用工具

正如 Uncle Ben 所说：

> 能力越~~大~~**强**，责任越大。

你手上有强大的工具，请明智地使用它们，避免无意中造成伤害。

## 有问题？

如有任何关于贡献的疑问，欢迎发起 [GitHub Discussion](https://github.com/raymondtxw/ai-fullstack-platform/discussions)。
