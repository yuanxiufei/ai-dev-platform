"""
加密工具 — API Key AES 加密存储

基于 cryptography.fernet 实现：
- 使用 SECRET_KEY 派生 Fernet 密钥（SHA256→base64）
- 加密：encrypt(plaintext) → ciphertext
- 解密：decrypt(ciphertext) → plaintext
- 密钥持久化：从环境变量 SECRET_KEY 派生，服务重启后仍可解密
"""
from __future__ import annotations

import base64
import hashlib
import os
from typing import Optional

# 延迟导入 cryptography，避免启动时无此依赖时崩溃
_Fernet: Optional[type] = None
_fernet_instance: Optional[object] = None


def _get_fernet():
    """延迟加载 cryptography.fernet。"""
    global _Fernet
    if _Fernet is None:
        try:
            from cryptography.fernet import Fernet as _F
            _Fernet = _F
        except ImportError:
            raise ImportError(
                "cryptography is required for API key encryption. "
                "Install it with: pip install cryptography"
            )
    return _Fernet


def _derive_key(secret: str) -> bytes:
    """从 SECRET_KEY 派生 Fernet 兼容的 32 字节 URL-safe base64 密钥。

    Fernet 要求 32 字节的 URL-safe base64 编码密钥。
    方法：SHA256(secret) → 32 bytes → base64.urlsafe_b64encode。
    """
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet_instance() -> object:
    """获取全局 Fernet 单例。"""
    global _fernet_instance
    if _fernet_instance is None:
        from app.core.config import settings
        Fernet = _get_fernet()
        key = _derive_key(settings.SECRET_KEY)
        _fernet_instance = Fernet(key)
    return _fernet_instance


def encrypt_api_key(plaintext: str) -> str:
    """加密 API Key。

    Args:
        plaintext: 原始 API Key 明文

    Returns:
        base64 编码的密文令牌字符串

    Raises:
        ImportError: 如果 cryptography 未安装
    """
    if not plaintext:
        return ""
    fernet = _get_fernet_instance()
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_api_key(ciphertext: str) -> str:
    """解密 API Key。

    Args:
        ciphertext: encrypt_api_key() 返回的密文

    Returns:
        原始 API Key 明文

    Raises:
        ImportError: 如果 cryptography 未安装
        cryptography.fernet.InvalidToken: 如果密文无效或密钥不匹配
    """
    if not ciphertext:
        return ""
    fernet = _get_fernet_instance()
    return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


def mask_api_key(key: str, visible: int = 4) -> str:
    """脱敏显示 API Key（仅显示首尾各 N 位）。

    Args:
        key: 完整 API Key
        visible: 首尾可见字符数

    Returns:
        脱敏字符串，如 "sk-a***b1c2"
    """
    if not key or len(key) <= visible * 2:
        return "*" * min(len(key), 8)
    return key[:visible] + "*" * min(len(key) - visible * 2, 6) + key[-visible:]
