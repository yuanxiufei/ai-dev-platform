from collections.abc import Generator
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session, SQLModel

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.models import TokenPayload, User

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def commit_or_rollback(session: Session, obj: SQLModel | None = None) -> None:
    """安全提交数据库 — 失败时自动 rollback。

    用法：
        commit_or_rollback(session, user)  # 先 add(obj) 再 commit + refresh
        commit_or_rollback(session)        # 仅 commit（用于 delete / bulk update）
    """
    try:
        if obj is not None:
            if obj not in session:
                session.add(obj)
        session.commit()
        if obj is not None:
            session.refresh(obj)
    except Exception:
        session.rollback()
        raise


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_ws(token: str) -> User:
    """从原始 token 字符串验证用户 — 用于 WebSocket 端点。

    WebSocket 无法使用 OAuth2PasswordBearer 机制，因此需要从
    query 参数中手动提取 token 并调用此函数进行验证。
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    with Session(engine) as session:
        user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Inactive user")
    return user


def get_current_active_superuser(current_user: CurrentUser) -> User:
    """验证当前用户是否为超级管理员。
    
    注意：当前实现依赖 get_current_user 已完成 is_active 检查，
    若作为独立依赖使用，需额外验证 is_active。
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user
