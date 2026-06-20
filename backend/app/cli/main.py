"""
CLI 主入口 — 借鉴 GPUStack gpustack/main.py 的 argparse 子命令模式
"""
from __future__ import annotations

import argparse
import sys
from typing import Sequence


def build_parser() -> argparse.ArgumentParser:
    """构建 CLI 参数解析器（子命令模式）"""
    parser = argparse.ArgumentParser(
        prog="ai-platform",
        description="AI Fullstack Platform — CLI 管理工具",
    )
    parser.add_argument(
        "-V", "--version",
        action="store_true",
        help="显示版本信息",
    )
    subparsers = parser.add_subparsers(dest="command", help="可用子命令")

    # ── start ──
    from app.cli.cmd_start import register_start_parser
    register_start_parser(subparsers)

    # ── models ──
    from app.cli.cmd_models import register_models_parser
    register_models_parser(subparsers)

    # ── config ──
    from app.cli.cmd_config import register_config_parser
    register_config_parser(subparsers)

    # ── migrate ──
    from app.cli.cmd_migrate import register_migrate_parser
    register_migrate_parser(subparsers)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    """CLI 入口函数"""
    parser = build_parser()

    if argv is None:
        argv = sys.argv[1:]

    # 无参数时打印帮助
    if not argv:
        parser.print_help()
        return

    args = parser.parse_args(argv)

    # --version 短路径
    if args.version and not args.command:
        from app.cli.cmd_version import show_version
        show_version()
        return

    # 分发到子命令处理器
    if args.command == "start":
        from app.cli.cmd_start import handle_start
        handle_start(args)
    elif args.command == "models":
        from app.cli.cmd_models import handle_models
        handle_models(args)
    elif args.command == "config":
        from app.cli.cmd_config import handle_config
        handle_config(args)
    elif args.command == "migrate":
        from app.cli.cmd_migrate import handle_migrate
        handle_migrate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
