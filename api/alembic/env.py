"""Alembic 환경 — 앱과 같은 Base·엔진을 쓴다.

sqlalchemy.url 대신 db.py._engine() 을 직접 쓰므로 Cloud SQL Connector /
DATABASE_URL 어느 경로든 앱과 똑같이 붙는다. 접속 정보 이중관리를 피한다.
"""
from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from api.services.db import Base, _engine

config = context.config
# 앱 기동 경로(db.py 의 command.upgrade)에서는 로깅 설정을 아예 건드리지 않는다.
# fileConfig 는 disable_existing_loggers=False 로 불러도 **루트 핸들러·포맷·레벨을
# alembic.ini 것으로 교체**한다. 그 결과 운영에서 ① 포맷이 `WARNI [name]` 로 바뀌어
# Cloud Logging 에 severity 필드 없이 stderr 로 나가 `severity>=WARNING` 필터가
# 아무것도 못 잡고 ② 루트 레벨이 WARN 으로 고정돼 앱의 log.info 가 전부 버려졌다.
# (실제로 이 때문에 턴 지연 진단을 회귀 빌드 텔레메트리로 세 번 반복했다.)
# CLI 로 alembic 을 직접 돌릴 때만 ini 의 로깅 설정을 쓴다.
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    try:
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
