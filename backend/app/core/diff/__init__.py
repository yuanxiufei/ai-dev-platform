"""
Diff Engine — 代码变更差异系统

每当你写入/修改一个文件，DiffEngine 生成 unified diff，
供前端 diff-viewer 展示绿色（新增）/ 红色（删除）的代码对比。

这是 AI IDE 区别于普通聊天工具的核心能力之一。
"""

from __future__ import annotations

from app.core.diff.diff_engine import DiffEngine, FileDiff, detect_language

__all__ = ["DiffEngine", "FileDiff", "detect_language"]
