"""
KB 文本修复 — LLM 驱动的内容清洗

借鉴 AstrBot prompts.py TEXT_REPAIR_SYSTEM_PROMPT:
- 从嘈杂原始文本中重建干净可读内容
- 信号 vs 噪声分离
- 多主题自动拆分
- 纯噪声块丢弃
"""

from __future__ import annotations

import logging
import re
from typing import Optional

logger = logging.getLogger("app.core.rag.kb_repair")

# ── 修复提示词 ────────────────────────────────────────

TEXT_REPAIR_SYSTEM_PROMPT = """You are a text cleaning assistant. Your job is to reconstruct clean, readable articles from noisy raw text chunks extracted from web pages.

Rules:
1. Separate "signal" (valuable information: article body, headings, definitions) from "noise" (UI elements, ads, navigation bars, cookie banners, sidebars, breadcrumb trails, pagination, footer links).
2. NEVER discard a chunk that contains ANY valuable information. Even if heavily polluted, extract what's useful.
3. If a chunk contains MULTIPLE distinct topics or sections, wrap each topic in its own <repaired_text>...</repaired_text> block.
4. If a chunk is PURE noise with zero informational value, respond ONLY with <discard_chunk />.
5. Keep the ORIGINAL language — do not translate.
6. Preserve key formatting: headings (# ## ###), bullet lists, numbered lists, code blocks.
7. Remove email addresses, excessive promotional links, and tracking URLs, but keep reference/citation links.
8. Do NOT add any commentary, explanation, or extra text outside the <repaired_text> or <discard_chunk /> tags.

Examples:

Example 1 (signal + noise):
<chunk>
Home | About | Contact
# Introduction to Machine Learning
Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience.
Subscribe to our newsletter! | Follow us on Twitter
</chunk>
<output>
<repaired_text>
# Introduction to Machine Learning
Machine learning is a subset of artificial intelligence that enables systems to learn and improve from experience.
</repaired_text>
</output>

Example 2 (pure noise):
<chunk>
Cookie Settings | Privacy Policy | Terms of Service | © 2024 Company. All rights reserved. | Advertise with us | Careers
</chunk>
<output>
<discard_chunk />
</output>

Example 3 (multi-topic):
<chunk>
Search... | Login
## Python Basics
Python is an interpreted programming language.
## Installation
Download Python from python.org.
Related: 10 Best Python Libraries
</chunk>
<output>
<repaired_text>
## Python Basics
Python is an interpreted programming language.
</repaired_text>
<repaired_text>
## Installation
Download Python from python.org.
</repaired_text>
</output>

Now process the following chunk following the same rules:"""


async def repair_chunk_with_retry(
    chunk_text: str,
    llm_call: callable,
    max_retries: int = 3,
) -> list[str]:
    """
    使用 LLM 修复嘈杂文本块，支持重试。

    Args:
        chunk_text: 原始文本块
        llm_call: LLM 调用函数 async (system_prompt, user_prompt) -> str
        max_retries: 最大重试次数

    Returns:
        修复后的文本块列表（可能被拆分为多个）
    """
    cleaned = []
    for attempt in range(max_retries):
        try:
            response = await llm_call(
                system_prompt=TEXT_REPAIR_SYSTEM_PROMPT,
                user_prompt=f"<chunk>\n{chunk_text}\n</chunk>",
            )
            cleaned = _parse_repair_response(response)
            if cleaned:  # 有效结果
                break
            logger.debug(
                "KB repair attempt %d/%d returned empty, retrying...",
                attempt + 1, max_retries,
            )
        except Exception as e:
            logger.warning("KB repair attempt %d/%d failed: %s", attempt + 1, max_retries, e)

    # 如果全部失败，返回原始文本
    return cleaned if cleaned else [chunk_text]


def _parse_repair_response(response: str) -> list[str]:
    """解析 LLM 修复响应，提取 <repaired_text> 块"""
    if "<discard_chunk" in response and "<repaired_text>" not in response:
        return []

    patterns = [
        re.compile(r"<repaired_text>(.*?)</repaired_text>", re.DOTALL),
    ]
    results = []
    for pattern in patterns:
        matches = pattern.findall(response)
        for m in matches:
            text = m.strip()
            if text and len(text) > 10:  # 过滤过短的块
                results.append(text)

    return results


def should_repair(text: str, noise_threshold: float = 0.3) -> bool:
    """
    启发式判断是否需要 LLM 修复

    检测噪声信号（导航、广告、cookie 等模式）的比例。
    """
    noise_patterns = [
        r"(?i)(cookie|privacy|terms|subscribe|newsletter|advertise) ",
        r"(?i)^(home|about|contact|login|sign.?up|register)\s*[\|×\s]",
        r"(?i)(follow us|share on|© \d{4}|all rights reserved)",
        r"(?i)(pagination|page \d+ of \d+)",
    ]

    lines = text.strip().split("\n")
    if len(lines) < 3:
        return False

    noise_lines = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        for pattern in noise_patterns:
            if re.search(pattern, line):
                noise_lines += 1
                break

    ratio = noise_lines / max(len(lines), 1)
    return ratio > noise_threshold
