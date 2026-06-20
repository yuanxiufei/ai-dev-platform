"""
GBNF (GGML BNF) 语法引擎 — JSON Schema → GBNF 自动转换

借鉴 llama.cpp 的 GBNF 约束系统：
https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md

功能：
1. JSON Schema → GBNF 语法规则自动转换
2. GBNF 语法校验
3. 内置常用语法模板（JSON object, array, enum, tool calls）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GBNFGrammar:
    """GBNF 语法规则容器"""

    root_rule: str = "root"
    rules: dict[str, str] = field(default_factory=dict)
    builtin_rules: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self.rules[self.root_rule] = self.rules.get(self.root_rule, "string")

    def add_rule(self, name: str, definition: str) -> None:
        self.rules[name] = definition

    def to_string(self) -> str:
        """输出符合 llama.cpp GBNF 规范的完整语法字符串"""
        lines: list[str] = []
        # 先输出根规则
        if self.root_rule in self.rules:
            lines.append(f"root ::= {self.rules[self.root_rule]}")
        # 再输出其他规则
        for name, definition in self.rules.items():
            if name == self.root_rule:
                continue
            lines.append(f"{name} ::= {definition}")
        return "\n".join(lines)


# ── 内置基础 GBNF 规则 ────────────────────────────

GBNF_PRIMITIVES: dict[str, str] = {
    "ws": r"""[ \t\n]* """,
    "string": r'''"\"" ([^"\\] | "\\" [\"\\bfnrt/] | "\\u" [0-9a-fA-F]{4})* "\"" ''',
    "boolean": r"""("true" | "false") """,
    "null": r""""null" """,
    "integer": r"""("-"? [0-9]+) """,
    "number": r"""("-"? ([0-9]+ | [0-9]* "." [0-9]+) ([eE] [-+]? [0-9]+)?) """,
    "letter": r"""[a-zA-Z] """,
    "digit": r"""[0-9] """,
    # JSON 通用值类型（用于 additionalProperties / 嵌套数组）
    "value": r"""(object | array | string | number | boolean | "null") """,
    "object": r""""{" space ( string space ":" space value ( "," space string space ":" space value )* )? space "}" """,
    "array": r""""[" space ( value ( "," space value )* )? space "]" """,
}


def _escape_gbnf_string(s: str) -> str:
    """转义 GBNF 字符串中的特殊字符"""
    escaped = s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\t', '\\t')
    return f'"\\"{escaped}\\""'


def _json_type_to_gbnf(schema: dict[str, Any], name: str = "value") -> tuple[str, dict[str, str]]:
    """
    递归将 JSON Schema 转换为 GBNF 规则

    返回 (根规则名称, {规则名: 规则定义})
    """
    rules: dict[str, str] = {}
    schema_type = schema.get("type", "string")

    if "enum" in schema:
        # 枚举 → GBNF 备选项
        enum_values = schema["enum"]
        choices = " | ".join(
            _escape_gbnf_string(str(v)) if isinstance(v, str) else str(v).lower()
            for v in enum_values
        )
        rules[name] = f"({choices})"
        return name, rules

    if schema_type == "object":
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        additional_properties = schema.get("additionalProperties", True)
        property_names = list(properties.keys())

        if not property_names:
            rules[name] = '"{" space "}"'
            return name, rules

        # 构建属性列表
        prop_rules: list[str] = []
        for i, prop_name in enumerate(property_names):
            prop_schema = properties[prop_name]
            prop_rule_name = f"{name}-{prop_name}"
            child_name, child_rules = _json_type_to_gbnf(prop_schema, prop_rule_name)
            rules.update(child_rules)

            key_literal = _escape_gbnf_string(prop_name)
            is_required = prop_name in required
            if is_required:
                if i > 0:
                    prop_rules.append(f'"," space {key_literal} space ":" space {child_name}')
                else:
                    prop_rules.append(f'{key_literal} space ":" space {child_name}')
            else:
                opt_rule = f'{name}-opt-{prop_name}'
                rules[opt_rule] = f'( "," space {key_literal} space ":" space {child_name} )?'
                prop_rules.append(opt_rule)

        # 构建完整 object 规则
        # 必需字段在前，可选字段在后
        props_str = " ".join(prop_rules)
        if additional_properties:
            extra_rule = f'{name}-extra'
            rules[extra_rule] = r'( "," space string space ":" space value )*'
            rules[name] = f'"{{" space {props_str} {extra_rule} space "}}"'
        else:
            rules[name] = f'"{{" space {props_str} space "}}"'

        return name, rules

    if schema_type == "array":
        items = schema.get("items", {"type": "string"})
        item_name, item_rules = _json_type_to_gbnf(items, f"{name}-item")
        rules.update(item_rules)

        min_items = schema.get("minItems", 0)
        if min_items > 0:
            rules[name] = f'"[" space {item_name} ("," space {item_name})* space "]"'
        else:
            rules[name] = f'"[" space ({item_name} ("," space {item_name})*)? space "]"'

        return name, rules

    if schema_type == "string":
        if "pattern" in schema:
            # 正则 pattern
            rules[name] = f'[^{{"]*'
        else:
            rules[name] = "string"
        return name, rules

    if schema_type in ("integer", "number"):
        rules[name] = schema_type
        return name, rules

    if schema_type == "boolean":
        rules[name] = "boolean"
        return name, rules

    # fallback
    rules[name] = "string"
    return name, rules


def json_schema_to_gbnf(json_schema: dict[str, Any], root_name: str = "root") -> str:
    """
    将 JSON Schema 转换为 GBNF 语法字符串

    Args:
        json_schema: JSON Schema 字典
        root_name: 根规则名称（默认 "root"）

    Returns:
        GBNF 语法字符串，可直接传给 llama.cpp --grammar

    Example:
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        gbnf = json_schema_to_gbnf(schema)
        # => root ::= "{" space "\\"name\\"" space ":" space string space "}"
    """
    grammar = GBNFGrammar(root_rule=root_name)

    # 添加基础规则
    grammar.rules.update(GBNF_PRIMITIVES)
    # 特殊定义 space（不带空格也可以）
    grammar.rules["space"] = r"""[ \t\n]* """

    # 转换用户 schema
    root_name_result, user_rules = _json_type_to_gbnf(json_schema, root_name)
    grammar.rules.update(user_rules)
    grammar.rules[root_name] = user_rules.get(root_name_result, grammar.rules.get(root_name_result, "string"))

    # 确保 root 是根
    grammar.root_rule = root_name
    if root_name not in grammar.rules:
        grammar.rules[root_name] = "string"

    return grammar.to_string()


# ── 内置语法模板 ──────────────────────────────────

def json_object_grammar() -> str:
    """生成通用 JSON object 语法（任意 key-value）"""
    return r"""root  ::= object
object ::= "{" space ( string space ":" space value ( "," space string space ":" space value )* )? space "}"
value  ::= object | array | string | number | boolean | "null"
array  ::= "[" space ( value ( "," space value )* )? space "]"
string ::= "\"" ([^"\\] | "\\" [\"\\bfnrt/] | "\\u" [0-9a-fA-F]{4})* "\""
number ::= "-"? ([0-9]+ | [0-9]* "." [0-9]+) ([eE] [-+]? [0-9]+)?
boolean ::= "true" | "false"
space  ::= [ \t\n]*"""


def tool_call_grammar() -> str:
    """生成 tool_calls 格式语法（OpenAI function calling 格式）"""
    return r"""root           ::= tool-calls
tool-calls     ::= "[" space tool-call ("," space tool-call)* space "]"
tool-call      ::= "{" space string space ":" space "\"function\"" space "," space string space ":" space function-object space "}"
function-object ::= "{" space string space ":" space string space "," space string space ":" space string space "}"
string         ::= "\"" ([^"\\] | "\\" [\"\\bfnrt/] | "\\u" [0-9a-fA-F]{4})* "\""
space          ::= [ \t\n]*"""


def enum_grammar(values: list[str]) -> str:
    """生成枚举类型语法"""
    choices = " | ".join(_escape_gbnf_string(v) for v in values)
    return f'root ::= {choices}'


def validate_gbnf(grammar_str: str) -> bool:
    """
    校验 GBNF 语法字符串的基本合法性

    检查：
    1. 包含 root 规则
    2. 所有引用的规则都已定义
    3. 没有明显的语法错误
    """
    if not grammar_str or not grammar_str.strip():
        return False

    lines = [l.strip() for l in grammar_str.strip().split("\n") if l.strip()]

    # 解析规则
    defined_rules: set[str] = set()
    referenced_rules: set[str] = set()

    rule_pattern = re.compile(r'^([\w-]+)\s*::=\s*(.+)$')
    # 移除 GBNF 字面量：字符类 [...] 和引号字符串 "..."（含 \" 转义）
    clean_re = re.compile(r'\[[^\]]*\]|\"[^\"\\]*(?:\\.[^\"\\]*)*\"')

    for line in lines:
        m = rule_pattern.match(line)
        if not m:
            continue
        rule_name = m.group(1)
        definition = m.group(2)
        defined_rules.add(rule_name)

        # 移除字面量后扫描剩余引用
        cleaned = clean_re.sub(" ", definition)
        refs = re.findall(r'\b([a-zA-Z_][\w-]*)\b', cleaned)
        for ref in refs:
            if ref not in {"root", "true", "false", "null", "e", "E"}:
                referenced_rules.add(ref)

    if "root" not in defined_rules:
        return False

    # 检查所有引用是否已定义
    undefined = referenced_rules - defined_rules
    return len(undefined) == 0
