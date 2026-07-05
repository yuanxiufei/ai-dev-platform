"""
语言检测 API (Session 48)

对标 VSCode languageDetection 服务 — 从文件名/内容推断编程语言。
采用三层回退策略：扩展名 → Shebang/声明 → 内容启发式 + Token频次分析。
"""

from __future__ import annotations

import re
from typing import List, Optional
from collections import Counter

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/system/language", tags=["system-language-detection"])


# ── 数据模型 ──

class DetectRequest(BaseModel):
    """语言检测请求"""
    content: str = Field(default="", description="文件内容 (前 10000 字符足够)")
    file_name: Optional[str] = Field(default=None, description="文件名/路径 (用于扩展名推断)")
    first_line: Optional[str] = Field(default=None, description="首行内容 (shebang/声明)")

class LanguageCandidate(BaseModel):
    """语言候选结果"""
    language_id: str = Field(..., description="语言标识符 (VSCode 风格)")
    language_name: str = Field(..., description="语言显示名")
    confidence: float = Field(..., description="置信度 0.0~1.0")
    source: str = Field(..., description="推断来源: extension/shebang/heuristic/bayesian")

class DetectResponse(BaseModel):
    """语言检测响应"""
    candidates: List[LanguageCandidate] = Field(default_factory=list)
    primary: Optional[LanguageCandidate] = Field(default=None, description="最高置信度候选")

class LanguageInfo(BaseModel):
    """语言信息"""
    id: str
    name: str
    extensions: List[str]
    aliases: List[str]
    mimetypes: List[str]


# ── 语言元数据注册表 ──

LANGUAGE_REGISTRY: dict[str, dict] = {
    "javascript": {
        "name": "JavaScript", "extensions": [".js", ".mjs", ".cjs"],
        "aliases": ["js", "node"], "mimetypes": ["text/javascript", "application/javascript"],
        "first_line_patterns": [r"^#!.*\bnode\b"],
        "heuristic_keywords": ["const ", "let ", "function", "=>", "require(", "import ", "export ", "console.log"],
        "heuristic_score": 2.0,
    },
    "typescript": {
        "name": "TypeScript", "extensions": [".ts", ".tsx", ".mts", ".cts"],
        "aliases": ["ts"], "mimetypes": ["text/typescript"],
        "first_line_patterns": [r"^#!.*\b(ts-node|deno)\b"],
        "heuristic_keywords": [": string", ": number", ": boolean", "interface ", "type ", "as const", "<T>", "React.FC"],
        "heuristic_score": 2.0,
    },
    "python": {
        "name": "Python", "extensions": [".py", ".pyw", ".pyi", ".pyx"],
        "aliases": ["py"], "mimetypes": ["text/x-python"],
        "first_line_patterns": [r"^#!.*\bpython", r"^# -\*- coding:"],
        "heuristic_keywords": ["def ", "class ", "import ", "from ", "if __name__", "self.", "print(", "elif ", "except "],
        "heuristic_score": 2.5,
    },
    "html": {
        "name": "HTML", "extensions": [".html", ".htm", ".shtml"],
        "aliases": [], "mimetypes": ["text/html"],
        "first_line_patterns": [r"^<!DOCTYPE\s+html", r"^<html"],
        "heuristic_keywords": ["<!DOCTYPE", "<html", "<head>", "<body>", "<div", "<span", "</", "/>"],
        "heuristic_score": 3.0,
    },
    "css": {
        "name": "CSS", "extensions": [".css"],
        "aliases": [], "mimetypes": ["text/css"],
        "heuristic_keywords": ["{", "}", ":", ";", "px", "rem", "em", "#", ".", "@media", "@import"],
        "heuristic_score": 1.0,
    },
    "scss": {
        "name": "SCSS", "extensions": [".scss"],
        "aliases": ["sass"], "mimetypes": ["text/x-scss"],
        "heuristic_keywords": ["$", "@mixin", "@include", "@extend", "&", "@if", "@for", "@each"],
        "heuristic_score": 2.0,
    },
    "json": {
        "name": "JSON", "extensions": [".json", ".jsonc", ".jsonl"],
        "aliases": [], "mimetypes": ["application/json"],
        "first_line_patterns": [r"^\s*[\[{]"],
        "heuristic_keywords": ['"', "{", "}", "[", "]", "true", "false", "null"],
        "heuristic_score": 1.5,
    },
    "markdown": {
        "name": "Markdown", "extensions": [".md", ".mdx", ".markdown"],
        "aliases": ["md"], "mimetypes": ["text/markdown"],
        "heuristic_keywords": ["# ", "## ", "### ", "```", "**", "* ", "- ", "1. ", "> ", "[", "]("],
        "heuristic_score": 3.0,
    },
    "xml": {
        "name": "XML", "extensions": [".xml", ".xsl", ".xsd", ".svg"],
        "aliases": [], "mimetypes": ["application/xml", "text/xml"],
        "first_line_patterns": [r"^<\?xml"],
        "heuristic_keywords": ["<?xml", "<", "/>", "xmlns"],
        "heuristic_score": 2.5,
    },
    "yaml": {
        "name": "YAML", "extensions": [".yml", ".yaml"],
        "aliases": ["yml"], "mimetypes": ["text/yaml"],
        "heuristic_keywords": [": ", "---", "  - ", "  ", "&", "*ref"],
        "heuristic_score": 1.5,
    },
    "sql": {
        "name": "SQL", "extensions": [".sql", ".psql"],
        "aliases": [], "mimetypes": ["text/x-sql"],
        "heuristic_keywords": ["SELECT ", "INSERT ", "UPDATE ", "DELETE ", "CREATE TABLE", "ALTER TABLE", "FROM ", "WHERE ", "JOIN "],
        "heuristic_score": 3.0,
    },
    "shellscript": {
        "name": "Shell Script", "extensions": [".sh", ".bash", ".zsh", ".fish"],
        "aliases": ["bash", "shell", "sh"], "mimetypes": ["text/x-shellscript"],
        "first_line_patterns": [r"^#!.*\b(bash|sh|zsh|fish)\b"],
        "heuristic_keywords": ["#!/bin/", "echo ", "export ", "$", "if [", "fi", "done", "esac", "source "],
        "heuristic_score": 2.0,
    },
    "java": {
        "name": "Java", "extensions": [".java"],
        "aliases": [], "mimetypes": ["text/x-java"],
        "heuristic_keywords": ["public class ", "private ", "protected ", "void ", "int ", "String ", "static ", "import java."],
        "heuristic_score": 2.5,
    },
    "cpp": {
        "name": "C++", "extensions": [".cpp", ".cc", ".cxx", ".hpp", ".hxx", ".h"],
        "aliases": ["c++"], "mimetypes": ["text/x-c++src"],
        "heuristic_keywords": ["#include", "std::", "cout", "cin", "namespace ", "template<", "vector<"],
        "heuristic_score": 2.0,
    },
    "c": {
        "name": "C", "extensions": [".c", ".h"],
        "aliases": [], "mimetypes": ["text/x-csrc"],
        "heuristic_keywords": ["#include", "printf(", "scanf(", "malloc(", "free(", "int main(", "void ", "struct "],
        "heuristic_score": 2.0,
    },
    "csharp": {
        "name": "C#", "extensions": [".cs", ".csx"],
        "aliases": ["c#"], "mimetypes": ["text/x-csharp"],
        "heuristic_keywords": ["using System", "namespace ", "class ", "void ", "string ", "var ", "Console.", "async "],
        "heuristic_score": 2.0,
    },
    "go": {
        "name": "Go", "extensions": [".go"],
        "aliases": ["golang"], "mimetypes": ["text/x-go"],
        "heuristic_keywords": ["package ", "import (", "func ", "fmt.", "err ", ":= ", "go ", "defer ", "chan "],
        "heuristic_score": 2.5,
    },
    "rust": {
        "name": "Rust", "extensions": [".rs"],
        "aliases": [], "mimetypes": ["text/x-rust"],
        "heuristic_keywords": ["fn ", "let ", "let mut", "impl ", "struct ", "enum ", "pub ", "use ", "match ", "&self"],
        "heuristic_score": 2.5,
    },
    "ruby": {
        "name": "Ruby", "extensions": [".rb", ".rbw"],
        "aliases": [], "mimetypes": ["text/x-ruby"],
        "first_line_patterns": [r"^#!.*\bruby\b"],
        "heuristic_keywords": ["def ", "end", "class ", "module ", "require ", "puts ", "attr_", "do |"],
        "heuristic_score": 2.0,
    },
    "php": {
        "name": "PHP", "extensions": [".php", ".phtml"],
        "aliases": [], "mimetypes": ["text/x-php"],
        "first_line_patterns": [r"^<\?php"],
        "heuristic_keywords": ["<?php", "$", "function ", "echo ", "->", "::", "array(", "namespace "],
        "heuristic_score": 2.5,
    },
    "kotlin": {
        "name": "Kotlin", "extensions": [".kt", ".kts"],
        "aliases": [], "mimetypes": ["text/x-kotlin"],
        "heuristic_keywords": ["fun ", "val ", "var ", "class ", "object ", "when ", "suspend ", "data class"],
        "heuristic_score": 2.0,
    },
    "swift": {
        "name": "Swift", "extensions": [".swift"],
        "aliases": [], "mimetypes": ["text/x-swift"],
        "heuristic_keywords": ["import Foundation", "var ", "let ", "func ", "class ", "struct ", "guard ", "@IBAction"],
        "heuristic_score": 2.0,
    },
    "r": {
        "name": "R", "extensions": [".r", ".R"],
        "aliases": [], "mimetypes": ["text/x-r"],
        "heuristic_keywords": ["<- ", "library(", "ggplot(", "data.frame", "c(", "function("],
        "heuristic_score": 2.0,
    },
    "dart": {
        "name": "Dart", "extensions": [".dart"],
        "aliases": [], "mimetypes": ["text/x-dart"],
        "heuristic_keywords": ["import 'package:", "void main(", "Widget ", "build(", "class ", "final ", "const "],
        "heuristic_score": 2.0,
    },
    "vue": {
        "name": "Vue", "extensions": [".vue"],
        "aliases": [], "mimetypes": ["text/x-vue"],
        "heuristic_keywords": ["<template>", "<script", "<style", "export default", "Vue.", "ref(", "computed("],
        "heuristic_score": 2.5,
    },
    "dockerfile": {
        "name": "Dockerfile", "extensions": ["Dockerfile", ".dockerfile"],
        "aliases": ["docker"], "mimetypes": [],
        "heuristic_keywords": ["FROM ", "RUN ", "CMD ", "COPY ", "EXPOSE ", "ENV ", "WORKDIR ", "ENTRYPOINT "],
        "heuristic_score": 3.0,
    },
    "makefile": {
        "name": "Makefile", "extensions": ["Makefile", "makefile", ".mk"],
        "aliases": ["make"], "mimetypes": [],
        "heuristic_keywords": [".PHONY:", "all:", "clean:", "\t", "$(CC)", "$(CFLAGS)"],
        "heuristic_score": 3.0,
    },
    "toml": {
        "name": "TOML", "extensions": [".toml"],
        "aliases": [], "mimetypes": ["text/x-toml"],
        "heuristic_keywords": ["[", "]", "=", '"', '#', "true", "false"],
        "heuristic_score": 1.0,
    },
    "ini": {
        "name": "INI", "extensions": [".ini", ".cfg", ".conf"],
        "aliases": ["properties"], "mimetypes": ["text/x-ini"],
        "heuristic_keywords": ["[", "]", "="],
        "heuristic_score": 1.0,
    },
    "graphql": {
        "name": "GraphQL", "extensions": [".graphql", ".gql"],
        "aliases": ["gql"], "mimetypes": ["application/graphql"],
        "heuristic_keywords": ["query ", "mutation ", "subscription ", "fragment ", "type ", "input ", "{", "}"],
        "heuristic_score": 2.5,
    },
    "plaintext": {
        "name": "Plain Text", "extensions": [".txt", ".text", ".log", ""],
        "aliases": ["text", "plaintext", "txt"], "mimetypes": ["text/plain"],
        "heuristic_keywords": [],
        "heuristic_score": 0.0,
    },
}

# 扩展名 → 语言ID 快速索引
EXT_TO_LANG: dict[str, str] = {}
for lang_id, info in LANGUAGE_REGISTRY.items():
    for ext in info.get("extensions", []):
        ext_lower = ext.lower()
        if ext_lower not in EXT_TO_LANG:
            EXT_TO_LANG[ext_lower] = lang_id
# 文件名映射（无扩展名的）
FILENAME_TO_LANG: dict[str, str] = {
    "dockerfile": "dockerfile",
    "makefile": "makefile",
    "gnumakefile": "makefile",
}


# ── Token 权重 (贝叶斯启发式) ──

def _tokenize(content: str, max_tokens: int = 200) -> list[str]:
    """简单分词：按空白/标点分割 """
    tokens = re.findall(r'[a-zA-Z_]\w*|\S', content[:max_tokens * 20])
    return tokens[:max_tokens]


def _bayesian_score(content: str, language_id: str) -> float:
    """基于关键词频率的贝叶斯启发式评分"""
    info = LANGUAGE_REGISTRY.get(language_id)
    if not info or not info.get("heuristic_keywords"):
        return 0.0
    tokens = _tokenize(content.lower())
    if not tokens:
        return 0.0
    keywords_lower = [kw.lower() for kw in info["heuristic_keywords"]]
    token_set = set(tokens)
    hits = sum(1 for kw in keywords_lower if any(kw in t for t in token_set))
    total_kw = len(keywords_lower)
    ratio = hits / total_kw if total_kw > 0 else 0
    return ratio * info.get("heuristic_score", 1.0)


# ── 检测逻辑 ──

def _detect_by_extension(file_name: Optional[str]) -> List[LanguageCandidate]:
    """Layer 1: 文件扩展名推断 (置信度 0.9)"""
    if not file_name:
        return []
    name_lower = file_name.lower()
    basename = name_lower.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    
    # 先检查文件名 (Dockerfile, Makefile 等)
    if basename in FILENAME_TO_LANG:
        lang_id = FILENAME_TO_LANG[basename]
        info = LANGUAGE_REGISTRY.get(lang_id)
        if info:
            return [LanguageCandidate(
                language_id=lang_id, language_name=info["name"],
                confidence=0.95, source="filename"
            )]
    
    # 再检查扩展名
    for ext, lang_id in EXT_TO_LANG.items():
        if basename.endswith(ext):
            info = LANGUAGE_REGISTRY.get(lang_id)
            if info:
                return [LanguageCandidate(
                    language_id=lang_id, language_name=info["name"],
                    confidence=0.9, source="extension"
                )]
    return []


def _detect_by_shebang(first_line: Optional[str]) -> List[LanguageCandidate]:
    """Layer 2: Shebang/声明检测 (置信度 0.95)"""
    if not first_line:
        return []
    first_line = first_line.strip()
    
    # 检查所有语言的 first_line_patterns
    for lang_id, info in LANGUAGE_REGISTRY.items():
        for pattern in info.get("first_line_patterns", []):
            if re.search(pattern, first_line, re.IGNORECASE):
                return [LanguageCandidate(
                    language_id=lang_id, language_name=info["name"],
                    confidence=0.95, source="shebang"
                )]
    return []


def _detect_by_heuristic(content: str, threshold: float = 0.15) -> List[LanguageCandidate]:
    """Layer 3: 内容启发式 + Token 频次 (置信度 0.5~0.85)"""
    if not content or len(content.strip()) < 5:
        return [LanguageCandidate(
            language_id="plaintext", language_name="Plain Text",
            confidence=0.85, source="heuristic"
        )]
    
    results: List[tuple[str, float]] = []
    for lang_id in LANGUAGE_REGISTRY:
        if lang_id == "plaintext":
            continue
        score = _bayesian_score(content, lang_id)
        if score > threshold:
            results.append((lang_id, score))
    
    results.sort(key=lambda x: -x[1])
    
    if not results:
        return [LanguageCandidate(
            language_id="plaintext", language_name="Plain Text",
            confidence=0.6, source="heuristic"
        )]
    
    # 取前5，归一化置信度
    max_score = results[0][1] if results else 1.0
    candidates = []
    for lang_id, score in results[:5]:
        normalized = min(score / max_score * 0.85, 0.85)
        info = LANGUAGE_REGISTRY.get(lang_id, {})
        candidates.append(LanguageCandidate(
            language_id=lang_id,
            language_name=info.get("name", lang_id),
            confidence=round(normalized, 3),
            source="heuristic"
        ))
    return candidates


# ── API 路由 ──

@router.post("/detect", response_model=DetectResponse)
async def detect_language(req: DetectRequest) -> DetectResponse:
    """
    检测代码语言 — 三层回退策略
    
    1. 文件名扩展名 → 置信度 0.9
    2. Shebang/文档声明 → 置信度 0.95
    3. 内容启发式 Token 频次 → 置信度 0.5~0.85
    
    返回带置信度的候选列表 + 最佳匹配
    """
    candidates: List[LanguageCandidate] = []
    
    # Layer 1: 扩展名
    ext_results = _detect_by_extension(req.file_name)
    if ext_results:
        return DetectResponse(candidates=ext_results, primary=ext_results[0])
    
    # Layer 2: Shebang
    first_line = req.first_line or (req.content.split("\n")[0] if req.content else None)
    shebang_results = _detect_by_shebang(first_line)
    if shebang_results:
        return DetectResponse(candidates=shebang_results, primary=shebang_results[0])
    
    # Layer 3: 内容启发式
    content = req.content or ""
    candidates = _detect_by_heuristic(content)
    primary = candidates[0] if candidates else None
    return DetectResponse(candidates=candidates, primary=primary)


@router.get("/map", response_model=List[LanguageInfo])
async def get_language_map() -> list[LanguageInfo]:
    """获取语言→扩展名映射表"""
    result = []
    for lang_id, info in LANGUAGE_REGISTRY.items():
        result.append(LanguageInfo(
            id=lang_id,
            name=info["name"],
            extensions=info.get("extensions", []),
            aliases=info.get("aliases", []),
            mimetypes=info.get("mimetypes", []),
        ))
    return sorted(result, key=lambda x: x.name)
