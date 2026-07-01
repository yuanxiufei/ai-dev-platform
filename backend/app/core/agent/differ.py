"""
Aider-Style Fuzzy Search-Replace Diff Engine

借鉴 Aider diffs.py 的设计核心:
- Search-Replace 编辑块 (非 unified diff)
- Fuzzy matching (容错匹配，忽略空白差异)
- 冲突检测 (同一 region 多次修改)
- 撤销支持 (保存逆操作)
- 多文件并发编辑

来源: D:/code/aider/aider/diffs.py
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EditBlock:
    """单个编辑操作"""
    file_path: str
    search: str          # 要搜索的原始代码块
    replace: str         # 替换后的代码块 (空=删除)
    start_line: int = 0  # 匹配到的起始行号 (1-based)
    end_line: int = 0    # 匹配到的结束行号
    fuzzy_matched: bool = False  # 是否用了模糊匹配

    @property
    def is_delete(self) -> bool:
        return self.replace == ""

    @property
    def is_insert(self) -> bool:
        return self.search == ""

    @property
    def reverse_edit(self) -> EditBlock:
        """生成逆操作 (用于撤销)"""
        return EditBlock(
            file_path=self.file_path,
            search=self.replace,
            replace=self.search,
        )


@dataclass
class DiffResult:
    """单文件 Diff 应用结果"""
    file_path: str
    original: str
    modified: str | None = None
    applied_edits: list[EditBlock] = field(default_factory=list)
    failed_edits: list[EditBlock] = field(default_factory=list)
    conflict_edits: list[tuple[EditBlock, EditBlock]] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.failed_edits) == 0 and len(self.conflict_edits) == 0

    @property
    def changed(self) -> bool:
        return self.original != self.modified if self.modified else False

    @property
    def unified_diff(self) -> str:
        """生成标准 unified diff"""
        if not self.changed:
            return ""
        diff_lines = difflib.unified_diff(
            self.original.splitlines(keepends=True),
            self.modified.splitlines(keepends=True) if self.modified else [],
            fromfile=f"a/{self.file_path}",
            tofile=f"b/{self.file_path}",
            lineterm="",
        )
        return "".join(diff_lines)

    @property
    def search_replace_diff(self) -> str:
        """生成 Aider 风格的 Search-Replace 展示"""
        parts = [f"# File: {self.file_path}\n"]
        for i, edit in enumerate(self.applied_edits, 1):
            parts.append(f"## Edit {i}")
            if edit.fuzzy_matched:
                parts.append("  (fuzzy matched)")
            parts.append(f"```")
            parts.append(f"<<<<<<< SEARCH (line {edit.start_line}-{edit.end_line})")
            parts.append(edit.search)
            parts.append("=======")
            parts.append(edit.replace)
            parts.append(f">>>>>>> REPLACE")
            parts.append("```\n")
        return "\n".join(parts)


class FuzzyDiffer:
    """
    Aider 风格模糊 Diff 引擎

    核心特性:
    1. 精确匹配优先 → 失败时回退到模糊匹配 (忽略空白差异)
    2. 冲突检测: 多个编辑操作修改同一区间时报告冲突
    3. 编辑排序: 从下往上应用避免行号漂移
    4. 撤销支持: 每个 EditBlock 可生成逆操作
    """

    # 空白规范化正则: 压缩连续空白为单个空格
    _WHITESPACE_RE = re.compile(r"\s+")

    @staticmethod
    def _normalize(text: str) -> str:
        """规范化文本: 去除首尾空白 + 压缩中间空白"""
        return FuzzyDiffer._WHITESPACE_RE.sub(" ", text.strip())

    @classmethod
    def fuzzy_find(
        cls,
        content: str,
        search: str,
        threshold: float = 0.8,
    ) -> tuple[int, int, bool]:
        """
        在 content 中模糊匹配 search，返回 (start_line, end_line, is_fuzzy)

        策略:
        1. 先尝试精确匹配
        2. 如果失败，规范化后行级匹配 (SequenceMatcher 求最佳子序列)
        3. 如果仍然失败，抛出 ValueError

        Args:
            content: 完整文件内容
            search: 要搜索的代码块
            threshold: 相似度阈值 (0.0-1.0)

        Returns:
            (start_line, end_line, is_fuzzy): 匹配到的行号 (1-based) 和是否模糊匹配
        """
        if search == "":
            return 0, 0, False  # 插入操作，无需搜索

        # 策略 1: 精确匹配
        idx = content.find(search)
        if idx >= 0:
            start = content[:idx].count("\n") + 1
            end = start + search.count("\n")
            return start, end, False

        # 策略 2: 行级模糊匹配
        search_lines = search.strip().splitlines()
        content_lines = content.splitlines()

        best_start, best_end, best_ratio = 0, 0, 0.0

        for i in range(len(content_lines) - len(search_lines) + 1):
            window = content_lines[i:i + len(search_lines)]
            # 逐行计算相似度
            total_ratio = 0.0
            for wl, sl in zip(window, search_lines):
                total_ratio += difflib.SequenceMatcher(
                    None,
                    cls._normalize(wl),
                    cls._normalize(sl),
                ).ratio()
            avg_ratio = total_ratio / len(search_lines) if search_lines else 0

            if avg_ratio > best_ratio:
                best_ratio = avg_ratio
                best_start = i + 1  # 1-based
                best_end = i + len(search_lines)

        if best_ratio >= threshold:
            return best_start, best_end, True

        # 策略 3: 整个搜索块作为一个单元的模糊匹配
        # 用滑动窗口检查完整搜索块与文件片段的相似度
        norm_search = cls._normalize(search)
        best_window_start, best_window_ratio = 0, 0.0
        chunk_size = max(len(search_lines), 5)

        for i in range(len(content_lines) - chunk_size + 1):
            window_lines = content_lines[i:i + chunk_size]
            norm_window = cls._normalize("\n".join(window_lines))
            ratio = difflib.SequenceMatcher(None, norm_window, norm_search).ratio()
            if ratio > best_window_ratio:
                best_window_ratio = ratio
                best_window_start = i + 1

        if best_window_ratio >= threshold:
            return best_window_start, best_window_start + len(search_lines) - 1, True

        raise ValueError(
            f"Could not find search block in file "
            f"(best fuzzy ratio: {best_window_ratio:.2f}, threshold: {threshold})"
        )

    @classmethod
    def apply_edits(
        cls,
        file_path: str,
        original: str,
        edits: list[EditBlock],
        fuzzy_threshold: float = 0.8,
    ) -> DiffResult:
        """
        应用一组编辑操作到文件内容

        编辑从下往上应用 (按起始行号倒序)，防止行号漂移。

        Args:
            file_path: 文件路径
            original: 原始文件内容
            edits: 编辑操作列表
            fuzzy_threshold: 模糊匹配阈值

        Returns:
            DiffResult: 包含修改后内容和成功/失败/冲突编辑的列表
        """
        result = DiffResult(file_path=file_path, original=original)
        modified = original

        # 按起始行号倒序排列 (从下往上应用)
        try:
            positioned: list[EditBlock] = []
            for edit in edits:
                if edit.is_insert and edit.start_line > 0:
                    positioned.append(edit)
                else:
                    start, end, fuzzy = cls.fuzzy_find(
                        modified, edit.search, fuzzy_threshold,
                    )
                    edit.start_line = start
                    edit.end_line = end
                    edit.fuzzy_matched = fuzzy
                    positioned.append(edit)
        except ValueError as e:
            result.failed_edits.append(edit)
            result.modified = modified
            return result

        # 排序: 从下往上
        positioned.sort(key=lambda e: e.start_line, reverse=True)

        # 冲突检测
        for i in range(len(positioned)):
            for j in range(i + 1, len(positioned)):
                a, b = positioned[i], positioned[j]
                # 检查区间是否重叠
                if a.start_line <= b.end_line and b.start_line <= a.end_line:
                    result.conflict_edits.append((a, b))

        if result.conflict_edits:
            result.modified = modified
            return result

        # 逐个应用编辑
        lines = modified.splitlines(keepends=True)

        for edit in positioned:
            if edit.is_insert:
                # 在指定行前插入
                insert_at = edit.start_line - 1  # 0-based
                insert_text = edit.replace
                if not insert_text.endswith("\n"):
                    insert_text += "\n"
                lines.insert(insert_at, insert_text)
            else:
                start_idx = edit.start_line - 1  # 0-based
                end_idx = edit.end_line           # exclusive

                # 验证搜索内容是否匹配
                actual = "".join(lines[start_idx:end_idx])
                if edit.search != actual and not edit.fuzzy_matched:
                    result.failed_edits.append(edit)
                    continue

                # 替换
                replace_lines = edit.replace.splitlines(keepends=True)
                lines[start_idx:end_idx] = [
                    l if l.endswith("\n") else l + "\n" for l in replace_lines
                ]

            result.applied_edits.append(edit)

        result.modified = "".join(lines)
        return result

    @classmethod
    def parse_edit_blocks(cls, text: str, file_path: str = "") -> list[EditBlock]:
        """
        从文本中解析 Aider 风格的编辑块

        Format:
        ```
        path/to/file.py
        <<<<<<< SEARCH
        old code
        =======
        new code
        >>>>>>> REPLACE
        ```

        也支持 LLM 常用格式:
        ```
        ```file:path/to/file.py
        // ... existing code ...
        ```
        ```
        """
        edits: list[EditBlock] = []
        current_file = file_path

        # 模式 1: Aider SEARCH/REPLACE 格式
        search_replace_pattern = re.compile(
            r"<<<<<<< SEARCH\s*\n(.*?)\n?=======\s*\n(.*?)\n?>>>>>>> REPLACE",
            re.DOTALL,
        )

        for match in search_replace_pattern.finditer(text):
            search = match.group(1).rstrip()
            replace = match.group(2).rstrip()
            edits.append(EditBlock(
                file_path=current_file,
                search=search,
                replace=replace,
            ))

        return edits

    @classmethod
    def multi_file_apply(
        cls,
        edits_by_file: dict[str, list[EditBlock]],
        file_contents: dict[str, str],
        fuzzy_threshold: float = 0.8,
    ) -> dict[str, DiffResult]:
        """
        多文件批量应用编辑

        Args:
            edits_by_file: {file_path: [EditBlock, ...]}
            file_contents: {file_path: current_content}
            fuzzy_threshold: 模糊匹配阈值

        Returns:
            {file_path: DiffResult}
        """
        results: dict[str, DiffResult] = {}

        for file_path, edits in edits_by_file.items():
            original = file_contents.get(file_path, "")
            if not edits:
                results[file_path] = DiffResult(
                    file_path=file_path, original=original, modified=original,
                )
                continue

            result = cls.apply_edits(file_path, original, edits, fuzzy_threshold)
            results[file_path] = result

        return results


# ── 全局单例 ──────────────────────────────────────────────

_differ_instance: FuzzyDiffer | None = None


def get_differ() -> FuzzyDiffer:
    """获取全局 FuzzyDiffer 单例"""
    global _differ_instance
    if _differ_instance is None:
        _differ_instance = FuzzyDiffer()
    return _differ_instance
