"""
migrate 子命令 — 数据库迁移

借鉴 GPUStack cmd/db_migration.py 的 SQLite→PostgreSQL 迁移模式
"""
from __future__ import annotations

import argparse
import os
import sys


def register_migrate_parser(subparsers: argparse._SubParsersAction) -> None:
    """注册 migrate 子命令"""
    p = subparsers.add_parser("migrate", help="数据库迁移")
    sub = p.add_subparsers(dest="migrate_action", help="操作")

    # upgrade — 应用迁移
    up = sub.add_parser("upgrade", help="应用所有待处理的迁移")
    up.add_argument("--revision", default="head", help="目标版本 (默认: head)")

    # downgrade — 回退迁移
    down = sub.add_parser("downgrade", help="回退迁移")
    down.add_argument("revision", help="目标版本")

    # current — 查看当前版本
    sub.add_parser("current", help="查看当前迁移版本")

    # history — 查看迁移历史
    sub.add_parser("history", help="查看迁移历史")

    # generate — 自动生成迁移
    gen = sub.add_parser("generate", help="自动生成迁移文件")
    gen.add_argument("--message", "-m", default="auto", help="迁移描述信息")


def handle_migrate(args: argparse.Namespace) -> None:
    """执行 migrate 子命令"""
    action = args.migrate_action

    # 确保在项目根目录
    _ensure_backend_root()

    if action == "upgrade":
        _run_alembic("upgrade", getattr(args, "revision", "head"))
    elif action == "downgrade":
        _run_alembic("downgrade", args.revision)
    elif action == "current":
        _run_alembic("current")
    elif action == "history":
        _run_alembic("history")
    elif action == "generate":
        msg = getattr(args, "message", "auto")
        _run_alembic("revision", "--autogenerate", "-m", msg)
    else:
        print("请指定操作: upgrade | downgrade | current | history | generate")


def _ensure_backend_root() -> None:
    """确保工作目录在 backend/ 下"""
    if not os.path.exists("alembic.ini") and not os.path.exists("alembic"):
        # 尝试找到 backend 目录
        if os.path.basename(os.getcwd()) != "backend":
            backend_dir = os.path.join(os.getcwd(), "backend")
            if os.path.isdir(backend_dir):
                os.chdir(backend_dir)
                print(f"📂 切换工作目录到: {backend_dir}")


def _run_alembic(*args: str) -> None:
    """执行 alembic 命令"""
    print(f"🔄 alembic {' '.join(args)}")
    from alembic.config import main as alembic_main
    try:
        alembic_main(argv=list(args))
    except SystemExit as e:
        if e.code != 0:
            print(f"❌ 迁移失败 (exit code: {e.code})")
            sys.exit(e.code)
