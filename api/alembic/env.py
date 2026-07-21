"""Alembic 환경 — 앱과 같은 Base·엔진을 쓴다.

sqlalchemy.url 대신 db.py._engine() 을 직접 쓰므로 Cloud SQL Connector /
DATABASE_URL 어느 경로든 앱과 똑같이 붙는다. 접속 정보 이중관리를 피한다.
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from api.services.db import Base, _engine

config = context.config
if config.config_file_name is not None:
    try:
        fileConfig(config.config_file_name)
    except Exception:   # noqa: BLE001 — 로깅 설정 실패가 마이그레이션을 막지 않게
        pass

target_metadata = Base.metadata


def run_migrations_online() -> None:
    connectable = _engine()
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url="postgresql://",
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
