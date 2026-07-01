"""
字幕解析器 — 支持 SRT / VTT / ASS 格式解析为结构化 SubtitleCue

使用方式:
    cues = parse_subtitle_file(content, format="srt")
    cues = parse_subtitle_file(content, format="vtt")
"""

from __future__ import annotations

import re
from pathlib import Path

# ── 时间戳解析 ───────────────────────────────────

_TIME_PATTERNS = {
    "srt": re.compile(
        r"(\d+)\s*\n"                     # 序号
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"  # 开始 HH:MM:SS,mmm
        r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})",           # 结束 HH:MM:SS,mmm
    ),
    "vtt": re.compile(
        r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})\s*-->\s*"
        r"(\d{2}):(\d{2}):(\d{2})\.(\d{3})",
    ),
}

_VTT_TIMESTAMP = re.compile(
    r"(?:(\d{2}):)?(\d{2}):(\d{2})\.(\d{3})"
)


def _timestamp_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def _vtt_timestamp_to_seconds(ts: str) -> float:
    m = _VTT_TIMESTAMP.match(ts.strip())
    if not m:
        raise ValueError(f"Invalid VTT timestamp: {ts}")
    hours = int(m.group(1)) if m.group(1) else 0
    mins = int(m.group(2))
    secs = int(m.group(3))
    millis = int(m.group(4))
    return hours * 3600 + mins * 60 + secs + millis / 1000.0


# ── 格式检测 ─────────────────────────────────────

def detect_format(filename: str | Path) -> str:
    """根据文件扩展名检测字幕格式"""
    suffix = Path(filename).suffix.lower()
    mapping = {".srt": "srt", ".vtt": "vtt", ".ass": "ass", ".ssa": "ass"}
    return mapping.get(suffix, "srt")


# ── SRT 解析 ────────────────────────────────────

def parse_srt(content_or_path: str | Path) -> list[dict]:
    """解析 SRT 字幕，返回 [{"sequence":1,"start_time":0.0,...}, ...]"""
    content = _read_content(content_or_path)
    cues = []
    pattern = _TIME_PATTERNS["srt"]

    for match in pattern.finditer(content):
        seq = int(match.group(1))
        start = _timestamp_to_seconds(
            match.group(2), match.group(3), match.group(4), match.group(5)
        )
        end = _timestamp_to_seconds(
            match.group(6), match.group(7), match.group(8), match.group(9)
        )

        # 提取该 cue 后的文本（到下一个 cue 或 EOF）
        text_start = match.end()
        text_end = content.find("\n\n", text_start)
        if text_end == -1:
            text_end = len(content)
        text = content[text_start:text_end].strip()

        # 去掉 VTT 样式标记
        text = _strip_vtt_tags(text)

        if text:
            cues.append({
                "sequence": seq,
                "start_time": start,
                "end_time": end,
                "text": text,
            })

    return cues


# ── VTT 解析 ────────────────────────────────────

def parse_vtt(content_or_path: str | Path) -> list[dict]:
    """解析 WebVTT 字幕"""
    content = _read_content(content_or_path)

    # 移除 WEBVTT 头部
    header_end = content.find("\n\n")
    if header_end != -1 and "WEBVTT" in content[:header_end]:
        content = content[header_end + 2:]

    cues = []
    # VTT cue 块: [可选序号]\nSS:SS.mmm --> SS:SS.mmm [可选 settings]\n文本\n\n
    pattern = re.compile(
        r"(?:(\d+)\s*\n)?"  # 可选序号
        r"(\S+)\s*-->\s*(\S+)(?:\s+[^\n]*)?\n"  # 时间戳 + 可选 settings
        r"((?:.+\n?)+?)(?=\n\n|\Z)",  # 文本
        re.MULTILINE,
    )

    for idx, match in enumerate(pattern.finditer(content), 1):
        seq = int(match.group(1)) if match.group(1) else idx
        start = _vtt_timestamp_to_seconds(match.group(2))
        end = _vtt_timestamp_to_seconds(match.group(3))
        text = match.group(4).strip()
        text = _strip_vtt_tags(text)

        if text:
            cues.append({
                "sequence": seq,
                "start_time": start,
                "end_time": end,
                "text": text,
            })

    return cues


# ── 通用入口 ─────────────────────────────────────

def parse_subtitle_file(
    content_or_path: str | Path,
    fmt: str | None = None,
) -> list[dict]:
    """通用字幕解析入口，自动检测格式或手动指定

    Args:
        content_or_path: 字幕文件路径或文本内容
        fmt: 格式 (srt/vtt/ass)，不指定则按扩展名自动检测

    Returns:
        [{"sequence": 1, "start_time": 0.0, "end_time": 2.5, "text": "Hello"}, ...]
    """
    if fmt is None and isinstance(content_or_path, (str, Path)):
        try:
            fmt = detect_format(str(content_or_path))
        except Exception:
            fmt = "srt"

    fmt = fmt or "srt"

    if fmt == "vtt":
        return parse_vtt(content_or_path)
    elif fmt in ("ass", "ssa"):
        # ASS/SSA 简化为只提取 Dialogue 行
        return _parse_ass(content_or_path)
    else:
        return parse_srt(content_or_path)


# ── ASS/SSA 简化解析 ────────────────────────────

def _parse_ass(content_or_path: str | Path) -> list[dict]:
    content = _read_content(content_or_path)
    cues = []
    seq = 0

    for line in content.splitlines():
        if line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            if len(parts) >= 10:
                try:
                    start = _vtt_timestamp_to_seconds(parts[1].strip())
                    end = _vtt_timestamp_to_seconds(parts[2].strip())
                except ValueError:
                    continue
                text = parts[9].strip()
                # 移除 ASS 样式标签 {\xxx}
                text = re.sub(r"\{[^}]*\}", "", text)
                # 移除 \N 换行
                text = text.replace("\\N", " ").replace("\\n", " ").strip()
                if text:
                    seq += 1
                    cues.append({
                        "sequence": seq,
                        "start_time": start,
                        "end_time": end,
                        "text": text,
                    })
    return cues


# ── 辅助函数 ─────────────────────────────────────

def _read_content(content_or_path: str | Path) -> str:
    if isinstance(content_or_path, Path):
        return content_or_path.read_text(encoding="utf-8")
    # 优先当作路径处理
    path = Path(str(content_or_path))
    if path.exists() and path.is_file():
        return path.read_text(encoding="utf-8")
    return str(content_or_path)


def _strip_vtt_tags(text: str) -> str:
    """移除 VTT 样式标签 <b>, <i>, <u>, <c.xxx>, <v xxx> 等"""
    text = re.sub(r"</?[bius](\.[^>]*)?>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<c\.[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<v\s[^>]*>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<ruby[^>]*>.*?</ruby>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<rt[^>]*>.*?</rt>", "", text, flags=re.IGNORECASE)
    return text.strip()
