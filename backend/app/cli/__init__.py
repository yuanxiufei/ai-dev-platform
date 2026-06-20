"""
CLI 命令行工具 — 借鉴 GPUStack cmd/ 架构

统一入口: ai-platform <subcommand>

子命令:
  start       — 启动 API 服务器（Server 模式）
  models      — 模型管理（list/download/load/unload）
  config      — 配置管理（show/reload）
  migrate     — 数据库迁移
  version     — 版本信息
"""

from app.cli.main import main

__all__ = ["main"]
