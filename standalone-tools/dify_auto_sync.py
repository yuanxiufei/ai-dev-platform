#!/usr/bin/env python3
"""
Dify → 主项目 自动同步守护脚本

部署在 Dify 服务器上，监听 knowledge-data/documents/ 目录变化，
当 Dify 训练完文档后自动回调主项目的 dify-webhook 端点完成同步。

----------------------------------------------------------------------
推荐方案：同网络直连（最简单）
----------------------------------------------------------------------
  1. 将 Dify 容器接入主项目 Docker 网络:
     docker network connect ai-platform-net dify-api

  2. 在 Dify 工作流中添加 HTTP 节点，知识库训练完成后 POST:
     http://backend:8000/api/v1/rag/knowledge-bases/dify-webhook
     Body: {"kb_name":"技术文档","mode":"replace"}

  这样 Dify 通过容器名 backend:8000 直接调用主项目，
  无需 IP、端口、密钥，也无需本脚本。

----------------------------------------------------------------------
备选方案：本脚本（无法共享网络时使用）
----------------------------------------------------------------------

设计原则:
- 主项目不加 watchdog，由 Dify 侧主动触发
- 文件变化后延迟 debounce 再同步（避免频繁触发）
- 支持 inotify（Linux）和 polling（跨平台）两种模式

部署方式 (Dify 侧):
  1. 将此脚本放入 Dify 服务器
  2. pip install watchdog httpx
  3. 配置环境变量或直接传参运行:
     python dify_auto_sync.py \
       --watch-dir /path/to/knowledge-data/documents/ \
       --api-url http://主项目地址:18000/api/v1/rag/knowledge-bases/dify-webhook \
       --kb-name 技术文档 \
       --mode replace

  或在 Dify 的 docker-compose 中作为 sidecar 运行。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("dify-auto-sync")


# ── HTTP 回调 ─────────────────────────────────────────────

async def call_webhook(
    api_url: str,
    kb_name: str,
    doc_dir: str,
    mode: str = "replace",
    secret: str = "",
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    description: str = "",
    timeout: float = 600.0,
) -> bool:
    """调用主项目的 dify-webhook 端点触发同步"""
    import httpx

    payload = {
        "kb_name": kb_name,
        "kb_description": description,
        "doc_dir": doc_dir,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "mode": mode,
        "secret": secret,
    }

    logger.info("Calling webhook: %s (kb=%s, mode=%s)", api_url, kb_name, mode)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(api_url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info(
                "Sync OK: KB=%s docs=%d chunks=%d embedded=%d in %.1fs",
                data.get("kb_name"),
                data.get("total_documents", 0),
                data.get("total_chunks", 0),
                data.get("total_embedded", 0),
                data.get("duration_sec", 0),
            )
            if data.get("errors"):
                for err in data["errors"]:
                    logger.warning("  Sync warning: %s", err)
            return True

    except httpx.HTTPStatusError as e:
        logger.error("Webhook HTTP error %d: %s", e.response.status_code, e.response.text[:500])
        return False
    except httpx.TimeoutException:
        logger.error("Webhook timeout after %.0fs", timeout)
        return False
    except httpx.ConnectError:
        logger.error("Cannot connect to %s — is the main project running?", api_url)
        return False
    except Exception as e:
        logger.exception("Webhook call failed: %s", e)
        return False


# ── inotify 模式 (Linux) ────────────────────────────────

def run_inotify(args):
    """使用 watchdog 的 inotify 监听文件变化"""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        logger.error("watchdog not installed. Run: pip install watchdog")
        sys.exit(1)

    api_url = args.api_url
    kb_name = args.kb_name
    mode = args.mode
    secret = args.secret or os.environ.get("DIFY_WEBHOOK_SECRET", "")
    watch_dir = args.watch_dir
    debounce_sec = args.debounce
    chunk_size = args.chunk_size
    chunk_overlap = args.chunk_overlap
    description = args.description

    if not os.path.isdir(watch_dir):
        logger.error("Watch directory does not exist: %s", watch_dir)
        sys.exit(1)

    logger.info("Watching directory: %s (inotify, debounce=%ds)", watch_dir, debounce_sec)

    # 防抖：变化后等 debounce_sec 秒无新变化才触发
    last_change: float = 0.0
    sync_scheduled: bool = False
    loop = asyncio.new_event_loop()

    async def _debounced_sync():
        nonlocal sync_scheduled, last_change
        await asyncio.sleep(debounce_sec + 0.5)
        # 如果期间又有新变化，跳过
        if time.monotonic() - last_change < debounce_sec:
            sync_scheduled = False
            return
        await call_webhook(
            api_url=api_url,
            kb_name=kb_name,
            doc_dir=watch_dir,
            mode=mode,
            secret=secret,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            description=description,
        )
        sync_scheduled = False

    class DocChangeHandler(FileSystemEventHandler):
        def _on_change(self, path: str):
            nonlocal last_change, sync_scheduled
            # 只关心文档类文件
            ext = os.path.splitext(path)[1].lower()
            valid_exts = {".md", ".txt", ".pdf", ".docx", ".html", ".htm", ".csv", ".json"}
            if ext not in valid_exts:
                return

            logger.info("Detected change: %s", path)
            last_change = time.monotonic()

            if not sync_scheduled:
                sync_scheduled = True
                asyncio.run_coroutine_threadsafe(_debounced_sync(), loop)

        def on_created(self, event):
            if not event.is_directory:
                self._on_change(event.src_path)

        def on_modified(self, event):
            if not event.is_directory:
                self._on_change(event.src_path)

        def on_deleted(self, event):
            if not event.is_directory:
                self._on_change(event.src_path)

        def on_moved(self, event):
            if not event.is_directory:
                self._on_change(event.dest_path)

    observer = Observer()
    observer.schedule(DocChangeHandler(), watch_dir, recursive=True)
    observer.start()

    def _run_loop():
        asyncio.set_event_loop(loop)
        loop.run_forever()

    import threading
    t = threading.Thread(target=_run_loop, daemon=True)
    t.start()

    logger.info("Auto-sync daemon started. Press Ctrl+C to stop.")

    try:
        observer.join()
    except KeyboardInterrupt:
        logger.info("Stopping...")
        observer.stop()
        loop.call_soon_threadsafe(loop.stop)

    observer.join()


# ── Polling 模式 (跨平台) ────────────────────────────────

def run_polling(args):
    """轮询文件变化（跨平台，无 watchdog 依赖）"""
    api_url = args.api_url
    kb_name = args.kb_name
    mode = args.mode
    secret = args.secret or os.environ.get("DIFY_WEBHOOK_SECRET", "")
    watch_dir = args.watch_dir
    interval = args.interval
    debounce_sec = args.debounce
    chunk_size = args.chunk_size
    chunk_overlap = args.chunk_overlap
    description = args.description

    if not os.path.isdir(watch_dir):
        logger.error("Watch directory does not exist: %s", watch_dir)
        sys.exit(1)

    logger.info("Watching directory: %s (polling, interval=%ds, debounce=%ds)",
                watch_dir, interval, debounce_sec)

    valid_exts = {".md", ".txt", ".pdf", ".docx", ".html", ".htm", ".csv", ".json"}
    last_snapshot: dict[str, float] = {}    # filepath → mtime
    last_change: float = 0.0

    async def _main_loop():
        nonlocal last_snapshot, last_change

        async def do_sync():
            await call_webhook(
                api_url=api_url,
                kb_name=kb_name,
                doc_dir=watch_dir,
                mode=mode,
                secret=secret,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                description=description,
            )

        # 首次启动立即同步一次
        logger.info("First run: initial sync")
        await do_sync()

        while True:
            await asyncio.sleep(interval)

            # 扫描目录
            current: dict[str, float] = {}
            for root, _, files in os.walk(watch_dir):
                for fn in files:
                    ext = os.path.splitext(fn)[1].lower()
                    if ext in valid_exts:
                        fp = os.path.join(root, fn)
                        try:
                            current[fp] = os.path.getmtime(fp)
                        except OSError:
                            pass

            # 对比变化
            changed = False
            new_files = set(current.keys()) - set(last_snapshot.keys())
            deleted_files = set(last_snapshot.keys()) - set(current.keys())
            for fp in new_files:
                logger.info("New file detected: %s", fp)
                changed = True
            for fp in deleted_files:
                logger.info("Deleted file: %s", fp)
                changed = True
            for fp in set(current.keys()) & set(last_snapshot.keys()):
                if current[fp] != last_snapshot[fp]:
                    logger.info("Modified file: %s", fp)
                    changed = True

            if changed:
                last_change = time.monotonic()
                last_snapshot = current

                # 防抖等待
                while True:
                    await asyncio.sleep(debounce_sec)
                    # 再次扫描确认无新变化
                    recheck: dict[str, float] = {}
                    for root, _, files in os.walk(watch_dir):
                        for fn in files:
                            ext = os.path.splitext(fn)[1].lower()
                            if ext in valid_exts:
                                fp = os.path.join(root, fn)
                                try:
                                    recheck[fp] = os.path.getmtime(fp)
                                except OSError:
                                    pass
                    if recheck == current:
                        break
                    current = recheck
                    last_snapshot = current

                logger.info("Debounced — triggering sync")
                await do_sync()
            else:
                # 无变化，更新快照（可能有同时间戳的替换）
                last_snapshot = current

    try:
        asyncio.run(_main_loop())
    except KeyboardInterrupt:
        logger.info("Polling stopped.")


# ── 一次性同步 ────────────────────────────────────────────

def run_once(args):
    """执行一次同步后退出（适合 cron 定时任务）"""
    api_url = args.api_url
    kb_name = args.kb_name
    mode = args.mode
    secret = args.secret or os.environ.get("DIFY_WEBHOOK_SECRET", "")
    watch_dir = args.watch_dir
    chunk_size = args.chunk_size
    chunk_overlap = args.chunk_overlap
    description = args.description

    async def _sync():
        ok = await call_webhook(
            api_url=api_url,
            kb_name=kb_name,
            doc_dir=watch_dir,
            mode=mode,
            secret=secret,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            description=description,
        )
        sys.exit(0 if ok else 1)

    asyncio.run(_sync())


# ── CLI 入口 ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Dify → 主项目 知识库自动同步",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
推荐: 同网络直连 → Dify 工作流 HTTP 节点 POST backend:8000，无需本脚本。

备选: 本脚本 (网络不互通时)
  # 持续监听（inotify）
  python dify_auto_sync.py --watch-dir /app/knowledge-data/documents/ \\
      --api-url http://backend:8000/api/v1/rag/knowledge-bases/dify-webhook \\
      --kb-name 技术文档 --mode replace

  # 轮询模式
  python dify_auto_sync.py --watch-dir /app/knowledge-data/documents/ \\
      --api-url http://backend:8000/api/v1/rag/knowledge-bases/dify-webhook \\
      --kb-name 技术文档 --mode replace --method polling --interval 30

  # 一次性同步 (适合 cron: */5 * * * *)
  python dify_auto_sync.py --watch-dir /app/knowledge-data/documents/ \\
      --api-url http://backend:8000/api/v1/rag/knowledge-bases/dify-webhook \\
      --kb-name 技术文档 --mode replace --once
        """,
    )
    parser.add_argument("--watch-dir", required=True,
                        help="Dify 文档目录 (knowledge-data/documents/)")
    parser.add_argument("--api-url", required=True,
                        help="主项目 webhook URL (完整路径)")
    parser.add_argument("--kb-name", required=True,
                        help="主项目中的知识库名称")
    parser.add_argument("--description", default="",
                        help="知识库描述")
    parser.add_argument("--mode", choices=["replace", "append"], default="replace",
                        help="同步模式: replace=清空重导, append=增量追加")
    parser.add_argument("--secret", default="",
                        help="Webhook 密钥 (与 DIFY_WEBHOOK_SECRET 匹配)")
    parser.add_argument("--chunk-size", type=int, default=512)
    parser.add_argument("--chunk-overlap", type=int, default=50)
    parser.add_argument("--method", choices=["inotify", "polling"], default="inotify",
                        help="监听方式: inotify (Linux) 或 polling (跨平台)")
    parser.add_argument("--once", action="store_true",
                        help="执行一次同步后退出 (适合 cron)")
    parser.add_argument("--debounce", type=int, default=5,
                        help="防抖延迟(秒), 默认 5")
    parser.add_argument("--interval", type=int, default=30,
                        help="轮询间隔(秒), 默认 30")
    parser.add_argument("--timeout", type=float, default=600.0,
                        help="HTTP 请求超时(秒), 默认 600")

    args = parser.parse_args()

    if args.once:
        run_once(args)
    elif args.method == "polling":
        run_polling(args)
    else:
        run_inotify(args)


if __name__ == "__main__":
    main()
