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
        # disable_existing_loggers=False 필수 — 기본값 True 로 두면 기동 시
        # 실행되는 마이그레이션(db.py 의 command.upgrade)이 fileConfig 를 타면서
        # import 시점에 만들어진 앱 로거(mindlens, api.services.*, api.interview.*)를
        # 전부 disable 시켜버려 운영 로그가 전혀 안 찍히는 문제가 있었다.
        fileConfig(config.config_file_name, disable_existing_loggers=False)
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
