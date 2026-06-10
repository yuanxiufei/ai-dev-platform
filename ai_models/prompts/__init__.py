"""
AI Models 的 Prompt 模板子包。

包含两类模板：
  - code_gen.py  : 代码生成相关（截图→布局、布局→代码、全栈项目、API 生成）
  - video_gen.py : 视频生成相关（文本→视频、UI 演示视频、风格模板）

所有模板都是 str 类型的 Python 常量，使用 .format() 填入参数。
变量占位符见各文件顶部的 docstring。

Usage:
    from ai_models.prompts.code_gen import LAYOUT_TO_CODE
    prompt = LAYOUT_TO_CODE.format(framework="vue", layout_json=json_str)
"""

from ai_models.prompts.code_gen import (
    SCREENSHOT_TO_LAYOUT,
    LAYOUT_TO_CODE,
    TEXT_TO_FULLSTACK,
    PROJECT_STRUCTURE,
    API_GENERATION,
)
from ai_models.prompts.video_gen import (
    TEXT_TO_VIDEO,
    UI_DEMO_VIDEO,
    VIDEO_STYLE_TEMPLATES,
)

__all__ = [
    # code_gen
    "SCREENSHOT_TO_LAYOUT",
    "LAYOUT_TO_CODE",
    "TEXT_TO_FULLSTACK",
    "PROJECT_STRUCTURE",
    "API_GENERATION",
    # video_gen
    "TEXT_TO_VIDEO",
    "UI_DEMO_VIDEO",
    "VIDEO_STYLE_TEMPLATES",
]
