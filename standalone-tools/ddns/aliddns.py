#!/usr/bin/env python3
"""
阿里云 DDNS 自动更新脚本 — 免费动态域名解析

功能：
- 自动检测公网 IP 变化
- 通过阿里云 DNS API 更新 A 记录（或 AAAA 记录）
- 支持 Windows 开机自启 + 后台运行
- 完全免费，使用你自己的阿里云域名

使用方式：
  # 首次运行（交互式配置）
  python aliddns.py --setup
  
  # 直接运行（读取配置文件）
  python aliddns.py
  
  # 指定子域名和记录类型
  python aliddns.py --subdomain wake --type A
  
依赖：
  pip install requests aliyun-python-sdk-alidns20150109
  （如果装不了 SDK，脚本会自动用纯 requests 方式调用 API）

作者：AI Fullstack Platform — Standalone WOL 套件
"""

import json
import os
import sys
import time
import logging
import socket
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional, Tuple

# ── 日志配置 ────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ali-ddns")

# ── 配置路径 ────────────────────────────────────────
CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / "aliddns_config.json"
LOG_FILE = CONFIG_DIR / "aliddns.log"

# 公网 IP 检测服务列表（按优先级排序）
IP_SERVICES = [
    "https://api.ip.sb/ip",           # 最快
    "https://ifconfig.me/ip",
    "https://api.ipify.org",
    "https://icanhazip.com",
    "https://checkip.amazonaws.com",   # AWS 备选
]


def get_config_path() -> Path:
    """获取配置文件路径（支持自定义位置）"""
    env_path = os.environ.get("ALIDDNS_CONFIG")
    if env_path:
        return Path(env_path)
    return CONFIG_FILE


def load_config() -> dict:
    """加载配置文件"""
    path = get_config_path()
    if not path.exists():
        log.error(f"配置文件不存在: {path}")
        log.info("请先运行: python aliddns.py --setup")
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 必填字段校验
    required = ["access_key_id", "access_key_secret", "domain", "subdomain"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        log.error(f"配置缺少必填字段: {missing}")
        sys.exit(1)

    # 默认值填充
    config.setdefault("record_type", "A")
    config.setdefault("interval", 300)       # 每5分钟检测一次
    config.setdefault("ttl", 600)            # TTL 10分钟
    config.setdefault("ip_service_index", 0) # 使用的IP服务索引
    config.setdefault("last_ip", "")
    config.setdefault("last_updated", "")

    return config


def save_config(config: dict) -> None:
    """保存配置文件"""
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    os.chmod(path, 0o600)  # 仅本用户可读写（保护密钥）


# ── 公网 IP 检测 ───────────────────────────────────

def get_public_ipv4() -> Optional[str]:
    """获取公网 IPv4 地址"""
    return _get_public_ip(ipv6=False)


def get_public_ipv6() -> Optional[str]:
    """获取公网 IPv6 地址"""
    return _get_public_ip(ipv6=True)


def _get_public_ip(ipv6: bool = False) -> Optional[str]:
    """
    获取公网 IP 地址。
    
    Args:
        ipv6: True=获取IPv6, False=获取IPv4
    
    Returns:
        IP 地址字符串，失败返回 None
    """
    import urllib.request

    services = list(IP_SERVICES)
    if ipv6:
        # IPv6 专用服务
        services.insert(0, "https://api64.ip.sb/ip")

    for i, url in enumerate(services):
        try:
            log.debug(f"尝试从 {url} 获取{'IPv6' if ipv6 else 'IPv4'}...")
            req = urllib.request.Request(url, headers={"User-Agent": "AliDDNS/1.0"})
            
            # 设置超时
            with urllib.request.urlopen(req, timeout=10) as resp:
                ip = resp.read().decode("utf-8").strip()
                
                # 验证格式
                if ipv6 and ":" not in ip:
                    continue
                if not ipv6 and "." not in ip:
                    continue
                    
                log.info(f"成功获取公网 {'IPv6' if ipv6 else 'IPv4'}: {ip}")
                return ip
                
        except Exception as e:
            log.warning(f"{url} 失败: {e}")
            continue

    log.error("所有 IP 检测服务均失败")
    return None


def get_public_ip_by_dns() -> Optional[str]:
    """通过 DNS 查询外部地址（备用方案）"""
    try:
        # 用 opendns 的特殊域名解析
        socket.setdefaulttimeout(5)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("resolver1.opendns.com", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception as e:
        log.debug(f"DNS 方式获取 IP 失败: {e}")
        return None


# ── 阿里云 API 调用 ────────────────────────────────

def call_aliyun_api(
    access_key_id: str,
    access_key_secret: str,
    action: str,
    params: dict,
) -> dict:
    """
    调用阿里云 DNS API（纯 requests 实现，无需安装 SDK）。
    
    使用 RPC 风格签名：SHA256 + HMAC-SHA256。
    """
    from urllib.parse import quote_plus
    import hashlib
    import hmac
    import uuid

    # 构建公共参数
    common_params = {
        "Format": "JSON",
        "Version": "2015-01-09",
        "AccessKeyId": access_key_id,
        "SignatureMethod": "HMAC-SHA256",
        "Timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "SignatureVersion": "1.0",
        "SignatureNonce": str(uuid.uuid4()),
        "Action": action,
    }

    # 合并所有参数
    all_params = {**common_params, **params}

    # 排序并编码
    sorted_params = sorted(all_params.items())
    query_string = "&".join([f"{quote_plus(k)}={quote_plus(str(v))}" for k, v in sorted_params])

    # 签名字符串
    string_to_sign = f"GET&{quote_plus('/')}&{quote_plus(query_string)}"

    # 计算 HMAC-SHA256 签名
    secret = f"{access_key_secret}&"
    signature = hmac.new(
        secret.encode("utf-8"),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).digest()

    signature_b64 = __import__("base64").b64encode(signature).decode("utf-8")

    # 最终请求 URL
    final_url = (
        f"https://alidns.aliyuncs.com/?"
        f"{query_string}&Signature={quote_plus(signature_b64)}"
    )

    # 发送请求
    import urllib.request
    req = urllib.request.Request(final_url, headers={
        "User-Agent": "AliDDNS-Updater/1.0",
    })

    with urllib.request.urlopen(req, timeout=15) as resp:
        body = json.loads(resp.read().decode("utf-8"))

    return body


def describe_domain_records(
    access_key_id: str,
    access_key_secret: str,
    domain: str,
    subdomain: str,
    record_type: str = "A",
) -> Optional[dict]:
    """
    查询指定子域名的 DNS 记录。
    
    Returns:
        记录信息字典，未找到返回 None
    """
    rr_key = f"{subdomain}.{domain}" if subdomain != "@" else domain
    
    result = call_aliyun_api(access_key_id, access_key_secret, "DescribeDomainRecords", {
        "DomainName": domain,
        "RRKeyWord": subdomain,
        "Type": record_type,
        "PageSize": 50,
    })

    records = result.get("DomainRecords", {}).get("Record", [])
    
    for record in records:
        if record.get("RR") == subdomain or (subdomain == "@" and record.get("RR") == ""):
            return record
    
    return None


def add_or_update_record(
    access_key_id: str,
    access_key_secret: str,
    domain: str,
    subdomain: str,
    value: str,
    record_type: str = "A",
    ttl: int = 600,
) -> Tuple[bool, str]:
    """
    新增或更新 DNS 记录。
    
    Returns:
        (是否变更, 消息)
    """
    # 先查是否存在
    existing = describe_domain_records(access_key_id, access_key_secret, domain, subdomain, record_type)
    
    full_name = f"{subdomain}.{domain}" if subdomain != "@" else domain
    
    if existing:
        current_value = existing.get("Value", "")
        record_id = existing.get("RecordId")
        
        if current_value == value:
            log.info(f"[无需更新] {full_name} → {value} (与当前值一致)")
            return False, f"IP 未变: {value}"
        
        # 更新现有记录
        log.info(f"[更新记录] {full_name}: {current_value} → {value}")
        
        call_aliyun_api(access_key_id, access_key_secret, "UpdateDomainRecord", {
            "RecordId": record_id,
            "RR": subdomain,
            "Type": record_type,
            "Value": value,
            "TTL": str(ttl),
        })
        
        return True, f"已更新: {current_value} → {value}"
    else:
        # 新增记录
        log.info(f"[新增记录] {full_name} → {value}")
        
        call_aliyun_api(access_key_id, access_key_secret, "AddDomainRecord", {
            "DomainName": domain,
            "RR": subdomain,
            "Type": record_type,
            "Value": value,
            "TTL": str(ttl),
        })
        
        return True, f"新增记录: {value}"


# ── 主逻辑 ──────────────────────────────────────────

def check_and_update(config: dict, force: bool = False) -> bool:
    """执行一次检查和更新。Returns 是否有变更。"""
    
    # 获取当前公网 IP
    if config["record_type"] == "AAAA":
        new_ip = get_public_ipv6()
    else:
        new_ip = get_public_ipv4()
    
    if not new_ip:
        log.error("无法获取公网 IP")
        return False
    
    # 比较是否有变化
    old_ip = config.get("last_ip", "")
    
    if not force and new_ip == old_ip:
        log.info(f"IP 未变 ({new_ip})，跳过更新")
        return False
    
    # 调用阿里云 API 更新
    changed, message = add_or_update_record(
        access_key_id=config["access_key_id"],
        access_key_secret=config["access_key_secret"],
        domain=config["domain"],
        subdomain=config["subdomain"],
        value=new_ip,
        record_type=config["record_type"],
        ttl=config.get("ttl", 600),
    )
    
    # 保存最新状态
    config["last_ip"] = new_ip
    config["last_updated"] = datetime.now().isoformat()
    save_config(config)
    
    if changed:
        log.info(f"✅ DNS 已更新: {config['subdomain']}.{config['domain']} → {new_ip}")
    else:
        log.info(f"ℹ️  {message}")
    
    return changed


def run_daemon_mode(config: dict) -> None:
    """后台守护模式：持续循环检测"""
    interval = config.get("interval", 300)
    log.info(f"🚀 守护模式启动 | 子域名: {config['subdomain']}.{config['domain']} | 类型: {config['record_type']}")
    log.info(f"   检测间隔: {interval}s | 按 Ctrl+C 停止")

    # 启动时立即检测一次
    check_and_update(config, force=True)

    while True:
        try:
            time.sleep(interval)
            check_and_update(config)
        except KeyboardInterrupt:
            log.info("\n👋 收到停止信号，退出")
            break
        except Exception as e:
            log.error(f"检测异常: {e}", exc_info=True)
            time.sleep(30)  # 异常后等待30秒再试


# ── 交互式配置向导 ─────────────────────────────────

def interactive_setup() -> None:
    """引导用户完成首次配置"""
    print("=" * 60)
    print("  阿里云 DDNS 配置向导")
    print("=" * 60)
    print()

    # Step 1: AccessKey
    print("【第1步】阿里云 AccessKey 凭证")
    print("  获取方式:")
    print("  1. 打开 https://ram.console.aliyun.com/manage/ak")
    print("  2. 创建或复制你的 AccessKey ID 和 Secret")
    print("  3. ⚠️  确保 RAM 用户拥有 'AliyunDNSFullAccess' 权限")
    print()
    
    access_key_id = input("  AccessKey ID: ").strip()
    access_key_secret = input("  AccessKey Secret: ").strip()
    
    if not access_key_id or not access_key_secret:
        print("❌ AccessKey 不能为空！")
        sys.exit(1)
    
    print()
    print("【第2步】域名配置")
    domain = input(f"  你的域名 (例如: example.com): ").strip()
    
    if not domain:
        print("❌ 域名不能为空！")
        sys.exit(1)
    
    # 清理域名前缀
    if domain.startswith("http://") or domain.startswith("https://"):
        domain = domain.split("//")[1]
    domain = domain.rstrip("/").split("/")[0]
    
    default_subdomain = "wake"
    subdomain = input(f"  子域名 (默认: {default_subdomain}): ").strip() or default_subdomain
    
    print()
    print("【第3步】记录类型")
    print("  A    = IPv4 地址 (推荐，大多数情况)")
    print("  AAAA = IPv6 地址")
    
    record_type = input("  选择类型 [A/AAAA，默认: A]: ").strip().upper() or "A"
    if record_type not in ("A", "AAAA"):
        record_type = "A"

    print()
    print("【第4步】其他设置")
    interval_input = input(f"  检测间隔秒数 (默认: 300，即5分钟): ").strip()
    interval = int(interval_input) if interval_input.isdigit() else 300
    
    ttl_input = input(f"  DNS TTL 秒数 (默认: 600，即10分钟): ").strip()
    ttl = int(ttl_input) if ttl_input.isdigit() else 600

    # 构建配置
    config = {
        "access_key_id": access_key_id,
        "access_key_secret": access_key_secret,
        "domain": domain,
        "subdomain": subdomain,
        "record_type": record_type,
        "interval": interval,
        "ttl": ttl,
        "created_at": datetime.now().isoformat(),
        "last_ip": "",
        "last_updated": "",
    }
    
    # 保存
    save_config(config)
    
    print()
    print("=" * 60)
    print("✅ 配置已保存！")
    print(f"   配置文件: {get_config_path()}")
    print(f"   你的动态域名: {subdomain}.{domain}")
    print(f"   记录类型: {record_type}")
    print(f"   检测间隔: {interval}s")
    print()
    print("下一步操作:")
    print(f"  1. 运行测试:  python {Path(__file__).name} --test")
    print(f"  2. 后台运行:  python {Path(__file__).name}")
    print(f"  3. Windows自启: 运行 install_service.bat")
    print("=" * 60)


def show_status(config: dict) -> None:
    """显示当前状态"""
    full_domain = f"{config['subdomain']}.{config['domain']}"
    
    print("=" * 55)
    print("  阿里云 DDNS 状态")
    print("=" * 55)
    print(f"  动态域名:     {full_domain}")
    print(f"  记录类型:     {config['record_type']}")
    print(f"  当前解析 IP:  {config['last_ip'] or '(尚未检测)'}")
    print(f"  最后更新:     {config['last_updated'] or '(尚未更新)'}")
    print(f"  检测间隔:     {config['interval']}s")
    print(f"  TTL:          {config['ttl']}s")
    print(f"  配置创建于:   {config.get('created_at', '-')}")
    print("-" * 55)
    
    # 尝试查询实际 DNS 解析结果
    try:
        resolved_ip = socket.gethostbyname(full_domain)
        status_color = "✅" if resolved_ip == config.get('last_ip', '') else "⚠️"
        print(f"  DNS 实际解析:  {resolved_ip}  {status_color}")
    except Exception:
        print(f"  DNS 实际解析:  (无法解析 - 可能尚未添加记录)")
    
    print("=" * 55)


# ── CLI 入口 ────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="阿里云 DDNS 自动更新 — 免费动态域名解析",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python aliddns.py --setup              # 首次配置
  python aliddns.py                      # 后台守护运行
  python aliddns.py --test               # 测试一次
  python aliddns.py --status             # 查看状态
  python aliddns.py --force              # 强制更新
  python aliddns.py --subdomain home     # 使用不同子域名
""",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument("--setup", "-s", action="store_true", help="交互式首次配置")
    group.add_argument("--test", "-t", action="store_true", help="单次测试后退出")
    group.add_argument("--status", action="store_true", help="显示当前状态")
    group.add_argument("--force", "-f", action="store_true", help="强制更新（不比较旧IP）")

    parser.add_argument("--subdomain", type=str, help="指定子域名（覆盖配置）")
    parser.add_argument("--type", choices=["A", "AAAA"], help="记录类型（覆盖配置）")
    parser.add_argument("--interval", type=int, help="检测间隔秒数")
    parser.add_argument("--config", type=str, help="指定配置文件路径")
    parser.add_argument("--quiet", "-q", action="store_true", help="静默模式")

    args = parser.parse_args()

    # 自定义配置路径
    if args.config:
        global CONFIG_FILE
        CONFIG_FILE = Path(args.config)

    if args.quiet:
        log.setLevel(logging.WARNING)

    # Setup 模式
    if args.setup:
        interactive_setup()
        return

    # 加载配置
    config = load_config()

    # 命令行覆盖
    if args.subdomain:
        config["subdomain"] = args.subdomain
    if args.type:
        config["record_type"] = args.type
    if args.interval:
        config["interval"] = args.interval

    # Status 模式
    if args.status:
        show_status(config)
        return

    # 单次测试模式
    if args.test:
        log.info("🔍 单次测试模式")
        changed = check_and_update(config, force=args.force)
        sys.exit(0 if changed is not None else 1)

    # 默认：守护模式
    run_daemon_mode(config)


if __name__ == "__main__":
    main()
