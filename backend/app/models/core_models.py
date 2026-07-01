"""
核心认证/用户模型 — User, Item, Tenant, Token 等基础模型
"""
import uuid
from datetime import datetime, timezone

from pydantic import EmailStr
from sqlalchemy import DateTime, Text, Boolean
from sqlmodel import Column, Field, Relationship, SQLModel


def get_datetime_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── Tenant (多租户) ──────────────────────────────────

class TenantBase(SQLModel):
    name: str = Field(max_length=100)
    slug: str = Field(max_length=50, index=True, unique=True)
    is_active: bool = True
    plan: str = Field(default="free", max_length=20)  # free | pro | enterprise
    quota_limit: int = Field(default=1000)              # 资源配额上限


class Tenant(TenantBase, table=True):
    __tablename__ = "tenant"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    config_json: dict | None = Field(default=None, sa_column=Column("config_json", Text))
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),
    )
    updated_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))

    users: list["User"] = Relationship(back_populates="tenant")


class TenantPublic(TenantBase):
    id: uuid.UUID
    created_at: datetime | None = None


class TenantCreate(SQLModel):
    name: str
    slug: str
    plan: str = "free"


class TenantUpdate(SQLModel):
    name: str | None = None
    is_active: bool | None = None
    plan: str | None = None
    quota_limit: int | None = None


# ── User ─────────────────────────────────────────────

class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)


class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)
    tenant_id: uuid.UUID | None = None


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    tenant_slug: str | None = Field(default=None, max_length=50)


class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore[assignment]
    password: str | None = Field(default=None, min_length=8, max_length=128)


class UserUpdateMe(SQLModel):
    full_name: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    tenant_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="tenant.id",
        nullable=True,
        index=True,
    )
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    items: list["Item"] = Relationship(back_populates="owner", cascade_delete=True)
    tenant: Tenant | None = Relationship(back_populates="users")


class UserPublic(UserBase):
    id: uuid.UUID
    tenant_id: uuid.UUID | None = None
    created_at: datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic]
    total: int
    page: int
    size: int


# ── Item ─────────────────────────────────────────────

class ItemBase(SQLModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=255)


class ItemCreate(ItemBase):
    pass


class ItemUpdate(ItemBase):
    title: str | None = Field(default=None, min_length=1, max_length=255)  # type: ignore[assignment]


class Item(ItemBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime | None = Field(
        default_factory=get_datetime_utc,
        sa_type=DateTime(timezone=True),  # type: ignore
    )
    owner_id: uuid.UUID = Field(
        foreign_key="user.id", nullable=False, ondelete="CASCADE"
    )
    owner: User | None = Relationship(back_populates="items")


class ItemPublic(ItemBase):
    id: uuid.UUID
    owner_id: uuid.UUID
    created_at: datetime | None = None


class ItemsPublic(SQLModel):
    data: list[ItemPublic]
    count: int


# ── Auth ─────────────────────────────────────────────

class Message(SQLModel):
    message: str


class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(SQLModel):
    sub: str | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)
