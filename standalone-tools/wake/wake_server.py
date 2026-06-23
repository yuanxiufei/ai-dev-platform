#!/usr/bin/env python3
"""
Wake Server — 远程唤醒休眠的 AI Fullstack 服务器

通过发送 Wake-on-LAN (WOL) 魔术包唤醒目标机器。

依赖：仅使用 Python 标准库（socket），无需安装第三方包。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
使用方法：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 基本唤醒（使用默认广播 255.255.255.255）：

    python wake_server.py --mac AA:BB:CC:DD:EE:FF

2. 指定子网广播地址（推荐，更精准）：

    python wake_server.py --mac AA:BB:CC:DD:EE:FF --broadcast 192.168.1.255

3. 指定端口（标准 WOL 端口 = 9）：

    python wake_server.py --mac AA:BB:CC:DD:EE:FF --port 9

5. 跨互联网唤醒（通过 DDNS 域名 + 端口转发）：

    python wake_server.py --mac AA:BB:CC:DD:EE:FF --broadcast wake.yourdomain.com --port 9

6. 连续发送多次（提高可靠性）：

    python wake_server.py --mac AA:BB:CC:DD:EE:FF --count 3

7. 指定网卡发送（需要 root / Administrator）：

    python wake_server.py --mac AA:BB:CC:DD:EE:FF --interface eth0

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
前置条件（需要被唤醒的服务器上配置）：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BIOS:
  - 进入 BIOS → Power Management → 启用 Wake-on-LAN
  - 关闭 ErP / EuP 节能模式（如果存在）

Windows 网卡:
  - 设备管理器 → 网卡 → 属性 → 电源管理
  - ✓ 允许此设备唤醒计算机
  - ✓ 只允许魔术包唤醒计算机
  - 属性 → 高级 → Wake on Magic Packet → Enabled

Linux 网卡:
  - sudo ethtool -s eth0 wol g          # 启用 WOL
  - sudo ethtool eth0 | grep Wake-on    # 验证: Wake-on: g
  - 写入 systemd service 持久化

macOS:
  - 系统偏好设置 → 节能 → ✓ 唤醒以供网络访问
  - 或: sudo pmset -a womp 1

网络:
  - 两台机器必须在同一子网（同一路由器下）
  - 推荐使用有线网卡（Wi-Fi WOL 不稳定）

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

import argparse
import socket
import struct
import sys
import time


def mac_to_bytes(mac_str: str) -> bytes:
    """将 MAC 地址字符串转为 6 字节。

    支持格式：AA:BB:CC:DD:EE:FF, AA-BB-CC-DD-EE-FF, AABBCCDDEEFF
    """
    mac_str = mac_str.replace(":", "").replace("-", "").replace(".", "").strip().upper()
    if len(mac_str) != 12:
        raise ValueError(
            f"MAC 地址长度无效: {len(mac_str)} 字符 (需要 12)\n"
            f"  接收: '{mac_str}'\n"
            f"  正确格式: AA:BB:CC:DD:EE:FF"
        )

    try:
        return bytes.fromhex(mac_str)
    except ValueError:
        raise ValueError(f"MAC 地址包含非十六进制字符: '{mac_str}'")


def build_magic_packet(mac_address: str) -> bytes:
    """构建 WOL 魔术包。

    标准格式: 6 × 0xFF + 16 × MAC = 102 字节
    """
    mac_bytes = mac_to_bytes(mac_address)
    return b"\xff" * 6 + mac_bytes * 16


def resolve_target(broadcast: str, port: int) -> str:
    """解析广播目标（支持 IP、域名）。
    
    如果是域名，先解析为 IP 地址再返回。
    """
    # 检查是否为纯 IP
    parts = broadcast.replace(".", "").replace(":", "")
    if parts.replace("-", "").isdigit():
        return broadcast
    
    # 域名解析
    try:
        print(f"  [DNS] 正在解析域名: {broadcast} ...")
        ip = socket.gethostbyname(broadcast)
        print(f"  [DNS] 解析成功: {broadcast} → {ip}")
        return ip
    except socket.gaierror as e:
        raise ValueError(f"无法解析域名 '{broadcast}': {e}")


def send_magic_packet(
    mac_address: str,
    broadcast: str = "255.255.255.255",
    port: int = 9,
    interface: str | None = None,
) -> bool:
    """发送 WOL 魔术包。

    Args:
        mac_address: 目标网卡 MAC 地址
        broadcast: 广播地址（默认 255.255.255.255，也支持域名）
        port: UDP 端口（默认 9）
        interface: 指定网卡名称（可选）

    Returns:
        True 如果发送成功
    """
    packet = build_magic_packet(mac_address)

    # 解析目标地址（支持域名）
    target_ip = resolve_target(broadcast, port)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    # 如果指定了网卡，绑定到该网卡
    if interface:
        try:
            # SO_BINDTODEVICE (25) — Linux only
            sock.setsockopt(socket.SOL_SOCKET, 25, interface.encode())
        except OSError:
            print(f"[WARN] 无法绑定到网卡 '{interface}'（可能权限不足或系统不支持）")

    try:
        sock.sendto(packet, (target_ip, port))
        print()
        print("  ✓ 魔术包已发送！")
        print(f"    目标 MAC : {mac_address}")
        print(f"    目标地址 : {target_ip}:{port}" + (f" ({broadcast})" if target_ip != broadcast else ""))
        print(f"    包大小   : {len(packet)} 字节")
        print()
        print("  如果目标机器已正确配置 Wake-on-LAN，")
        print("  它将在 10-60 秒内启动。")
        return True
    except Exception as e:
        print(f"\n  ✗ 发送失败: {e}", file=sys.stderr)
        return False
    finally:
        sock.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="远程唤醒 AI Fullstack 服务器 (Wake-on-LAN)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 局域网唤醒
  python wake_server.py --mac AA:BB:CC:DD:EE:FF
  python wake_server.py --mac AA:BB:CC:DD:EE:FF --broadcast 192.168.1.255

  # 跨互联网唤醒（需要 DDNS + 端口转发）
  python wake_server.py --mac AA:BB:CC:DD:EE:FF --broadcast wake.yourdomain.com --port 9
  python wake_server.py --mac AA:BB:CC:DD:EE:FF --port 7 --count 3
        """,
    )

    parser.add_argument(
        "--mac", "-m",
        required=True,
        help="目标机器的 MAC 地址 (格式: AA:BB:CC:DD:EE:FF)",
    )
    parser.add_argument(
        "--broadcast", "-b",
        default="255.255.255.255",
        help="广播地址 (默认: 255.255.255.255，也可用子网广播如 192.168.1.255)",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=9,
        help="WOL 端口 (默认: 9，也可用 7)",
    )
    parser.add_argument(
        "--interface", "-i",
        default=None,
        help="指定发送网卡名称 (如 eth0, eno1)",
    )
    parser.add_argument(
        "--count", "-c",
        type=int,
        default=1,
        help="发送次数 (默认: 1，增加次数提高可靠性)",
    )

    args = parser.parse_args()

    print()
    print("=" * 55)
    print("  AI Fullstack Platform — Wake-on-LAN 远程唤醒")
    print("=" * 55)
    print(f"  目标 MAC  : {args.mac}")
    print(f"  广播地址  : {args.broadcast}:{args.port}")
    print(f"  发送次数  : {args.count}")
    if args.interface:
        print(f"  绑定网卡  : {args.interface}")
    print()

    # 验证 MAC 地址
    try:
        mac_to_bytes(args.mac)
    except ValueError as e:
        print(f"  ✗ MAC 地址错误: {e}", file=sys.stderr)
        sys.exit(1)

    success_count = 0
    for i in range(args.count):
        if args.count > 1:
            print(f"  [第 {i + 1}/{args.count} 次发送]")
        ok = send_magic_packet(
            mac_address=args.mac,
            broadcast=args.broadcast,
            port=args.port,
            interface=args.interface,
        )
        if ok:
            success_count += 1
        if args.count > 1 and i < args.count - 1:
            time.sleep(1)

    if success_count > 0:
        print(f"\n  完成: {success_count}/{args.count} 次发送成功")
    else:
        print(f"\n  失败: 所有 {args.count} 次发送均失败", file=sys.stderr)
        print("  请检查:\n"
              "    1. MAC 地址是否正确\n"
              "    2. 两台机器是否在同一子网\n"
              "    3. 目标机器是否已启用 Wake-on-LAN (BIOS + OS)\n"
              "    4. 防火墙是否阻止了 UDP 广播", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
