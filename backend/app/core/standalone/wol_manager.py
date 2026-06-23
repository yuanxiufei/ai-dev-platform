"""
WakeOnLANManager — 远程唤醒管理

核心能力：
1. 自动检测本机 MAC 地址和广播地址
2. 构造并发送 Wake-on-LAN 魔术包（102字节标准格式）
3. 通过 API 暴露 WOL 配置，方便另一台电脑执行唤醒

WOL 原理：
- 魔术包 = 6 字节 0xFF + MAC 地址重复 16 次
- 通过 UDP 发送到子网广播地址的 7 或 9 端口
- 目标网卡在收到魔术包后触发开机/唤醒信号

前置条件（目标机器）：
- BIOS/UEFI 中启用 Wake-on-LAN（通常在 Power Management）
- 操作系统网卡属性中启用「允许此设备唤醒计算机」
- 某些主板需在 BIOS 中关闭 ErP/EuP 节能
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import re
import socket
import struct
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("standalone.wol")


# ── 魔术包 ────────────────────────────────────────


def _mac_to_bytes(mac_str: str) -> bytes:
    """将 MAC 地址字符串转为 6 字节二进制。

    支持格式：AA:BB:CC:DD:EE:FF, AA-BB-CC-DD-EE-FF, AABBCCDDEEFF
    """
    mac_str = mac_str.replace(":", "").replace("-", "").replace(".", "").strip().upper()
    if len(mac_str) != 12:
        raise ValueError(f"Invalid MAC address length: {len(mac_str)} chars (need 12)")
    return bytes.fromhex(mac_str)


def build_magic_packet(mac_address: str) -> bytes:
    """构建 Wake-on-LAN 魔术包。

    Args:
        mac_address: 目标网卡 MAC 地址

    Returns:
        102 字节魔术包（6*0xFF + 16*MAC）
    """
    mac_bytes = _mac_to_bytes(mac_address)
    return b"\xff" * 6 + mac_bytes * 16  # = 102 bytes


def send_magic_packet(
    mac_address: str,
    broadcast: str = "255.255.255.255",
    port: int = 9,
) -> bool:
    """发送 WOL 魔术包。

    Args:
        mac_address: 目标 MAC 地址
        broadcast: 广播地址（默认 255.255.255.255）
        port: UDP 端口（默认 9，也可用 7）

    Returns:
        True 如果发送成功
    """
    packet = build_magic_packet(mac_address)

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(2)
        sock.sendto(packet, (broadcast, port))
        sock.close()

        logger.info(
            "WOL magic packet sent — MAC=%s broadcast=%s:%d packet_size=%d",
            mac_address, broadcast, port, len(packet),
        )
        return True
    except Exception as e:
        logger.error("Failed to send WOL magic packet: %s", e)
        return False


# ── 网络接口检测 ──────────────────────────────────


def _run_command(cmd: list[str]) -> str:
    """运行命令并返回 stdout"""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.stdout
    except Exception:
        return ""


def _parse_mac_from_string(text: str) -> list[str]:
    """从文本中提取所有 MAC 地址"""
    # MAC 地址正则（6组十六进制）
    pattern = r"([0-9A-Fa-f]{2}[-:.]?){5}[0-9A-Fa-f]{2}"
    matches = re.findall(pattern, text)
    # 规范化格式
    seen = set()
    result = []
    for raw in matches:
        normalized = raw.replace("-", ":").replace(".", ":").upper()
        # 跳过全 0 或广播地址
        if normalized in ("00:00:00:00:00:00", "FF:FF:FF:FF:FF:FF"):
            continue
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def detect_mac_addresses() -> list[dict]:
    """检测本机所有网络接口的 MAC 地址和广播地址。

    Returns:
        列表，每项包含 interface_name, mac, ip, broadcast
    """
    system = platform.system()
    interfaces: list[dict] = []

    if system == "Windows":
        # 使用 ipconfig /all 获取详细信息
        output = _run_command(["ipconfig", "/all"])
        # 解析 ipconfig 输出
        current_iface: dict = {}
        for line in output.split("\n"):
            line = line.strip()
            # 接口名
            if line and not line.startswith(" ") and ":" in line and "Windows" not in line:
                if current_iface and "mac" in current_iface:
                    interfaces.append(current_iface)
                iface_name = line.rstrip(":")
                current_iface = {"interface_name": iface_name, "mac": "", "ip": "", "broadcast": ""}
            # 物理地址
            if "物理地址" in line or "Physical Address" in line:
                parts = line.rsplit(":", 1) if ":" in line else line.rsplit(":", 1)
                raw_mac = parts[-1].strip().replace("-", ":")
                current_iface["mac"] = raw_mac
            # IPv4
            if "IPv4" in line or "IP Address" in line:
                parts = line.rsplit(":", 1)
                current_iface["ip"] = parts[-1].strip().rstrip("(首选)").rstrip("(Preferred)").strip()

        if current_iface and "mac" in current_iface:
            interfaces.append(current_iface)

        # 如果 ipconfig 解析失败，用 getmac 作为回退
        if not interfaces:
            output = _run_command(["getmac", "/v", "/fo", "csv"])
            for line in output.strip().split("\n")[1:]:
                parts = [p.strip('"') for p in line.split(",")]
                if len(parts) >= 3:
                    interfaces.append({
                        "interface_name": parts[0] or parts[1],
                        "mac": parts[2].replace("-", ":"),
                        "ip": "",
                        "broadcast": "",
                    })

    elif system == "Linux":
        # 使用 ip link 获取 MAC + ip addr 获取 IP
        link_output = _run_command(["ip", "-o", "link", "show"])
        addr_output = _run_command(["ip", "-o", "-4", "addr", "show"])

        # 解析接口
        iface_macs: dict[str, str] = {}
        for line in link_output.split("\n"):
            if not line.strip():
                continue
            parts = line.split(":")
            if len(parts) >= 2:
                iface_name = parts[1].strip()
                macs = _parse_mac_from_string(line)
                if macs:
                    iface_macs[iface_name] = macs[0]

        # 解析 IP/广播
        iface_ips: dict[str, dict] = {}
        for line in addr_output.split("\n"):
            match = re.search(r"(\w+)\s+inet\s+(\S+)\s+brd\s+(\S+)", line)
            if match:
                iface_ips[match.group(1)] = {
                    "ip": match.group(2).split("/")[0],
                    "broadcast": match.group(3),
                }

        for name, mac in iface_macs.items():
            if name == "lo":  # 跳过回环
                continue
            info = iface_ips.get(name, {})
            interfaces.append({
                "interface_name": name,
                "mac": mac,
                "ip": info.get("ip", ""),
                "broadcast": info.get("broadcast", ""),
            })

        # 回退：读 /sys/class/net
        if not interfaces:
            net_dir = "/sys/class/net"
            if os.path.isdir(net_dir):
                for iface in os.listdir(net_dir):
                    if iface == "lo":
                        continue
                    addr_file = os.path.join(net_dir, iface, "address")
                    if os.path.isfile(addr_file):
                        with open(addr_file, "r") as f:
                            mac = f.read().strip()
                        if mac and mac != "00:00:00:00:00:00":
                            interfaces.append({
                                "interface_name": iface,
                                "mac": mac,
                                "ip": "",
                                "broadcast": "",
                            })

    elif system == "Darwin":  # macOS
        output = _run_command(["ifconfig"])
        # 解析 ifconfig 输出
        current_iface: dict = {}
        for line in output.split("\n"):
            if not line.startswith("\t") and not line.startswith(" ") and line.strip():
                if current_iface and "mac" in current_iface and current_iface["interface_name"] != "lo0":
                    interfaces.append(current_iface)
                current_iface = {
                    "interface_name": line.split(":")[0],
                    "mac": "", "ip": "", "broadcast": "",
                }
            if "ether" in line and current_iface:
                macs = _parse_mac_from_string(line)
                if macs:
                    current_iface["mac"] = macs[0]
            if "inet " in line and "inet6" not in line and current_iface:
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == "inet" and i + 1 < len(parts):
                        current_iface["ip"] = parts[i + 1]
                    if p == "broadcast" and i + 1 < len(parts):
                        current_iface["broadcast"] = parts[i + 1]

        if current_iface and "mac" in current_iface and current_iface["interface_name"] != "lo0":
            interfaces.append(current_iface)

    # 过滤掉没有 MAC 的接口
    return [i for i in interfaces if i["mac"] and i["mac"] != "00:00:00:00:00:00"]


def derive_broadcast(ip_address: str) -> str:
    """根据 IP 推导子网广播地址。

    仅支持 /24 子网（最常见家庭/办公网络）。
    """
    if not ip_address:
        return "255.255.255.255"
    try:
        parts = ip_address.split(".")
        if len(parts) == 4:
            # 假设 /24 子网
            parts[3] = "255"
            return ".".join(parts)
    except Exception:
        pass
    return "255.255.255.255"


# ── WOL 配置与管理 ───────────────────────────────


@dataclass
class WOLConfig:
    """Wake-on-LAN 配置"""

    # 目标 MAC 地址（本机的网卡 MAC）
    target_mac: str = ""

    # 广播地址（默认 255.255.255.255 全广播，或子网广播如 192.168.1.255）
    broadcast_address: str = "255.255.255.255"

    # UDP 端口（9 是 WOL 标准端口）
    port: int = 9

    # 自动检测到的网络接口信息
    interfaces: list[dict] = field(default_factory=list)

    # 最后发送时间
    last_sent_at: float = 0.0

    # 最后发送是否成功
    last_sent_success: bool = False


class WakeOnLANManager:
    """Wake-on-LAN 远程唤醒管理器。

    职责：
    1. 自动检测本机所有网络接口的 MAC/IP/广播地址
    2. 构造并发送 WOL 魔术包
    3. 提供 WOL 配置查询 API

    使用方式：
        ```python
        wol_mgr = WakeOnLANManager()
        await wol_mgr.detect()

        # 发送魔术包（唤醒本机）
        await wol_mgr.send()

        # 发送魔术包（唤醒指定 MAC）
        await wol_mgr.send_to("AA:BB:CC:DD:EE:FF", "192.168.1.255")
        ```
    """

    def __init__(self, config: WOLConfig | None = None) -> None:
        self.config = config or WOLConfig()

    async def detect(self) -> dict:
        """自动检测本机网络接口并填充配置。

        在启动时调用，自动识别本机 MAC 和广播地址。
        """
        interfaces = detect_mac_addresses()
        self.config.interfaces = interfaces

        # 如果没有手动配置过 target_mac，自动选择第一个非回环接口
        if not self.config.target_mac and interfaces:
            # 优先选择有 IP 的接口
            for iface in interfaces:
                if iface["ip"]:
                    self.config.target_mac = iface["mac"]
                    if not self.config.broadcast_address or self.config.broadcast_address == "255.255.255.255":
                        derived = derive_broadcast(iface["ip"])
                        if derived != "255.255.255.255":
                            self.config.broadcast_address = derived
                    logger.info(
                        "Auto-selected interface: %s (MAC=%s, IP=%s, broadcast=%s)",
                        iface["interface_name"], iface["mac"], iface["ip"],
                        self.config.broadcast_address,
                    )
                    break
            # 回退：用第一个有 MAC 的接口
            if not self.config.target_mac and interfaces:
                self.config.target_mac = interfaces[0]["mac"]
                logger.info("Fallback to first interface: %s (MAC=%s)",
                            interfaces[0]["interface_name"], interfaces[0]["mac"])

        logger.info(
            "WOL Manager detected %d interfaces, target MAC=%s, broadcast=%s:%d",
            len(interfaces), self.config.target_mac,
            self.config.broadcast_address, self.config.port,
        )
        return self.get_info()

    def get_info(self) -> dict:
        """获取 WOL 完整配置信息（用于 API 响应）。"""
        return {
            "target_mac": self.config.target_mac,
            "broadcast_address": self.config.broadcast_address,
            "port": self.config.port,
            "interfaces": self.config.interfaces,
            "last_sent_at": self.config.last_sent_at,
            "last_sent_success": self.config.last_sent_success,
            "platform": platform.system(),
        }

    async def send(self) -> dict:
        """发送 WOL 魔术包到配置的目标地址（本机）。

        Returns:
            {"success": bool, "message": str, "target_mac": str, "broadcast": str}
        """
        if not self.config.target_mac:
            return {"success": False, "message": "No target MAC configured. Run detect() first.", "target_mac": "", "broadcast": ""}

        # 在线程池中运行（send_magic_packet 是同步 socket 操作）
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None,
            send_magic_packet,
            self.config.target_mac,
            self.config.broadcast_address,
            self.config.port,
        )

        self.config.last_sent_at = time.time()
        self.config.last_sent_success = success

        if success:
            return {
                "success": True,
                "message": f"Magic packet sent to {self.config.target_mac} via {self.config.broadcast_address}:{self.config.port}",
                "target_mac": self.config.target_mac,
                "broadcast": self.config.broadcast_address,
                "port": self.config.port,
            }
        else:
            return {
                "success": False,
                "message": "Failed to send magic packet. Check network permissions.",
                "target_mac": self.config.target_mac,
                "broadcast": self.config.broadcast_address,
            }

    async def send_to(self, mac_address: str, broadcast: str = "255.255.255.255", port: int = 9) -> dict:
        """向指定 MAC 地址发送 WOL 魔术包（用于唤醒另一台机器）。

        Args:
            mac_address: 目标机器的 MAC 地址
            broadcast: 广播地址
            port: UDP 端口

        Returns:
            {"success": bool, "message": str}
        """
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None, send_magic_packet, mac_address, broadcast, port,
        )

        self.config.last_sent_at = time.time()
        self.config.last_sent_success = success

        return {
            "success": success,
            "message": f"Magic packet {'sent' if success else 'failed'} to {mac_address} via {broadcast}:{port}",
            "target_mac": mac_address,
            "broadcast": broadcast,
            "port": port,
        }

    async def configure(self, target_mac: str = "", broadcast_address: str = "", port: int = 0) -> dict:
        """手动配置 WOL 参数。

        Args:
            target_mac: 目标 MAC 地址（空则不修改）
            broadcast_address: 广播地址（空则不修改）
            port: UDP 端口（0 则不修改）

        Returns:
            更新后的配置
        """
        if target_mac:
            # 验证 MAC 格式
            _mac_to_bytes(target_mac)
            self.config.target_mac = target_mac
            logger.info("WOL target MAC updated: %s", target_mac)

        if broadcast_address:
            self.config.broadcast_address = broadcast_address
            logger.info("WOL broadcast address updated: %s", broadcast_address)

        if port > 0 and port < 65536:
            self.config.port = port
            logger.info("WOL port updated: %d", port)

        return self.get_info()


# ── 全局单例 ────────────────────────────────────────

_wol_manager: Optional[WakeOnLANManager] = None


async def init_wol_manager(config: WOLConfig | None = None) -> WakeOnLANManager:
    """初始化 WOL 管理器单例并自动检测网络接口。"""
    global _wol_manager
    if _wol_manager is None:
        _wol_manager = WakeOnLANManager(config)
        await _wol_manager.detect()
        logger.info("WakeOnLANManager singleton initialized")
    return _wol_manager


def get_wol_manager() -> Optional[WakeOnLANManager]:
    return _wol_manager
