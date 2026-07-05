"""
Configuration Resolver — VS Code 风格 ${variable} 解析器

对标: vscode/src/vs/workbench/services/configurationResolver/
支持: ${config:}, ${env:}, ${workspaceFolder}, ${file}, ${fileBasename},
      ${fileExtname}, ${fileDirname}, ${relativeFile}, ${lineNumber},
      ${selectedText}, ${execPath}, ${pathSeparator}, ${/}, ${userHome}
"""

from __future__ import annotations
import os, re, json
from pathlib import Path
from typing import Any, Callable, Optional

_VAR_RE = re.compile(r'\$\{(.+?)\}')

class ConfigurationResolver:
    """解析文本中的 ${variable} 引用"""

    def __init__(
        self,
        workspace_root: str = "",
        config_getter: Optional[Callable[[str], Any]] = None,
        env_getter: Optional[Callable[[str], str]] = None,
    ):
        self.ws_root = workspace_root
        self.ws_name = Path(workspace_root).name if workspace_root else ""
        self._config = config_getter or (lambda k: None)
        self._env = env_getter or (lambda k: os.environ.get(k))
        self._ctx: dict[str, str] = {}

    def set_context(self, **kwargs: str) -> None:
        self._ctx.update(kwargs)

    def resolve(self, text: str) -> str:
        """解析文本中所有 ${...} 变量"""
        if not text or '${' not in text:
            return text
        result = text
        for _ in range(3):  # 最多3轮解析 (支持嵌套)
            prev = result
            result = _VAR_RE.sub(lambda m: self._resolve_var(m.group(1)), result)
            if result == prev:
                break
        return result

    def _resolve_var(self, var: str) -> str:
        """解析单个变量名"""
        # 嵌套: ${config:${env:KEY}} → 递归
        if '${' in var:
            var = _VAR_RE.sub(lambda m: self._resolve_var(m.group(1)), var)

        # 带前缀: config: / env: / command:
        if ':' in var:
            prefix, name = var.split(':', 1)
            prefix = prefix.strip()
            name = name.strip()
            if prefix == 'config':
                val = self._config(name)
                return str(val) if val is not None else f'${{{var}}}'
            if prefix == 'env':
                val = self._env(name)
                return val if val is not None else f'${{{var}}}'
            if prefix == 'command':
                return f'${{{var}}}'  # command 变量运行时求值
            return f'${{{var}}}'

        # 无前缀变量
        return self._resolve_builtin(var)

    def _resolve_builtin(self, name: str) -> str:
        """解析内置变量"""
        builtins: dict[str, Any] = {
            'workspaceFolder': self.ws_root,
            'workspaceFolderBasename': self.ws_name,
            'cwd': self.ws_root or os.getcwd(),
            'userHome': str(Path.home()),
            'pathSeparator': os.sep, '/': os.sep,
            'execPath': '',
            'lineNumber': self._ctx.get('lineNumber', ''),
            'selectedText': self._ctx.get('selectedText', ''),
            'file': self._ctx.get('file', ''),
            'fileBasename': self._ctx.get('fileBasename', '') or (
                Path(self._ctx.get('file', '')).name if self._ctx.get('file') else ''),
            'fileExtname': self._ctx.get('fileExtname', '') or (
                Path(self._ctx.get('file', '')).suffix if self._ctx.get('file') else ''),
            'fileDirname': self._ctx.get('fileDirname', '') or (
                str(Path(self._ctx.get('file', '')).parent) if self._ctx.get('file') else ''),
            'relativeFile': self._ctx.get('relativeFile', '') or self._make_relative(),
            'relativeFileDirname': self._ctx.get('relativeFileDirname', '') or self._make_rel_dir(),
            'fileWorkspaceFolder': self._ctx.get('fileWorkspaceFolder', '') or self.ws_root,
        }

        val = builtins.get(name, f'${{{name}}}')
        return str(val) if val is not None else ''

    def _make_relative(self) -> str:
        f = self._ctx.get('file', '')
        if f and self.ws_root:
            try:
                return str(Path(f).relative_to(self.ws_root))
            except ValueError:
                return f
        return f

    def _make_rel_dir(self) -> str:
        d = self._ctx.get('fileDirname', '') or (
            str(Path(self._ctx.get('file', '')).parent) if self._ctx.get('file') else '')
        if d and self.ws_root:
            try:
                return str(Path(d).relative_to(self.ws_root))
            except ValueError:
                return d
        return d

    def resolve_all(self, config_dict: dict[str, Any]) -> dict[str, Any]:
        """递归解析 dict 中所有值"""
        result = {}
        for k, v in config_dict.items():
            if isinstance(v, str):
                result[k] = self.resolve(v)
            elif isinstance(v, dict):
                result[k] = self.resolve_all(v)
            elif isinstance(v, list):
                result[k] = [
                    self.resolve(item) if isinstance(item, str) else item
                    for item in v
                ]
            else:
                result[k] = v
        return result
