"""
str_replace 精确编辑工具 — 借鉴 Trae Agent TextEditorTool

提供 "view → str_replace → insert → create" 四种操作，支持：
- view: 查看文件内容（含行号），支持行范围
- str_replace: 精确字符串替换（唯一性检查，防止误替换）
- insert: 在指定行后插入内容
- create: 创建新文件

与完整文件重写相比，精确编辑更安全：
1. 最小化变更范围
2. 唯一性校验防止误匹配
3. 保留文件其他部分的格式和内容

用法:
    tool = TextEditorTool()
    # 查看文件
    result = await tool.call(command="view", path="app/main.py")
    # 精确替换
    result = await tool.call(command="str_replace", path="app/main.py",
                             old_str="print('hello')", new_str="print('hello world')")
    # 插入
    result = await tool.call(command="insert", path="app/main.py",
                             insert_line=10, new_str="# New comment")
    # 创建
    result = await tool.call(command="create", path="app/new_file.py",
                             file_text="print('new')")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.tools.builtin_tool import BuiltinTool, ToolExecResult
from app.core.tools.schema import ToolParam, ParamType

logger = logging.getLogger("tools.text_editor")


@dataclass
class TextEditorTool(BuiltinTool):
    """str_replace 精确编辑工具"""

    name: str = "str_replace"
    description: str = (
        "精确文件编辑工具。支持四种操作："
        "1) view — 查看文件内容（含行号），可选行范围；"
        "2) str_replace — 精确字符串替换，old_str 必须唯一匹配；"
        "3) insert — 在指定行后插入内容；"
        "4) create — 创建新文件。"
        "优先使用 str_replace 而非重写整个文件。"
    )
    parameters: list[ToolParam] = field(default_factory=lambda: [
        ToolParam("command", ParamType.STRING, required=True,
                  description="操作类型: view | str_replace | insert | create"),
        ToolParam("path", ParamType.STRING, required=True,
                  description="文件路径（相对于工作区根目录）"),
        ToolParam("old_str", ParamType.STRING, required=False,
                  description="要替换的旧字符串（str_replace 操作必需）"),
        ToolParam("new_str", ParamType.STRING, required=False,
                  description="新字符串（str_replace 和 insert 操作使用）"),
        ToolParam("insert_line", ParamType.INTEGER, required=False,
                  description="插入位置（行号，insert 操作必需，内容插入到该行之后）"),
        ToolParam("view_range", ParamType.STRING, required=False,
                  description="查看范围，格式: 'start-end' 如 '1-50'（view 操作可选）"),
        ToolParam("file_text", ParamType.STRING, required=False,
                  description="文件完整内容（create 操作必需）"),
    ])
    category: str = "code"
    tags: list[str] = field(default_factory=lambda: ["editor", "file", "str_replace", "code"])

    def __post_init__(self):
        super().__post_init__()
        self._workspace_root = Path.cwd()  # 默认工作区根目录

    @property
    def workspace_root(self) -> Path:
        return self._workspace_root

    def _resolve_path(self, path: str) -> Path:
        """解析路径，防止目录遍历攻击"""
        resolved = (self._workspace_root / path).resolve()
        # 安全检查：确保在工作区内
        try:
            resolved.relative_to(self._workspace_root.resolve())
        except ValueError:
            raise PermissionError(
                f"路径遍历攻击检测: '{path}' 试图访问工作区外的文件"
            )
        return resolved

    async def handler(
        self,
        command: str,
        path: str,
        old_str: str = "",
        new_str: str = "",
        insert_line: int = 0,
        view_range: str = "",
        file_text: str = "",
        sandbox=None,
    ) -> str:
        """
        执行编辑命令（所有操作经过 Sandbox 安全检查）

        Args:
            command: view | str_replace | insert | create
            path: 文件路径
            old_str: 旧字符串（str_replace）
            new_str: 新字符串（str_replace / insert）
            insert_line: 插入行号（insert）
            view_range: 查看范围（view）
            file_text: 文件内容（create）
            sandbox: 可选沙箱实例

        Returns:
            执行结果描述
        """
        # 🆕 如果提供了 sandbox，使用 sandbox 进行文件操作
        if sandbox:
            return await self._execute_in_sandbox(
                sandbox, command, path, old_str, new_str,
                insert_line, view_range, file_text,
            )

        command = command.strip().lower()

        if command == "view":
            return self._view(path, view_range)
        elif command == "str_replace":
            return self._str_replace(path, old_str, new_str)
        elif command == "insert":
            return self._insert(path, insert_line, new_str)
        elif command == "create":
            return self._create(path, file_text)
        else:
            return f"❌ 未知命令: '{command}'。支持: view, str_replace, insert, create"

    async def _execute_in_sandbox(
        self, sandbox, command: str, path: str, old_str: str, new_str: str,
        insert_line: int, view_range: str, file_text: str,
    ) -> str:
        """通过 Sandbox 执行文件操作"""
        command = command.strip().lower()

        if command == "view":
            content = await sandbox.read_file(path)
            return self._format_view(content, view_range)

        elif command == "str_replace":
            content = await sandbox.read_file(path)
            result = self._do_str_replace(path, content, old_str, new_str)
            if result.startswith("✅"):
                await sandbox.write_file(path, content.replace(old_str, new_str))
            return result

        elif command == "insert":
            content = await sandbox.read_file(path)
            result = self._do_insert(path, content, insert_line, new_str)
            if result.startswith("✅"):
                lines = content.split("\n")
                lines.insert(insert_line, new_str)
                await sandbox.write_file(path, "\n".join(lines))
            return result

        elif command == "create":
            await sandbox.write_file(path, file_text)
            return f"✅ 文件已创建: {path} ({len(file_text)} 字符)"

        return f"❌ 未知命令: '{command}'"

    # ── 核心操作 ──────────────────────────────────────────

    def _view(self, path: str, view_range: str = "") -> str:
        """查看文件内容（含行号）"""
        try:
            filepath = self._resolve_path(path)
            if not filepath.exists():
                return f"❌ 文件不存在: {path}"

            content = filepath.read_text(encoding="utf-8")
            return self._format_view(content, view_range)

        except PermissionError as e:
            return f"🚫 {e}"
        except UnicodeDecodeError:
            return f"❌ 文件不是有效的 UTF-8 文本: {path}"
        except Exception as e:
            return f"❌ 读取文件失败: {path} — {e}"

    def _format_view(self, content: str, view_range: str = "") -> str:
        """格式化带行号的视图"""
        lines = content.split("\n")

        # 解析行范围
        start_line, end_line = 1, len(lines)
        if view_range:
            try:
                parts = view_range.split("-")
                start_line = int(parts[0])
                end_line = int(parts[1]) if len(parts) > 1 else start_line + 50
            except ValueError:
                pass

        start_line = max(1, start_line)
        end_line = min(len(lines), end_line)

        # 格式化输出
        line_width = len(str(end_line))
        output_lines = []
        for i in range(start_line - 1, end_line):
            line_num = i + 1
            output_lines.append(f"{line_num:>{line_width}} | {lines[i]}")

        header = f"📄 {len(lines)} 行"
        if view_range:
            header += f"（显示 {start_line}-{end_line}）"
        output_lines.insert(0, header)

        return "\n".join(output_lines)

    def _str_replace(self, path: str, old_str: str, new_str: str) -> str:
        """精确字符串替换"""
        try:
            filepath = self._resolve_path(path)
            if not filepath.exists():
                return f"❌ 文件不存在: {path}"

            content = filepath.read_text(encoding="utf-8")
            return self._do_str_replace(path, content, old_str, new_str)

        except PermissionError as e:
            return f"🚫 {e}"
        except UnicodeDecodeError:
            return f"❌ 文件不是有效的 UTF-8 文本: {path}"
        except Exception as e:
            return f"❌ 替换失败: {path} — {e}"

    def _do_str_replace(self, path: str, content: str, old_str: str, new_str: str) -> str:
        """执行替换逻辑（不涉及文件 IO）"""
        if not old_str and old_str != "":
            return "❌ str_replace 操作需要 old_str 参数（不能为空）"

        occurrences = content.count(old_str)

        if occurrences == 0:
            return (
                f"❌ 未找到匹配的字符串。old_str:\n"
                f"```\n{old_str[:200]}\n```\n"
                f"请使用 view 命令确认文件内容，确保 old_str 精确匹配（含缩进和换行）。"
            )

        if occurrences > 1:
            # 列出所有出现位置
            lines = content.split("\n")
            positions = []
            for i, line in enumerate(lines, 1):
                if old_str.split("\n")[0] in line:
                    positions.append(f"  第 {i} 行: {line[:80]}")
            return (
                f"❌ old_str 在文件中出现了 {occurrences} 次（需要唯一匹配）。\n"
                f"匹配位置:\n" + "\n".join(positions[:5]) +
                ("\n  ..." if len(positions) > 5 else "") +
                f"\n请提供更大的上下文使 old_str 唯一。"
            )

        # 唯一匹配 — 执行替换
        new_content = content.replace(old_str, new_str)
        Path(path).resolve()
        filepath = self._resolve_path(path)
        filepath.write_text(new_content, encoding="utf-8")

        # 统计变更
        added = len(new_str) - len(old_str)
        return (
            f"✅ 文件已更新: {path}\n"
            f"   替换了 {len(old_str)} → {len(new_str)} 字符"
            + (f"（+{added} 字符）" if added > 0 else f"（{added} 字符）" if added < 0 else "")
        )

    def _insert(self, path: str, insert_line: int, new_str: str) -> str:
        """在指定行后插入"""
        try:
            filepath = self._resolve_path(path)
            if not filepath.exists():
                return f"❌ 文件不存在: {path}"

            content = filepath.read_text(encoding="utf-8")
            return self._do_insert(path, content, insert_line, new_str)

        except PermissionError as e:
            return f"🚫 {e}"
        except UnicodeDecodeError:
            return f"❌ 文件不是有效的 UTF-8 文本: {path}"
        except Exception as e:
            return f"❌ 插入失败: {path} — {e}"

    def _do_insert(self, path: str, content: str, insert_line: int, new_str: str) -> str:
        """执行插入逻辑"""
        if not new_str:
            return "❌ insert 操作需要 new_str 参数"

        lines = content.split("\n")
        total_lines = len(lines)

        if insert_line < 0 or insert_line > total_lines:
            return (
                f"❌ 插入行号 {insert_line} 超出范围（文件共 {total_lines} 行，"
                f"有效范围: 0-{total_lines}，0 表示文件开头）"
            )

        lines.insert(insert_line, new_str)
        new_content = "\n".join(lines)
        filepath = self._resolve_path(path)
        filepath.write_text(new_content, encoding="utf-8")

        return f"✅ 已在 {path} 第 {insert_line} 行后插入 {len(new_str)} 字符"

    def _create(self, path: str, file_text: str) -> str:
        """创建新文件"""
        try:
            filepath = self._resolve_path(path)

            if filepath.exists():
                return f"❌ 文件已存在: {path}（使用 str_replace 修改）"

            # 确保父目录存在
            filepath.parent.mkdir(parents=True, exist_ok=True)

            # 🆕 通过 Sandbox 安全创建
            filepath.write_text(file_text, encoding="utf-8")

            return f"✅ 文件已创建: {path} ({len(file_text)} 字符, {file_text.count(chr(10))+1} 行)"

        except PermissionError as e:
            return f"🚫 {e}"
        except Exception as e:
            return f"❌ 创建文件失败: {path} — {e}"


# ── 工具注册 ──────────────────────────────────────────────────

def register_text_editor_tool() -> TextEditorTool:
    """注册 str_replace 工具到全局注册中心"""
    from app.core.tools.registry import get_tool_registry

    tool = TextEditorTool()
    registry = get_tool_registry()
    registry.register_sync(tool)
    logger.info("TextEditorTool (str_replace) registered")
    return tool
