"""
远程终端 WebSocket 通道 — 借鉴 OpenVSCode RemoteTerminalChannelClient

通过 WebSocket 提供终端数据流传输:
  - 客户端 → 服务端: input/resize/shutdown
  - 服务端 → 客户端: data/exit/title_changed
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.core.terminal import PTYProcessBackend, TerminalSize

logger = logging.getLogger(__name__)


class TerminalWebSocketChannel:
    """终端 WebSocket 通道

    封装 PTY 后端与 WebSocket 之间的双向通信:
    - 接收客户端输入/控制消息
    - 将 PTY 输出推送到客户端
    """

    def __init__(
        self,
        websocket: WebSocket,
        backend: PTYProcessBackend,
        session_id: str,
    ) -> None:
        self._ws = websocket
        self._backend = backend
        self._session_id = session_id
        self._terminal_id: str | None = None
        self._alive: bool = True

    async def handle(self) -> None:
        """主处理循环: 创建终端 + 双向通信"""
        await self._ws.accept()

        try:
            # 1. 等待 INIT 消息
            init_msg = await self._ws.receive_text()
            init_data = json.loads(init_msg)

            if init_data.get("type") != "init":
                await self._ws.send_json({"type": "error", "message": "Expected init message"})
                return

            # 2. 创建 PTY 进程
            shell = init_data.get("shell", "/bin/bash")
            cwd = init_data.get("cwd")
            env = init_data.get("env")
            rows = init_data.get("rows", 24)
            cols = init_data.get("cols", 80)

            self._terminal_id = self._backend.create_process(
                session_id=self._session_id,
                shell=shell,
                cwd=cwd,
                env=env,
                size=TerminalSize(rows=rows, cols=cols),
            )

            # 3. 注册数据回调 → 推送到 WebSocket
            async def on_terminal_data(_tid: str, data: bytes) -> None:
                if self._alive:
                    try:
                        await self._ws.send_bytes(data)
                    except Exception:
                        self._alive = False

            def sync_on_data(_tid: str, data: bytes) -> None:
                # 同步回调包装
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    loop.create_task(on_terminal_data(_tid, data))
                except RuntimeError:
                    pass

            self._backend.on_data(self._terminal_id, sync_on_data)

            # 4. 注册退出回调
            async def on_terminal_exit(_tid: str, exit_code: int) -> None:
                if self._alive:
                    await self._ws.send_json({
                        "type": "exit",
                        "exit_code": exit_code,
                    })

            def sync_on_exit(_tid: str, exit_code: int) -> None:
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    loop.create_task(on_terminal_exit(_tid, exit_code))
                except RuntimeError:
                    pass

            self._backend.on_exit(self._terminal_id, sync_on_exit)

            # 5. 发送 READY
            await self._ws.send_json({"type": "ready", "terminal_id": self._terminal_id})

            # 6. 主循环: 接收客户端消息
            while self._alive:
                msg = await self._ws.receive_text()
                data = json.loads(msg)
                msg_type = data.get("type")

                if msg_type == "input":
                    self._backend.write(self._terminal_id, data.get("data", ""))
                elif msg_type == "resize":
                    self._backend.resize(
                        self._terminal_id,
                        rows=data.get("rows", 24),
                        cols=data.get("cols", 80),
                    )
                elif msg_type == "shutdown":
                    break
                elif msg_type == "ping":
                    await self._ws.send_json({"type": "pong"})

        except WebSocketDisconnect:
            logger.info("Terminal WebSocket disconnected: session=%s", self._session_id)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON from terminal client: %s", e)
        except Exception as e:
            logger.error("Terminal WebSocket error: %s", e)
        finally:
            self._alive = False
            if self._terminal_id:
                self._backend.shutdown(self._terminal_id)
            try:
                await self._ws.close()
            except Exception:
                pass
