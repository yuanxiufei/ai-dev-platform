"""
config 子命令 — 借鉴 GPUStack cmd/reload_config.py

子子命令:
  ai-platform config show      — 显示当前配置（脱敏）
  ai-platform config reload    — 热加载配置
"""
from __future__ import annotations

import argparse
import os


_SENSITIVE_KEYS = {
    "SECRET_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY",
    "AZURE_OPENAI_API_KEY", "REPLICATE_API_KEY", "ZHIPU_API_KEY", "QWEN_API_KEY",
    "DATABASE_URL", "JWT_SECRET_KEY",
}


def register_config_parser(subparsers: argparse._SubParsersAction) -> None:
    """注册 config 子命令"""
    p = subparsers.add_parser("config", help="配置管理")
    sub = p.add_subparsers(dest="config_action", help="操作")

    # show
    sub.add_parser("show", help="显示当前配置")

    # reload
    rl = sub.add_parser("reload", help="热加载配置")
    rl.add_argument("--server-url", default="http://localhost:8000",
                    help="API 服务器地址 (默认: http://localhost:8000)")


def handle_config(args: argparse.Namespace) -> None:
    """执行 config 子命令"""
    action = args.config_action

    if action == "show":
        _show_config()
    elif action == "reload":
        _reload_config(getattr(args, "server_url", "http://localhost:8000"))
    else:
        print("请指定操作: show | reload")


def _show_config() -> None:
    """显示当前配置（敏感值脱敏）"""
    try:
        from app.core.config import settings
        print("当前配置 (敏感值已脱敏):")
        print("-" * 50)

        # 使用 model_dump 获取所有字段
        try:
            config_dict = settings.model_dump()
        except AttributeError:
            config_dict = settings.dict()

        for key in sorted(config_dict.keys()):
            if key.startswith("_"):
                continue
            val = config_dict[key]
            if key.upper() in _SENSITIVE_KEYS and val:
                val = _mask_value(val)
            print(f"  {key} = {val}")
    except Exception as e:
        print(f"❌ 无法读取配置: {e}")


def _reload_config(server_url: str) -> None:
    """通过 API 热加载配置"""
    import urllib.request
    import json

    url = f"{server_url.rstrip('/')}/api/v1/system/config/reload"
    print(f"🔄 正在请求热加载: {url}")

    try:
        req = urllib.request.Request(url, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            print(f"✅ 配置已热加载: {data}")
    except urllib.error.HTTPError as e:
        print(f"❌ 服务器返回错误 {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        print(f"❌ 无法连接服务器 ({server_url}): {e.reason}")
    except Exception as e:
        print(f"❌ 热加载失败: {e}")


def _mask_value(val: str) -> str:
    """脱敏字符串值"""
    if len(val) <= 8:
        return "***"
    return val[:4] + "****" + val[-4:]
