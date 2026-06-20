"""
version 子命令 — 显示版本信息
"""
from __future__ import annotations

import sys


__version__ = "0.2.0"


def show_version() -> None:
    """打印版本信息"""
    print(f"ai-platform v{__version__}")
    print(f"Python {sys.version}")
