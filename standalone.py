"""
独立运行启动器 — 无需 Docker 的一键启动方案

用法:
    python standalone.py                  # 启动所有服务
    python standalone.py --no-watchdog    # 跳过守护进程
    python standalone.py --no-sleep       # 跳过智能休眠
    python standalone.py --port 18080      # 自定义端口
    python standalone.py --help           # 查看帮助

环境要求:
    - Python 3.11+
    - 已安装项目依赖 (uv sync 或 pip install -r requirements.txt)
    - 已配置 .env 文件（环境变量）
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import time
import traceback
from pathlib import Path

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("STANDALONE_MODE", "1")

# ════════════════════════════════════════════════════════
# 日志配置
# ════════════════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("standalone.launcher")


# ════════════════════════════════════════════════════════
# 颜色输出
# ════════════════════════════════════════════════════════

class Colors:
    """终端颜色"""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    CYAN = "\033[36m"

    @staticmethod
    def enabled() -> bool:
        return sys.platform != "win32" or os.getenv("TERM") == "xterm"


def stylize(text: str, *styles: str) -> str:
    if Colors.enabled():
        return "".join(styles) + text + Colors.RESET
    return text


def banner() -> None:
    """打印启动横幅"""
    print()
    print(stylize("╔══════════════════════════════════════════════════════╗", Colors.CYAN))
    print(stylize("║       AI Fullstack Platform - Standalone Runtime      ║", Colors.BOLD + Colors.CYAN))
    print(stylize("║         无需 Docker · 一键启动 · 自愈运行              ║", Colors.DIM))
    print(stylize("╚══════════════════════════════════════════════════════╝", Colors.CYAN))
    print()


class StandaloneLauncher:
    """独立运行启动器。

    完整流程：
    1. 加载环境变量 (.env)
    2. 初始化 FastAPI 应用
    3. 注入 StandaloneManager 及其中间件
    4. 在新的 asyncio loop 中启动 uvicorn
    5. （可选）启动守护进程监控
    """

    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.host: str = args.host or "0.0.0.0"
        self.port: int = args.port or 8000
        self.watchdog_enabled: bool = args.watchdog and not args.no_watchdog
        self.sleep_enabled: bool = not args.no_sleep
        self.auth_enabled: bool = not args.no_auth
        self.reload: bool = args.reload
        self.workers: int = args.workers or 1

        # 运行时对象
        self._manager_started: bool = False
        self._shutdown_event = asyncio.Event()

    async def run(self) -> None:
        """主入口"""
        banner()
        logger.info("Standalone Runtime starting...")
        logger.info("  Python: %s", sys.version.split()[0])
        logger.info("  Host: %s", self.host)
        logger.info("  Port: %d", self.port)
        logger.info("  Watchdog: %s", "enabled" if self.watchdog_enabled else "disabled")
        logger.info("  Smart Sleep: %s", "enabled" if self.sleep_enabled else "disabled")
        logger.info("  API Auth: %s", "enabled" if self.auth_enabled else "disabled")
        logger.info("  Reload: %s", "enabled" if self.reload else "disabled")

        if self.watchdog_enabled:
            await self._run_with_watchdog()
        else:
            await self._run_direct()

    async def _run_direct(self) -> None:
        """直接启动 uvicorn（无守护进程）"""
        import uvicorn

        config = uvicorn.Config(
            app="app.main:app",
            host=self.host,
            port=self.port,
            log_level="info",
            reload=self.reload,
            workers=self.workers if not self.reload else 1,
        )
        server = uvicorn.Server(config)

        # 注册信号处理
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: self._shutdown_event.set())
            except NotImplementedError:
                pass  # Windows 不支持

        # 传入 standalone 配置给 lifespan
        os.environ["STANDALONE_SLEEP_ENABLED"] = str(self.sleep_enabled).lower()
        os.environ["STANDALONE_AUTH_ENABLED"] = str(self.auth_enabled).lower()

        logger.info(stylize("→ Starting uvicorn directly...", Colors.GREEN))
        await server.serve()

    async def _run_with_watchdog(self) -> None:
        """使用守护进程包装启动（进程监控 + 自动重启）"""
        from app.core.standalone.watchdog import ProcessWatchdog, WatchdogConfig

        uvicorn_cmd = [
            sys.executable, "-m", "uvicorn", "app.main:app",
            "--host", self.host,
            "--port", str(self.port),
            "--log-level", "info",
        ]
        if self.workers > 1:
            uvicorn_cmd.extend(["--workers", str(self.workers)])

        wd_config = WatchdogConfig(
            cmd=uvicorn_cmd,
            cwd=str(BACKEND_DIR),
            env={
                "STANDALONE_MODE": "1",
                "STANDALONE_SLEEP_ENABLED": str(self.sleep_enabled).lower(),
                "STANDALONE_AUTH_ENABLED": str(self.auth_enabled).lower(),
            },
            health_check_url=f"http://127.0.0.1:{self.port}/api/v1/utils/health-check/",
            max_restarts=self.args.max_restarts or 10,
            restart_delay_base=2.0,
        )

        watchdog = ProcessWatchdog(wd_config)

        # 注册信号
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: self._shutdown_event.set())
            except NotImplementedError:
                pass

        logger.info(stylize("→ Starting with watchdog supervision...", Colors.GREEN))
        await watchdog.start()

        # 等待关闭信号
        try:
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            pass

        logger.info("Shutdown signal received, stopping watchdog...")
        await watchdog.stop()
        logger.info(stylize("✓ Standalone Runtime stopped.", Colors.GREEN))


# ════════════════════════════════════════════════════════
# CLI 参数解析
# ════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Fullstack Platform — Standalone Runtime Launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python standalone.py                        # 默认启动（含守护+休眠+鉴权）
  python standalone.py --no-watchdog          # 不启用进程守护
  python standalone.py --no-sleep             # 不启用智能休眠
  python standalone.py --no-auth              # 不启用 API 鉴权
  python standalone.py --port 18080            # 自定义端口
  python standalone.py --reload               # 开发模式（热重载）
  python standalone.py --workers 4            # 多 worker 模式
        """,
    )
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=18000, help="监听端口 (默认: 18000)")
    parser.add_argument("--no-watchdog", action="store_true", help="禁用进程守护")
    parser.add_argument("--watchdog", action="store_true", default=True, help="启用进程守护 (默认)")
    parser.add_argument("--no-sleep", action="store_true", help="禁用智能休眠")
    parser.add_argument("--no-auth", action="store_true", help="禁用 API 鉴权")
    parser.add_argument("--reload", action="store_true", help="启用热重载（开发模式）")
    parser.add_argument("--workers", type=int, default=0, help="Uvicorn worker 数量")
    parser.add_argument("--max-restarts", type=int, default=10, help="最大重启次数（0=无限制）")
    return parser.parse_args()


# ════════════════════════════════════════════════════════
# 入口
# ════════════════════════════════════════════════════════

def main() -> None:
    args = parse_args()

    # 检查后端目录
    if not (BACKEND_DIR / "app" / "main.py").exists():
        print(stylize(f"Error: backend not found at {BACKEND_DIR}", Colors.RED))
        print("Please run this script from the project root directory.")
        sys.exit(1)

    launcher = StandaloneLauncher(args)

    try:
        asyncio.run(launcher.run())
    except KeyboardInterrupt:
        print()
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error("Fatal error: %s\n%s", e, traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    main()
