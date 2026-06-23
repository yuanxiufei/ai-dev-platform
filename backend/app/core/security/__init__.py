"""
安全模块 — 认证 + 内容安全

认证：
- 密码哈希/验证（Argon2 + Bcrypt）
- JWT Token 生成

内容安全：
- KeywordsStrategy: 正则关键词匹配
- LLMJudgeStrategy: LLM-as-Judge 安全裁判
- StrategySelector: 配置驱动的策略组装
"""

# ── 认证相关 ──────────────────────────────────────────
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher

from app.core.config import settings

password_hash = PasswordHash(
    (
        Argon2Hasher(),
        BcryptHasher(),
    )
)

ALGORITHM = "HS256"


def create_access_token(subject: str | Any, expires_delta: timedelta) -> str:
    expire = datetime.now(timezone.utc) + expires_delta
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_password(
    plain_password: str, hashed_password: str
) -> tuple[bool, str | None]:
    return password_hash.verify_and_update(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return password_hash.hash(password)


# ── 内容安全 ─────────────────────────────────────────
from app.core.security.content_safety import (  # noqa: F401, E402
    ContentSafetyStrategy,
    KeywordsStrategy,
    LLMJudgeStrategy,
    StrategySelector,
    init_content_safety,
    get_content_safety,
)
