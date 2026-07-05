"""
Context Key Engine — VS Code 风格 when 子句评估引擎

对标: vscode/src/vs/platform/contextkey/common/contextkey.ts

功能:
  1. 维护工作区级 context key 字典 (bool/str/number)
  2. when 子句表达式求值 (&&, ||, !, ==, !=, >, <, >=, <=, in, not in, =~ regex)
  3. 内置 context keys (编辑器状态/系统信息) 自动同步
  4. 上下文变更事件通知 (WebSocket/subscriber)

When 子句语法:
  - 逻辑: &&, ||, !, ()
  - 比较: ==, !=, >, <, >=, <=
  - 集合: in, not in
  - 正则: =~
  - 布尔: key (等价于 key == true)
  - 取反: !key

用法:
  >>> engine = ContextKeyEngine(workspace_id="ws1")
  >>> engine.set("editorHasSelection", True)
  >>> engine.set("editorLangId", "python")
  >>> engine.evaluate("editorHasSelection && editorLangId == 'python'")
  True
"""

from __future__ import annotations

import re
import time
import json
import sqlite3
import threading
from typing import Any, Callable, Optional, Union
from dataclasses import dataclass, field
from enum import Enum


# ==================== 类型定义 ====================

ContextKeyValue = Union[bool, str, int, float, None]

# When 子句 Token 类型
class TokenType(Enum):
    KEY = "key"
    STRING = "string"
    NUMBER = "number"
    BOOL = "bool"  # true/false
    NULL = "null"
    AND = "&&"
    OR = "||"
    NOT = "!"
    EQ = "=="
    NEQ = "!="
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    IN = "in"
    NOT_IN = "not in"
    REGEX = "=~"
    LPAREN = "("
    RPAREN = ")"
    EOF = "eof"


@dataclass
class Token:
    type: TokenType
    value: Any = None
    pos: int = 0


@dataclass
class ContextKeyChange:
    """Context key 变更事件"""
    workspace_id: str
    key: str
    old_value: ContextKeyValue
    new_value: ContextKeyValue
    timestamp: float = field(default_factory=time.time)


# 内置 context keys (VSCode 对标)
BUILTIN_KEYS = {
    "isMac": "darwin",
    "isLinux": "linux",
    "isWindows": "win32",
    "isWeb": True,
    "editorHasSelection": False,
    "editorHasMultipleSelections": False,
    "editorReadonly": False,
    "editorLangId": "plaintext",
    "editorHasCodeActions": False,
    "editorHasRenameProvider": False,
    "editorHasDefinitionProvider": False,
    "editorHasReferenceProvider": False,
    "editorHasFormatProvider": False,
    "editorHasSignatureHelpProvider": False,
    "editorHasCompletionProvider": False,
    "editorHasHoverProvider": False,
    "editorHasDiagnostics": False,
    "editorTabFocusMode": False,
    "terminalFocus": False,
    "searchViewletVisible": False,
    "sideBarVisible": True,
    "panelVisible": False,
    "zenMode": False,
    "inDebugMode": False,
    "debugState": "stopped",  # stopped/running/paused
    "gitOpenRepositoryCount": 0,
    "scmProvider": "",
    "listFocus": False,
    "inputFocus": False,
    "textInputFocus": False,
    "explorerViewletVisible": True,
    "extensionsViewletVisible": False,
    "activeEditorIsModified": False,
    "activeEditorIsPreview": False,
    "resourceExtname": "",
    "resourceFilename": "",
    "resourceLangId": "plaintext",
    "resourceDirname": "",
    "resourcePath": "",
    "workspaceFolderCount": 1,
    "isInDiffEditor": False,
    "isInMergeEditor": False,
    "chatSessionActive": False,
    "clipboardHasText": False,
    "clipboardHasImage": False,
}


# ==================== When 子句词法分析器 ====================

class WhenClauseLexer:
    """When 子句词法分析 (递归下降手写)"""

    _TOKEN_PATTERNS = [
        (re.compile(r'\s+'), None),                          # 空白 - 跳过
        (re.compile(r'&&'), TokenType.AND),
        (re.compile(r'\|\|'), TokenType.OR),
        (re.compile(r'!='), TokenType.NEQ),
        (re.compile(r'=='), TokenType.EQ),
        (re.compile(r'>='), TokenType.GTE),
        (re.compile(r'<='), TokenType.LTE),
        (re.compile(r'>'), TokenType.GT),
        (re.compile(r'<'), TokenType.LT),
        (re.compile(r'=~'), TokenType.REGEX),
        (re.compile(r'not\s+in'), TokenType.NOT_IN),
        (re.compile(r'\bin\b'), TokenType.IN),
        (re.compile(r'!'), TokenType.NOT),
        (re.compile(r'\('), TokenType.LPAREN),
        (re.compile(r'\)'), TokenType.RPAREN),
        (re.compile(r'\btrue\b'), None),                     # 布尔 - 特殊处理
        (re.compile(r'\bfalse\b'), None),                    # 布尔 - 特殊处理
        (re.compile(r'\bnull\b'), None),                     # null - 特殊处理
        (re.compile(r"'[^']*'"), None),                      # 单引号字符串
        (re.compile(r'"[^"]*"'), None),                      # 双引号字符串
        (re.compile(r'-?\d+\.\d+'), None),                   # 浮点数
        (re.compile(r'-?\d+'), None),                        # 整数
        (re.compile(r'[a-zA-Z_][a-zA-Z0-9_.]*'), None),     # 键名
    ]

    def __init__(self, source: str) -> None:
        self.source = source
        self.pos = 0
        self.tokens: list[Token] = []
        self._tokenize()

    def _tokenize(self) -> None:
        pos = 0
        while pos < len(self.source):
            matched = False
            for pattern, tok_type in self._TOKEN_PATTERNS:
                m = pattern.match(self.source, pos)
                if m:
                    text = m.group(0)
                    if tok_type is not None:
                        if tok_type == TokenType.NOT_IN:
                            # 空格跳过在此匹配组中已处理外围空白
                            pass
                        self.tokens.append(Token(type=tok_type, value=text, pos=pos))
                    elif text in ('true', 'false'):
                        self.tokens.append(Token(type=TokenType.BOOL, value=text == 'true', pos=pos))
                    elif text == 'null':
                        self.tokens.append(Token(type=TokenType.NULL, value=None, pos=pos))
                    elif text.startswith("'") or text.startswith('"'):
                        self.tokens.append(Token(type=TokenType.STRING, value=text[1:-1], pos=pos))
                    elif '.' in text or text.replace('-', '').replace('.', '').isdigit():
                        try:
                            val = float(text) if '.' in text else int(text)
                            self.tokens.append(Token(type=TokenType.NUMBER, value=val, pos=pos))
                        except ValueError:
                            self.tokens.append(Token(type=TokenType.KEY, value=text, pos=pos))
                    else:
                        self.tokens.append(Token(type=TokenType.KEY, value=text, pos=pos))
                    pos = m.end()
                    matched = True
                    break
            if not matched:
                # 跳过无法识别的字符
                pos += 1
        self.tokens.append(Token(type=TokenType.EOF, pos=len(self.source)))

    def __iter__(self):
        return iter(self.tokens)


# ==================== When 子句语法分析+求值 ====================

class WhenClauseEvaluator:
    """
    When 子句递归下降求值器

    语法优先级 (从低到高):
      expr     → or_expr
      or_expr  → and_expr ('||' and_expr)*
      and_expr → not_expr ('&&' not_expr)*
      not_expr → '!' not_expr | primary
      primary  → comparison | '(' expr ')'
      comparison → value (op value)?
      op       → '==' | '!=' | '>' | '<' | '>=' | '<=' | 'in' | 'not in' | '=~'
      value    → KEY | STRING | NUMBER | BOOL | NULL
    """

    def __init__(self, context: dict[str, ContextKeyValue]) -> None:
        self.context = context
        self.tokens: list[Token] = []
        self.current = 0

    def evaluate(self, when_clause: str) -> bool:
        """
        求值 when 子句

        Args:
            when_clause: 如 "editorHasSelection && editorLangId == 'python'"

        Returns:
            求值结果 (布尔值)
        """
        lexer = WhenClauseLexer(when_clause)
        self.tokens = [t for t in lexer if t.type != TokenType.EOF]  # 不需要 EOF token
        self.current = 0
        if not self.tokens:
            return True  # 空 when 子句永远为真
        result = self._parse_or()
        return result

    def _peek(self) -> Optional[Token]:
        if self.current < len(self.tokens):
            return self.tokens[self.current]
        return None

    def _advance(self) -> Optional[Token]:
        tok = self._peek()
        if tok:
            self.current += 1
        return tok

    def _check(self, *types: TokenType) -> bool:
        tok = self._peek()
        return tok is not None and tok.type in types

    def _match(self, *types: TokenType) -> Optional[Token]:
        if self._check(*types):
            return self._advance()
        return None

    def _parse_or(self) -> bool:
        left = self._parse_and()
        while self._match(TokenType.OR):
            right = self._parse_and()
            left = left or right
        return left

    def _parse_and(self) -> bool:
        left = self._parse_not()
        while self._match(TokenType.AND):
            right = self._parse_not()
            left = left and right
        return left

    def _parse_not(self) -> bool:
        if self._match(TokenType.NOT):
            return not self._parse_not()
        return self._parse_primary()

    def _parse_primary(self) -> bool:
        if self._match(TokenType.LPAREN):
            result = self._parse_or()
            self._match(TokenType.RPAREN)  # 容错: 跳过右括号
            return result
        return self._parse_comparison()

    def _parse_comparison(self) -> bool:
        left_val = self._parse_value()
        if left_val is None:
            # 如果 key 不存在, 跳过后续比较操作符
            self._skip_comparison()
            return False

        tok = self._peek()
        if tok and tok.type in (
            TokenType.EQ, TokenType.NEQ, TokenType.GT, TokenType.LT,
            TokenType.GTE, TokenType.LTE, TokenType.IN, TokenType.NOT_IN,
            TokenType.REGEX
        ):
            op = self._advance()
            right_val = self._parse_value()
            return self._apply_op(op, left_val, right_val)

        # 无比较操作符: 布尔键值 (如 "editorHasSelection" → Truthy)
        return bool(left_val)

    def _skip_comparison(self) -> None:
        """跳过比较操作符和右侧值 (当左侧 key 不存在时)"""
        tok = self._peek()
        if tok and tok.type in (
            TokenType.EQ, TokenType.NEQ, TokenType.GT, TokenType.LT,
            TokenType.GTE, TokenType.LTE, TokenType.IN, TokenType.NOT_IN,
            TokenType.REGEX
        ):
            self._advance()
            self._parse_value()

    def _parse_value(self) -> Any:
        tok = self._peek()
        if tok is None:
            return None

        if tok.type == TokenType.KEY:
            self._advance()
            key = str(tok.value)
            return self.context.get(key)

        if tok.type in (TokenType.STRING, TokenType.NUMBER, TokenType.BOOL, TokenType.NULL):
            self._advance()
            return tok.value

        # 未知 token, 跳过
        self._advance()
        return None

    @staticmethod
    def _apply_op(op: Token, left: Any, right: Any) -> bool:
        """应用比较操作符"""
        try:
            if op.type == TokenType.EQ:
                return left == right
            elif op.type == TokenType.NEQ:
                return left != right
            elif op.type == TokenType.GT:
                return float(left) > float(right) if left is not None and right is not None else False
            elif op.type == TokenType.LT:
                return float(left) < float(right) if left is not None and right is not None else False
            elif op.type == TokenType.GTE:
                return float(left) >= float(right) if left is not None and right is not None else False
            elif op.type == TokenType.LTE:
                return float(left) <= float(right) if left is not None and right is not None else False
            elif op.type == TokenType.IN:
                if isinstance(right, (list, tuple, set)):
                    return left in right
                if isinstance(right, str) and isinstance(left, str):
                    return left in right
                return False
            elif op.type == TokenType.NOT_IN:
                if isinstance(right, (list, tuple, set)):
                    return left not in right
                if isinstance(right, str) and isinstance(left, str):
                    return left not in right
                return True
            elif op.type == TokenType.REGEX:
                if right is None:
                    return False
                try:
                    return bool(re.search(str(right), str(left) if left is not None else ''))
                except re.error:
                    return False
        except (TypeError, ValueError):
            return False
        return False


# ==================== Context Key 引擎核心 ====================

class ContextKeyEngine:
    """
    Context Key 管理引擎

    特性:
      - 工作区隔离: 每个 workspace_id 独立 context
      - 内置键: 系统信息/编辑器状态自动维护
      - 订阅者: key 变更时通知回调
      - SQLite 持久化: 多进程安全 WAL 模式
    """

    _instances: dict[str, "ContextKeyEngine"] = {}
    _lock = threading.Lock()
    _db_path: str = ":memory:"

    @classmethod
    def configure_db(cls, db_path: str) -> None:
        """配置 SQLite 数据库路径 (全局单次调用)"""
        cls._db_path = db_path

    @classmethod
    def get_engine(cls, workspace_id: str) -> "ContextKeyEngine":
        """获取或创建工作区引擎"""
        with cls._lock:
            if workspace_id not in cls._instances:
                cls._instances[workspace_id] = cls(workspace_id)
            return cls._instances[workspace_id]

    def __init__(self, workspace_id: str) -> None:
        self.workspace_id = workspace_id
        self._context: dict[str, ContextKeyValue] = {}
        self._subscribers: dict[str, list[Callable[[ContextKeyChange], None]]] = {}

        # 初始化内置键
        import platform as _platform
        system = _platform.system().lower()
        for key, default in BUILTIN_KEYS.items():
            if key in ("isMac", "isLinux", "isWindows"):
                self._context[key] = False
            elif isinstance(default, str) and default in ("darwin", "linux", "win32"):
                self._context[key] = False
            else:
                self._context[key] = default

        # 设置平台键
        self._context["isMac"] = (system == "darwin")
        self._context["isLinux"] = (system == "linux")
        self._context["isWindows"] = (system == "win32")

        # 从数据库加载持久化 keys
        self._load_from_db()

    # ---- 数据库操作 ----

    def _get_db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS context_keys (
                workspace_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                value_type TEXT NOT NULL DEFAULT 'string',
                updated_at REAL NOT NULL,
                PRIMARY KEY (workspace_id, key)
            )
        """)
        conn.commit()
        return conn

    def _load_from_db(self) -> None:
        """从 SQLite 加载持久化 keys"""
        try:
            conn = self._get_db()
            cursor = conn.execute(
                "SELECT key, value, value_type FROM context_keys WHERE workspace_id = ?",
                (self.workspace_id,)
            )
            for key, val, vtype in cursor.fetchall():
                self._context[key] = self._deserialize(val, vtype)
            conn.close()
        except Exception:
            pass  # 内存模式或首次启动, 忽略

    def _save_to_db(self, key: str, value: ContextKeyValue) -> None:
        """持久化单个 key 到 SQLite"""
        try:
            val_str, vtype = self._serialize(value)
            conn = self._get_db()
            conn.execute(
                """INSERT OR REPLACE INTO context_keys
                   (workspace_id, key, value, value_type, updated_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (self.workspace_id, key, val_str, vtype, time.time())
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    def _delete_from_db(self, key: str) -> None:
        """从 SQLite 删除 key"""
        try:
            conn = self._get_db()
            conn.execute(
                "DELETE FROM context_keys WHERE workspace_id = ? AND key = ?",
                (self.workspace_id, key)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

    @staticmethod
    def _serialize(value: ContextKeyValue) -> tuple[str, str]:
        """序列化值为字符串 + 类型标记"""
        if isinstance(value, bool):
            return ('true' if value else 'false', 'bool')
        elif isinstance(value, (int, float)):
            return (str(value), 'number')
        elif isinstance(value, str):
            return (value, 'string')
        elif value is None:
            return ('null', 'null')
        return (str(value), 'string')

    @staticmethod
    def _deserialize(val_str: str, vtype: str) -> ContextKeyValue:
        """反序列化"""
        if vtype == 'bool':
            return val_str == 'true'
        elif vtype == 'number':
            try:
                return float(val_str) if '.' in val_str else int(val_str)
            except ValueError:
                return val_str
        elif vtype == 'null':
            return None
        return val_str

    # ---- 公共 API ----

    def get(self, key: str) -> ContextKeyValue:
        """获取 context key 值"""
        return self._context.get(key)

    def set(self, key: str, value: ContextKeyValue, persist: bool = False) -> ContextKeyChange:
        """
        设置 context key 值

        Args:
            key: 键名
            value: 新值
            persist: 是否持久化到 SQLite

        Returns:
            ContextKeyChange 变更事件
        """
        old = self._context.get(key)
        self._context[key] = value

        if persist:
            self._save_to_db(key, value)
        else:
            # 非持久化 key: 如果之前持久化了, 移除数据库记录
            self._delete_from_db(key)

        change = ContextKeyChange(
            workspace_id=self.workspace_id,
            key=key,
            old_value=old,
            new_value=value,
        )

        # 通知订阅者
        self._notify(change)
        return change

    def delete(self, key: str) -> Optional[ContextKeyValue]:
        """删除 context key"""
        old = self._context.pop(key, None)
        self._delete_from_db(key)
        return old

    def batch_set(self, updates: dict[str, ContextKeyValue]) -> list[ContextKeyChange]:
        """批量设置 context keys"""
        changes = []
        for key, value in updates.items():
            changes.append(self.set(key, value))
        return changes

    def evaluate(self, when_clause: str) -> bool:
        """
        求值 when 子句

        Args:
            when_clause: VSCode 风格 when 子句

        Returns:
            求值结果

        Examples:
            >>> engine.evaluate("editorHasSelection && editorLangId == 'python'")
            True
            >>> engine.evaluate("!editorReadonly || isAdmin")
            True
        """
        if not when_clause or not when_clause.strip():
            return True
        evaluator = WhenClauseEvaluator(self._context)
        return evaluator.evaluate(when_clause)

    def get_all(self) -> dict[str, ContextKeyValue]:
        """获取所有 context keys"""
        return dict(self._context)

    def get_snapshot(self) -> dict[str, Any]:
        """获取快照 (序列化友好)"""
        result = {}
        for key, value in self._context.items():
            if value is None:
                result[key] = None
            elif isinstance(value, bool):
                result[key] = value
            elif isinstance(value, (int, float)):
                result[key] = value
            else:
                result[key] = str(value)
        return result

    # ---- 编辑器状态快捷方法 ----

    def update_editor_state(
        self,
        lang_id: str = "",
        has_selection: Optional[bool] = None,
        has_multi_selections: Optional[bool] = None,
        readonly: Optional[bool] = None,
        is_modified: Optional[bool] = None,
        resource_ext: str = "",
        resource_filename: str = "",
        resource_path: str = "",
    ) -> list[ContextKeyChange]:
        """快捷更新编辑器相关的 context keys"""
        updates: dict[str, ContextKeyValue] = {}
        if lang_id:
            updates["editorLangId"] = lang_id
            updates["resourceLangId"] = lang_id
        if has_selection is not None:
            updates["editorHasSelection"] = has_selection
        if has_multi_selections is not None:
            updates["editorHasMultipleSelections"] = has_multi_selections
        if readonly is not None:
            updates["editorReadonly"] = readonly
        if is_modified is not None:
            updates["activeEditorIsModified"] = is_modified
        if resource_ext:
            updates["resourceExtname"] = resource_ext
        if resource_filename:
            updates["resourceFilename"] = resource_filename
        if resource_path:
            updates["resourcePath"] = resource_path

        return self.batch_set(updates)

    def update_debug_state(self, state: str) -> ContextKeyChange:
        """更新调试状态: stopped / running / paused"""
        self.set("debugState", state)
        return self.set("inDebugMode", state != "stopped")

    # ---- 订阅者管理 ----

    def subscribe(self, subscriber_id: str, callback: Callable[[ContextKeyChange], None]) -> None:
        """订阅 key 变更事件"""
        if subscriber_id not in self._subscribers:
            self._subscribers[subscriber_id] = []
        self._subscribers[subscriber_id].append(callback)

    def unsubscribe(self, subscriber_id: str) -> None:
        """取消订阅"""
        self._subscribers.pop(subscriber_id, None)

    def _notify(self, change: ContextKeyChange) -> None:
        """通知所有订阅者"""
        for callbacks in self._subscribers.values():
            for cb in callbacks:
                try:
                    cb(change)
                except Exception:
                    pass

    @classmethod
    def clear_workspace(cls, workspace_id: str) -> None:
        """清除工作区所有 context keys"""
        with cls._lock:
            if workspace_id in cls._instances:
                engine = cls._instances[workspace_id]
                try:
                    conn = engine._get_db()
                    conn.execute(
                        "DELETE FROM context_keys WHERE workspace_id = ?",
                        (workspace_id,)
                    )
                    conn.commit()
                    conn.close()
                except Exception:
                    pass
                del cls._instances[workspace_id]


# ==================== 便捷函数 ====================

def evaluate_when(when_clause: str, context: dict[str, Any]) -> bool:
    """
    单次求值 when 子句 (无需创建引擎)

    Args:
        when_clause: When 子句字符串
        context: 上下文字典

    Returns:
        求值结果
    """
    evaluator = WhenClauseEvaluator(context)
    return evaluator.evaluate(when_clause)


# ==================== 测试辅助 ====================

def _test_context_key_engine() -> None:
    """运行时验证"""
    engine = ContextKeyEngine("test-ws")

    # 基本设置/获取
    engine.set("myKey", True)
    assert engine.get("myKey") is True

    engine.set("editorLangId", "python")
    assert engine.get("editorLangId") == "python"

    # When 子句求值
    assert engine.evaluate("myKey") is True
    assert engine.evaluate("!myKey") is False
    assert engine.evaluate("myKey && editorLangId == 'python'") is True
    assert engine.evaluate("myKey && editorLangId == 'javascript'") is False
    assert engine.evaluate("myKey || editorLangId == 'javascript'") is True
    assert engine.evaluate("editorLangId =~ 'py.*'") is True
    assert engine.evaluate("editorLangId in ('python', 'javascript')") is True
    assert engine.evaluate("editorLangId not in ('go', 'rust')") is True

    # 复杂表达式
    engine.set("a", 5)
    engine.set("b", 10)
    assert engine.evaluate("a > 3 && b < 20") is True
    assert engine.evaluate("a == 5 && b >= 10") is True
    assert engine.evaluate("(a > 3 && b < 20) || editorLangId == 'rust'") is True

    # 嵌套括号
    engine.set("x", True)
    engine.set("y", False)
    engine.set("z", True)
    assert engine.evaluate("x && (y || z)") is True
    assert engine.evaluate("(x && y) || (!y && z)") is True

    # 不存在的 key
    assert engine.evaluate("nonExistentKey") is False
    assert engine.evaluate("!nonExistentKey") is True
    assert engine.evaluate("nonExistentKey == 'something'") is False

    # 空 when 子句
    assert engine.evaluate("") is True
    assert engine.evaluate("   ") is True

    # 编辑器状态快捷更新
    engine.update_editor_state(lang_id="typescript", has_selection=True)
    assert engine.get("editorLangId") == "typescript"
    assert engine.get("editorHasSelection") is True

    # 调试状态
    engine.update_debug_state("paused")
    assert engine.get("debugState") == "paused"
    assert engine.get("inDebugMode") is True

    print("[OK] ContextKeyEngine 所有测试通过")


if __name__ == "__main__":
    _test_context_key_engine()
