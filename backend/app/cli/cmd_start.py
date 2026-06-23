"""
start 子命令 — 借鉴 GPUStack cmd/start.py

启动 API 服务器，支持所有运行时参数。
配置来源优先级: CLI args > 环境变量 > .env 文件
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any


def register_start_parser(subparsers: argparse._SubParsersAction) -> None:
    """注册 start 子命令的参数"""
    p = subparsers.add_parser("start", help="启动 API 服务器")
    # ── 服务器核心参数 ──
    p.add_argument("--host", default="0.0.0.0", help="绑定地址 (默认: 0.0.0.0)")
    p.add_argument("--port", type=int, default=18000, help="绑定端口 (默认: 18000)")
    p.add_argument("--workers", type=int, default=1, help="工作进程数 (默认: 1)")
    p.add_argument("--reload", action="store_true", help="开发模式热重载")
    # ── 数据库 ──
    p.add_argument("--db-url", default=None, help="数据库连接字符串 (环境变量: DATABASE_URL)")
    # ── 模型配置 ──
    p.add_argument("--models-dir", default=None, help="模型存储目录 (环境变量: MODELS_DIR)")
    p.add_argument("--prefer-local", type=_bool_or_default, default=None,
                   help="优先使用本地模型 (true/false)")
    # ── GPU/资源 ──
    p.add_argument("--gpu-enabled", type=_bool_or_default, default=None,
                   help="启用 GPU 控制层 (true/false)")
    p.add_argument("--resource-collector-interval", type=float, default=None,
                   help="资源采集间隔秒数")
    # ── Auth ──
    p.add_argument("--api-key-enabled", type=_bool_or_default, default=None,
                   help="启用 API Key 认证 (true/false)")
    # ── 远程代理 ──
    p.add_argument("--remote-agent-enabled", type=_bool_or_default, default=None,
                   help="启用远程代理 (true/false)")
    p.add_argument("--port-forward-range", default=None,
                   help="端口转发范围 (格式: 10000-20000)")
    # ── 日志 ──
    p.add_argument("--log-level", default=None,
                   choices=["debug", "info", "warning", "error"],
                   help="日志级别")


def _bool_or_default(val: str) -> bool:
    """解析布尔值，用于 argparse OptionalBool"""
    if val.lower() in ("true", "1", "yes"):
        return True
    if val.lower() in ("false", "0", "no"):
        return False
    raise argparse.ArgumentTypeError(f"Invalid boolean: {val}")


def handle_start(args: argparse.Namespace) -> None:
    """执行 start 命令"""
    # 将 CLI 参数注入环境变量（当前进程级别）
    _inject_env_from_args(args)

    print(f"🚀 Starting AI Fullstack Platform on {args.host}:{args.port}...")
    print(f"   Workers: {args.workers} | Reload: {args.reload}")
    print(f"   Models Dir: {args.models_dir or os.getenv('MODELS_DIR', 'models/')}")

    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=args.host,
        port=args.port,
        workers=args.workers if not args.reload else 1,
        reload=args.reload,
        log_level=args.log_level or "info",
    )


def _inject_env_from_args(args: argparse.Namespace) -> None:
    """将 CLI 参数注入环境变量（None 值不覆盖已有环境变量）"""
    mappings: dict[str, str | None] = {
        "DATABASE_URL": getattr(args, "db_url", None),
        "MODELS_DIR": getattr(args, "models_dir", None),
        "MODEL_PREFER_LOCAL": _bool_to_env(args, "prefer_local"),
        "GPU_ENABLED": _bool_to_env(args, "gpu_enabled"),
        "RESOURCE_COLLECTOR_INTERVAL": _float_to_env(args, "resource_collector_interval"),
        "API_KEY_ENABLED": _bool_to_env(args, "api_key_enabled"),
        "REMOTE_AGENT_ENABLED": _bool_to_env(args, "remote_agent_enabled"),
        "LOG_LEVEL": getattr(args, "log_level", None),
    }
    for env_key, val in mappings.items():
        if val is not None:
            os.environ[env_key] = val


def _bool_to_env(args: argparse.Namespace, field: str) -> str | None:
    val = getattr(args, field, None)
    if val is None:
        return None
    return "true" if val else "false"


def _float_to_env(args: argparse.Namespace, field: str) -> str | None:
    val = getattr(args, field, None)
    if val is None:
        return None
    return str(val)
