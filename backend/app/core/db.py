from sqlmodel import Session, create_engine, select

from app import crud
from app.core.config import settings
from app.models import User, UserCreate

# 根据数据库类型设置 connect_args
_database_url = str(settings.SQLALCHEMY_DATABASE_URI)
_connect_args: dict = {}
if "postgresql" in _database_url or "postgres" in _database_url:
    _connect_args = {"connect_timeout": 10}
else:
    # SQLite：允许多线程访问（FastAPI 异步上下文）
    _connect_args = {"check_same_thread": False}

engine = create_engine(
    _database_url,
    pool_pre_ping=True if "postgresql" in _database_url else False,
    pool_size=5,
    max_overflow=10,
    connect_args=_connect_args,
)


# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


def init_db(session: Session) -> None:
    # Tables should primarily be managed via Alembic migrations.
    # create_all serves as a safety net for any tables not yet covered
    # by migrations — it is not idempotent for schema changes but safe
    # for initial schema bootstrap.
    from sqlmodel import SQLModel

    # This works because the models are already imported and registered from app.models
    SQLModel.metadata.create_all(engine)

    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
        )
        user = crud.create_user(session=session, user_create=user_in)
