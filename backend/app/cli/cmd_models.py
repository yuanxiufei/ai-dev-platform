"""
models 子命令 — 借鉴 GPUStack 模型管理 CLI 模式

子子命令:
  ai-platform models list       — 列出所有注册模型
  ai-platform models download   — 下载模型
  ai-platform models load       — 加载模型到内存
  ai-platform models unload     — 卸载模型
  ai-platform models info NAME  — 模型详情
"""
from __future__ import annotations

import argparse
import asyncio
from typing import Any


def register_models_parser(subparsers: argparse._SubParsersAction) -> None:
    """注册 models 子命令及其子子命令"""
    p = subparsers.add_parser("models", help="模型管理")
    sub = p.add_subparsers(dest="models_action", help="操作")

    # list
    sub.add_parser("list", help="列出所有注册模型")

    # download
    dl = sub.add_parser("download", help="下载模型")
    dl.add_argument("name", help="模型名称 (如: qwen25-coder-7b)")
    dl.add_argument("--source", choices=["huggingface", "modelscope"], default="huggingface",
                    help="下载源 (默认: huggingface)")

    # load
    ld = sub.add_parser("load", help="加载模型到内存")
    ld.add_argument("name", help="模型名称")

    # unload
    ul = sub.add_parser("unload", help="卸载模型")
    ul.add_argument("name", help="模型名称")

    # info
    inf = sub.add_parser("info", help="模型详情")
    inf.add_argument("name", help="模型名称")


def handle_models(args: argparse.Namespace) -> None:
    """执行 models 子命令"""
    action = args.models_action

    if action == "list":
        _list_models()
    elif action == "download":
        _download_model(args.name, args.source)
    elif action == "load":
        _load_model(args.name)
    elif action == "unload":
        _unload_model(args.name)
    elif action == "info":
        _model_info(args.name)
    else:
        print("请指定操作: list | download | load | unload | info")


def _list_models() -> None:
    """列出所有注册模型"""
    try:
        from app.core.model_router import get_model_router
        router = get_model_router()
        if router and router.registry:
            models = router.registry.list_all()
        else:
            # 尝试从 scheduler 获取
            from app.ai_models.scheduler import get_scheduler
            sched = get_scheduler()
            models = sched.list_models() if sched else []
    except Exception:
        models = []

    if not models:
        print("(没有已注册的模型)")
        return

    print(f"{'名称':<30} {'能力':<20} {'优先级':<8} {'类型'}")
    print("-" * 75)
    for m in models:
        name = getattr(m, "name", getattr(m, "model_name", "unknown"))
        caps = getattr(m, "capabilities", None)
        if caps and isinstance(caps, list) and len(caps) > 0:
            capability = caps[0]
        else:
            capability = getattr(m, "capability", "-")
        priority = getattr(m, "base_priority", getattr(m, "priority", "-"))
        mtype = getattr(m, "source", "local")
        print(f"{name:<30} {str(capability):<20} {str(priority):<8} {mtype}")


def _download_model(name: str, source: str) -> None:
    """下载模型（同步 CLI 路径）"""
    print(f"⬇ 正在从 {source} 下载模型: {name}")
    try:
        from app.core.model_downloader import get_downloader
        downloader = get_downloader()
        if downloader:
            result = asyncio.get_event_loop().run_until_complete(
                downloader.download(name, source=source)
            )
            print(f"✅ 下载完成: {result}")
        else:
            print("⚠ 模型下载器未初始化，请先启动服务器")
    except Exception as e:
        print(f"❌ 下载失败: {e}")


def _load_model(name: str) -> None:
    """加载模型到内存"""
    print(f"📦 正在加载模型: {name}")
    try:
        from app.ai_models.scheduler import get_scheduler
        scheduler = get_scheduler()
        if scheduler:
            result = scheduler.load_model(name)
            print(f"✅ 加载完成: {result}")
        else:
            print("⚠ 调度器未初始化")
    except Exception as e:
        print(f"❌ 加载失败: {e}")


def _unload_model(name: str) -> None:
    """卸载模型"""
    print(f"🗑 正在卸载模型: {name}")
    try:
        from app.ai_models.scheduler import get_scheduler
        scheduler = get_scheduler()
        if scheduler:
            scheduler.unload_model(name)
            print(f"✅ 已卸载: {name}")
        else:
            print("⚠ 调度器未初始化")
    except Exception as e:
        print(f"❌ 卸载失败: {e}")


def _model_info(name: str) -> None:
    """查看模型详情"""
    try:
        from app.ai_models.registry import get_registry
        registry = get_registry()
        if registry:
            model = registry.get(name)
            if model:
                print(f"名称:     {model.name}")
                print(f"能力:     {getattr(model, 'capability', '-')}")
                print(f"优先级:   {getattr(model, 'base_priority', getattr(model, 'priority', '-'))}")
                print(f"来源:     {getattr(model, 'source', 'local')}")
                print(f"位置:     {getattr(model, 'path', '-')}")
                print(f"可用:     {getattr(model, 'available', 'unknown')}")
                print(f"评分:     {getattr(model, 'dynamic_score', '-')}")
                return
        print(f"❌ 未找到模型: {name}")
    except Exception as e:
        print(f"❌ 查询失败: {e}")
