"""
DDNSManager — 动态域名解析管理（阿里云 DNS）

核心能力：
1. 自动检测公网 IPv4/IPv6 地址变化
2. 通过阿里云 DNS API 更新 A/AAAA 记录
3. 后台守护模式持续检测 IP 变化
4. 支持多子域名、多记录类型管理
5. 完全可扩展，支持未来接入 Cloudflare / 腾讯云 DNS 等

与 standalone-tools/ddns/aliddns.py 的关系：
- 本模块复用 aliddns.py 的核心逻辑（通过 import）
- 同时可作为独立脚本运行：python standalone-tools/ddns/aliddns.py --test
- 也可作为后端服务的一部分运行：FastAPI → DDNSManager → 阿里云API

DDNS 原理：
- 定期获取本机公网 IP
- 与上次记录比较，有变化则调阿里云 API 更新 DNS 记录
- TTL 控制缓存时间，确保全球生效
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("standalone.ddns")

# ── 默认配置 ────────────────────────────────────────

# 公网 IP 检测服务列表（按优先级排序）
IP_SERVICES_V4 = [
    "https://api.ip.sb/ip",
    "https://ifconfig.me/ip",
    "https://api.ipify.org",
    "https://icanhazip.com",
    "https://checkip.amazonaws.com",
]

IP_SERVICES_V6 = [
    "https://api64.ip.sb/ip",
]

# 配置文件路径（支持环境变量覆盖）
DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[5] / "standalone-tools" / "ddns"


@dataclass
class DDNSConfig:
    """DDNS 管理器配置"""

    # 阿里云凭证
    access_key_id: str = ""
    access_key_secret: str = ""

    # 域名配置
    domain: str = ""           # 主域名，如 reginyuan.com
    subdomain: str = "wake"     # 子域名，如 wake → wake.reginyuan.com

    # DNS 记录配置
    record_type: str = "A"      # A=IPv4, AAAA=IPv6
    ttl: int = 600              # DNS 缓存时间(秒)，默认10分钟

    # 检测配置
    interval: int = 300         # 检测间隔(秒)，默认5分钟

    # 运行时状态（自动维护，不需要手动设置）
    last_ip: str = ""
    last_updated: str = ""
    created_at: str = ""

    # 守护进程状态
    daemon_running: bool = False
    daemon_started_at: float = 0.0
    daemon_check_count: int = 0
    daemon_update_count: int = 0
    daemon_last_error: str = ""

    # 更新历史（最近 N 条）
    history: list[dict] = field(default_factory=list)
    max_history: int = 50


class DDNSManager:
    """动态域名解析管理器。

    职责：
    1. 管理 DDNS 配置（加载/保存/更新）
    2. 检测公网 IP 变化并调用 DNS API 更新
    3. 提供后台守护模式的异步运行能力
    4. 提供 RESTful API 所需的所有查询接口

    使用方式：
        ```python
        mgr = DDNSManager()
        await mgr.load_config()          # 加载配置文件
        status = mgr.get_status()         # 获取当前状态
        result = await mgr.check_update() # 执行一次检查
        await mgr.start_daemon()          # 启动后台守护
        ```
    """

    def __init__(self, config_dir: str | Path | None = None) -> None:
        self.config = DDNSConfig()
        self._config_dir = Path(config_dir) if config_dir else DEFAULT_CONFIG_DIR
        self._config_file = self._config_dir / "aliddns_config.json"
        self._daemon_task: Optional[asyncio.Task] = None
        self._stop_event = asyncio.Event()

    @property
    def full_domain(self) -> str:
        """完整域名（子域名.主域名）"""
        if not self.config.domain:
            return ""
        if self.config.subdomain == "@" or not self.config.subdomain:
            return self.config.domain
        return f"{self.config.subdomain}.{self.config.domain}"

    # ── 配置管理 ────────────────────────────────────

    def load_config(self) -> dict:
        """从配置文件加载 DDNS 配置。"""
        path = self._config_file
        if not path.exists():
            logger.warning(f"DDNS 配置文件不存在: {path}")
            return {"loaded": False, "path": str(path), "error": "Config file not found"}

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 映射到配置对象
            for key in ("access_key_id", "access_key_secret", "domain", "subdomain",
                        "record_type", "ttl", "interval", "last_ip", "last_updated", "created_at"):
                if key in data and data[key]:
                    setattr(self.config, key, data[key])

            logger.info(
                f"DDNS config loaded: {self.full_domain} ({self.config.record_type}) "
                f"interval={self.config.interval}s"
            )
            return {
                "loaded": True,
                "path": str(path),
                "domain": self.full_domain,
                "record_type": self.config.record_type,
            }
        except Exception as e:
            logger.error(f"Failed to load DDNS config: {e}")
            return {"loaded": False, "path": str(path), "error": str(e)}

    def save_config(self) -> bool:
        """保存当前配置到文件。"""
        try:
            self._config_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "access_key_id": self.config.access_key_id,
                "access_key_secret": self.config.access_key_secret,
                "domain": self.config.domain,
                "subdomain": self.config.subdomain,
                "record_type": self.config.record_type,
                "ttl": self.config.ttl,
                "interval": self.config.interval,
                "last_ip": self.config.last_ip,
                "last_updated": self.config.last_updated,
                "created_at": self.config.created_at,
            }
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            # 保护密钥文件权限
            try:
                os.chmod(self._config_file, 0o600)
            except Exception:
                pass  # Windows 不支持 chmod 权限位

            logger.info(f"DDNS config saved to {self._config_file}")
            return True
        except Exception as e:
            logger.error(f"Failed to save DDNS config: {e}")
            return False

    def update_config(
        self,
        access_key_id: Optional[str] = None,
        access_key_secret: Optional[str] = None,
        domain: Optional[str] = None,
        subdomain: Optional[str] = None,
        record_type: Optional[str] = None,
        ttl: Optional[int] = None,
        interval: Optional[int] = None,
    ) -> dict:
        """更新 DDNS 配置参数。"""
        changed_fields = []
        field_map = {
            "access_key_id": access_key_id,
            "access_key_secret": access_key_secret,
            "domain": domain,
            "subdomain": subdomain,
            "record_type": record_type,
            "ttl": ttl,
            "interval": interval,
        }

        for key, value in field_map.items():
            if value is not None:
                setattr(self.config, key, value)
                changed_fields.append(key)

        success = self.save_config()
        return {
            "success": success,
            "changed_fields": changed_fields,
            "full_domain": self.full_domain,
        }

    # ── 公网 IP 检测 ──────────────────────────────

    async def get_public_ipv4(self) -> Optional[str]:
        """获取公网 IPv4 地址（异步）。"""
        return await asyncio.get_event_loop().run_in_executor(None, self._get_public_ip_v4_sync)

    async def get_public_ipv6(self) -> Optional[str]:
        """获取公网 IPv6 地址（异步）。"""
        return await asyncio.get_event_loop().run_in_executor(None, self._get_public_ip_v6_sync)

    def _get_public_ip_v4_sync(self) -> Optional[str]:
        """同步获取公网 IPv4。"""
        import urllib.request
        for url in IP_SERVICES_V4:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "AliDDNS-Updater/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    ip = resp.read().decode("utf-8").strip()
                    if "." in ip:
                        logger.debug(f"Got public IPv4 from {url}: {ip}")
                        return ip
            except Exception as e:
                logger.debug(f"{url} failed: {e}")
                continue
        logger.error("All IPv4 detection services failed")
        return None

    def _get_public_ip_v6_sync(self) -> Optional[str]:
        """同步获取公网 IPv6。"""
        import urllib.request
        services = IP_SERVICES_V6 + IP_SERVICES_V4
        for url in services:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "AliDDNS-Updater/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    ip = resp.read().decode("utf-8").strip()
                    if ":" in ip:
                        logger.debug(f"Got public IPv6 from {url}: {ip}")
                        return ip
            except Exception as e:
                logger.debug(f"{url} failed: {e}")
                continue
        logger.error("All IPv6 detection services failed")
        return None

    # ── 阿里云 DNS API ────────────────────────────

    def _call_aliyun_api(self, action: str, params: dict) -> dict:
        """
        调用阿里云 DNS API（纯标准库实现）。
        使用 RPC 风格签名：HMAC-SHA256。
        """
        from urllib.parse import quote_plus
        import hashlib
        import hmac
        import uuid

        common_params = {
            "Format": "JSON",
            "Version": "2015-01-09",
            "AccessKeyId": self.config.access_key_id,
            "SignatureMethod": "HMAC-SHA256",
            "Timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "SignatureVersion": "1.0",
            "SignatureNonce": str(uuid.uuid4()),
            "Action": action,
        }

        all_params = {**common_params, **params}
        sorted_params = sorted(all_params.items())
        query_string = "&".join([f"{quote_plus(k)}={quote_plus(str(v))}" for k, v in sorted_params])

        string_to_sign = f"GET&{quote_plus('/')}&{quote_plus(query_string)}"
        secret = f"{self.config.access_key_secret}&"
        signature = hmac.new(
            secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature_b64 = __import__("base64").b64encode(signature).decode("utf-8")

        final_url = (
            f"https://alidns.aliyuncs.com/?"
            f"{query_string}&Signature={quote_plus(signature_b64)}"
        )

        import urllib.request
        req = urllib.request.Request(final_url, headers={"User-Agent": "AliDDNS-Updater/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body

    def _describe_domain_record(self) -> Optional[dict]:
        """查询指定子域名的 DNS 记录。"""
        try:
            result = self._call_aliyun_api("DescribeDomainRecords", {
                "DomainName": self.config.domain,
                "RRKeyWord": self.config.subdomain,
                "Type": self.config.record_type,
                "PageSize": 50,
            })
            records = result.get("DomainRecords", {}).get("Record", [])
            for record in records:
                if record.get("RR") == self.config.subdomain:
                    return record
            return None
        except Exception as e:
            logger.error(f"DescribeDomainRecords failed: {e}")
            return None

    def _add_or_update_record(self, new_ip: str) -> Tuple[bool, str]:
        """新增或更新 DNS 记录。返回 (是否变更, 消息)。"""
        existing = self._describe_domain_record()
        full_name = self.full_domain

        if existing:
            current_value = existing.get("Value", "")
            record_id = existing.get("RecordId")

            if current_value == new_ip:
                return False, f"IP 未变: {new_ip}"

            # 更新现有记录
            self._call_aliyun_api("UpdateDomainRecord", {
                "RecordId": record_id,
                "RR": self.config.subdomain,
                "Type": self.config.record_type,
                "Value": new_ip,
                "TTL": str(self.config.ttl),
            })
            return True, f"已更新: {current_value} → {new_ip}"
        else:
            # 新增记录
            self._call_aliyun_api("AddDomainRecord", {
                "DomainName": self.config.domain,
                "RR": self.config.subdomain,
                "Type": self.config.record_type,
                "Value": new_ip,
                "TTL": str(self.config.ttl),
            })
            return True, f"新增记录: {new_ip}"

    # ── 核心逻辑 ────────────────────────────────────

    async def check_update(self, force: bool = False) -> dict:
        """
        执行一次 IP 检测和 DDNS 更新。

        Args:
            force: 强制更新（即使 IP 没变也调用 API）

        Returns:
            结果字典包含 success, message, ip, changed, resolved_ip 等
        """
        # 验证配置完整性
        missing = [k for k in ("access_key_id", "access_key_secret", "domain", "subdomain")
                   if not getattr(self.config, k)]
        if missing:
            return {"success": False, "message": f"缺少必填配置: {missing}", "changed": False}

        # 获取公网 IP
        if self.config.record_type == "AAAA":
            new_ip = await self.get_public_ipv6()
        else:
            new_ip = await self.get_public_ipv4()

        if not new_ip:
            return {"success": False, "message": "无法获取公网 IP", "changed": False}

        # 比较 IP 是否变化
        old_ip = self.config.last_ip
        if not force and new_ip == old_ip:
            logger.info(f"IP 未变 ({new_ip})，跳过更新")
            return {
                "success": True,
                "message": f"IP 未变 ({new_ip})",
                "changed": False,
                "ip": new_ip,
                "old_ip": old_ip,
            }

        # 调用阿里云 API
        loop = asyncio.get_event_loop()
        try:
            changed, message = await loop.run_in_executor(
                None, self._add_or_update_record, new_ip,
            )
        except Exception as e:
            error_msg = f"DNS API 调用失败: {e}"
            logger.error(error_msg)
            self._add_history("error", error_msg, new_ip)
            return {"success": False, "message": error_msg, "ip": new_ip, "changed": False}

        # 更新本地状态
        now_iso = datetime.now().isoformat()
        self.config.last_ip = new_ip
        self.config.last_updated = now_iso
        self.save_config()

        # 记录历史
        status = "updated" if changed else "unchanged"
        self._add_history(status, message, new_ip)

        # 尝试 DNS 解析验证
        resolved_ip = self._resolve_dns()

        result = {
            "success": True,
            "message": message,
            "changed": changed,
            "ip": new_ip,
            "old_ip": old_ip,
            "resolved_ip": resolved_ip,
            "dns_match": resolved_ip == new_ip if resolved_ip else None,
            "updated_at": now_iso,
        }

        logger.info(
            f"DDNS {'已更新' if changed else '无需更新'}: "
            f"{self.full_domain} → {new_ip} (resolved: {resolved_ip})"
        )
        return result

    def _resolve_dns(self) -> Optional[str]:
        """尝试 DNS 解析验证。"""
        try:
            socket.setdefaulttimeout(5)
            return socket.gethostbyname(self.full_domain)
        except Exception:
            return None

    def _add_history(self, status: str, message: str, ip: str) -> None:
        """添加一条更新记录到历史。"""
        entry = {
            "time": datetime.now().isoformat(),
            "status": status,  # updated, unchanged, error
            "message": message,
            "ip": ip,
            "domain": self.full_domain,
        }
        self.config.history.insert(0, entry)
        # 保持最大条数限制
        if len(self.config.history) > self.config.max_history:
            self.config.history = self.config.history[:self.config.max_history]

    # ── 状态查询 ────────────────────────────────────

    def get_status(self) -> dict:
        """获取 DDNS 当前完整状态（用于 API 响应）。"""
        resolved_ip = None
        dns_match = None

        if self.full_domain and self.config.last_ip:
            resolved_ip = self._resolve_dns()
            dns_match = resolved_ip == self.config.last_ip if resolved_ip else None

        return {
            # 基础信息
            "configured": bool(self.config.domain and self.config.access_key_id),
            "full_domain": self.full_domain or "(未配置)",
            "domain": self.config.domain,
            "subdomain": self.config.subdomain,
            "record_type": self.config.record_type,

            # IP 信息
            "current_ip": self.config.last_ip or "(尚未检测)",
            "resolved_ip": resolved_ip,
            "dns_match": dns_match,

            # 时间信息
            "last_updated": self.config.last_updated or "(尚未更新)",
            "created_at": self.config.created_at or "-",

            # 配置参数
            "ttl": self.config.ttl,
            "interval": self.config.interval,

            # 守护进程状态
            "daemon_running": self.config.daemon_running,
            "daemon_started_at": self.config.daemon_started_at,
            "daemon_check_count": self.config.daemon_check_count,
            "daemon_update_count": self.config.daemon_update_count,
            "daemon_last_error": self.config.daemon_last_error,

            # 统计
            "history_count": len(self.config.history),

            # 配置文件路径
            "config_path": str(self._config_file),
            "config_exists": self._config_file.exists(),
        }

    def get_history(self, limit: int = 20) -> list[dict]:
        """获取最近 N 条更新历史。"""
        return self.config.history[:limit]

    # ── 守护进程 ────────────────────────────────────

    async def start_daemon(self) -> dict:
        """启动后台守护模式（异步循环检测 IP）。"""
        if self.config.daemon_running:
            return {"success": False, "message": "守护进程已在运行中"}

        self._stop_event.clear()
        self.config.daemon_running = True
        self.config.daemon_started_at = time.time()
        self.config.daemon_check_count = 0
        self.config.daemon_update_count = 0
        self.config.daemon_last_error = ""

        self._daemon_task = asyncio.create_task(self._daemon_loop())
        logger.info(
            f"DDNS daemon started: {self.full_domain}, "
            f"interval={self.config.interval}s, pid={os.getpid()}"
        )
        return {
            "success": True,
            "message": f"守护进程已启动 (interval={self.config.interval}s)",
            "started_at": self.config.daemon_started_at,
        }

    async def stop_daemon(self) -> dict:
        """停止后台守护模式。"""
        if not self.config.daemon_running:
            return {"success": False, "message": "守护进程未在运行"}

        self._stop_event.set()
        if self._daemon_task:
            self._daemon_task.cancel()
            try:
                await self._daemon_task
            except (asyncio.CancelledError, Exception):
                pass
            self._daemon_task = None

        self.config.daemon_running = False
        logger.info(f"DDNS daemon stopped. Total checks: {self.config.daemon_check_count}")
        return {
            "success": True,
            "message": "守护进程已停止",
            "total_checks": self.config.daemon_check_count,
            "total_updates": self.config.daemon_update_count,
        }

    async def _daemon_loop(self) -> None:
        """后台守护主循环。"""
        logger.info(f"DDNS daemon loop started — checking every {self.config.interval}s")

        # 启动时立即检测一次
        try:
            result = await self.check_update(force=True)
            self.config.daemon_check_count += 1
            if result.get("changed"):
                self.config.daemon_update_count += 1
        except Exception as e:
            logger.error(f"Initial DDNS check failed: {e}")
            self.config.daemon_last_error = str(e)

        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self.config.interval)
                break  # 收到停止信号
            except asyncio.TimeoutError:
                pass  # 超时，继续执行检测

            try:
                result = await self.check_update()
                self.config.daemon_check_count += 1
                if result.get("changed"):
                    self.config.daemon_update_count += 1
            except Exception as e:
                logger.error(f"Daemon check error: {e}")
                self.config.daemon_last_error = str(e)
                self.config.daemon_check_count += 1

        self.config.daemon_running = False
        logger.info("DDNS daemon loop exited")

    async def test_connection(self) -> dict:
        """测试阿里云 API 连通性和配置有效性。"""
        # Step 1: 测试 IP 检测
        ip = await self.get_public_ipv4()
        if not ip:
            return {
                "success": False,
                "step": "ip_detection",
                "message": "无法获取公网 IP（网络问题？）",
            }

        # Step 2: 测试 API 凭证（查询域名记录列表）
        try:
            loop = asyncio.get_event_loop()
            records_result = await loop.run_in_executor(
                None, self._call_aliyun_api, "DescribeDomainRecords", {
                    "DomainName": self.config.domain,
                    "PageSize": 1,  # 只查1条，最小化请求
                },
            )

            total = records_result.get("TotalCount", 0)
            return {
                "success": True,
                "step": "all_ok",
                "public_ip": ip,
                "api_connected": True,
                "domain_records_total": total,
                "message": (
                    f"连接正常 | 公网IP: {ip} | "
                    f"域名 {self.config.domain} 共 {total} 条DNS记录"
                ),
            }
        except Exception as e:
            return {
                "success": False,
                "step": "api_auth",
                "public_ip": ip,
                "api_connected": False,
                "message": f"阿里云API认证失败: {e}",
            }


# ── 全局单例 ────────────────────────────────────────

_ddns_manager: Optional[DDNSManager] = None


def init_ddns_manager(config_dir: str | Path | None = None) -> DDNSManager:
    """初始化 DDNS 管理器单例并加载配置。"""
    global _ddns_manager
    if _ddns_manager is None:
        _ddns_manager = DDNSManager(config_dir=config_dir)
        _ddns_manager.load_config()
        logger.info("DDNSManager singleton initialized")
    return _ddns_manager


def get_ddns_manager() -> Optional[DDNSManager]:
    """获取 DDNS 管理器单例（未初始化则返回 None）。"""
    return _ddns_manager
