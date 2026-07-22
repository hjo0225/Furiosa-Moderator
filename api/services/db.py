"""Cloud SQL(Postgres) 연결 + ORM 테이블 정의.

아키텍처 §7 의 엔티티를 관계형으로 그대로 옮긴다. Firestore 문서 중첩 대신 FK 로 잇는다.
- project 1:N session 1:N turn
- guide / insight 는 project 당 1개(1:1)

접속은 Cloud SQL Python Connector 를 쓴다. Cloud Run 에서 --add-cloudsql-instances 로
유닉스 소켓을 붙이는 방식도 있지만, 커넥터는 로컬 개발에서도 같은 코드로 붙어서
'로컬에서 되는데 배포하면 안 되는' 격차가 안 생긴다.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from functools import lru_cache

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    text,
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ProjectRow(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner: Mapped[str] = mapped_column(String(128), default="anonymous")
    title: Mapped[str] = mapped_column(String(200), default="")
    topic: Mapped[str] = mapped_column(Text)
    target: Mapped[str] = mapped_column(Text, default="")
    motivation: Mapped[str] = mapped_column(Text, default="")
    utilization: Mapped[str] = mapped_column(Text, default="")
    material_text: Mapped[str] = mapped_column(Text, default="")
    discord_webhook_url: Mapped[str] = mapped_column(Text, default="")
    # 참가 조건 스크리너(F4.3) — 순서 있는 단일선택 문항 리스트. guides.questions 와 같은 판단으로 JSONB.
    screener: Mapped[list] = mapped_column(JSONB, default=list)
    # 지식팩 금칙어(F1.5) — 진행자가 먼저 꺼내면 안 되는 주제·표현 문자열 리스트. screener 와 같은 판단으로 JSONB.
    blocklist: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    sessions: Mapped[list["SessionRow"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class GuideRow(Base):
    __tablename__ = "guides"

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    goal: Mapped[str] = mapped_column(Text, default="")
    # 문항은 순서 있는 리스트라 JSONB 로 둔다. 문항 단위로 조회·집계할 일이 없고,
    # 별도 테이블로 빼면 순서 유지·버전 관리만 복잡해진다.
    questions: Mapped[list] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SessionRow(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    respondent_id: Mapped[str] = mapped_column(String(32), default="")
    status: Mapped[str] = mapped_column(String(16), default="consented", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    asked: Mapped[int] = mapped_column(Integer, default=0)
    summary: Mapped[str] = mapped_column(Text, default="")
    covered: Mapped[list] = mapped_column(JSONB, default=list)

    # 동의 로그 (R-1). PII 는 담지 않는다 — UA 는 해시만.
    consent_agreed: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    consent_purpose_version: Mapped[str] = mapped_column(String(16), default="v1")
    consent_ua_hash: Mapped[str] = mapped_column(String(32), default="")

    project: Mapped[ProjectRow] = relationship(back_populates="sessions")
    turns: Mapped[list["TurnRow"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class TurnRow(Base):
    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)  # 이미 마스킹된 텍스트만 들어온다
    emotion: Mapped[str] = mapped_column(String(16), default="", index=True)
    emotion_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    is_probe: Mapped[bool] = mapped_column(Boolean, default=False)
    question_id: Mapped[str] = mapped_column(String(16), default="")
    # F6.1 응답 버킷 분류 — 슬로우패스(reflect_bucket)가 사후 기입. 분포는 DB 실측이 센다(계약 1).
    bucket_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    bucket_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    bucket_evidence: Mapped[str] = mapped_column(Text, default="")
    pii_types: Mapped[list] = mapped_column(JSONB, default=list)
    guardrail_rewritten: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    session: Mapped[SessionRow] = relationship(back_populates="turns")


class InsightRow(Base):
    __tablename__ = "insights"

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    overall: Mapped[str] = mapped_column(Text, default="")
    themes: Mapped[list] = mapped_column(JSONB, default=list)
    sentiment: Mapped[dict] = mapped_column(JSONB, default=dict)
    # 문항별 버킷 분포(F6.4) — sentiment 와 같은 DB 실측을 인사이트 행에 함께 보존한다.
    bucket_distribution: Mapped[dict] = mapped_column(JSONB, default=dict)
    # 문항별 AI 요약(F6.3) — LLM 해석 출력. 버킷 분포와 같은 행에 함께 보존해 재방문 때도 유지.
    question_summaries: Mapped[list] = mapped_column(JSONB, default=list)
    session_count: Mapped[int] = mapped_column(Integer, default=0)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BriefingChunkRow(Base):
    __tablename__ = "briefing_chunks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    seq: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(200), default="")   # 출처 보존 (중립성 필터)
    angle: Mapped[str] = mapped_column(String(10), default="")     # 슬롯 필터 검색용
    embedding = mapped_column(Vector(1024))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MaterialRow(Base):
    __tablename__ = "materials"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(10))     # 'upload' | 'web'
    angle: Mapped[str] = mapped_column(String(10))      # '현상' | '원인' | '활용'
    url: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(Text, default="")
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SlotSummaryRow(Base):
    __tablename__ = "slot_summaries"

    project_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True
    )
    angle: Mapped[str] = mapped_column(String(10), primary_key=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


@lru_cache
def _engine():
    """엔진 싱글톤. INSTANCE_CONNECTION_NAME 이 있으면 커넥터, 없으면 DATABASE_URL."""
    icn = os.environ.get("INSTANCE_CONNECTION_NAME", "")
    if icn:
        from google.cloud.sql.connector import Connector, IPTypes

        connector = Connector(refresh_strategy="lazy")

        def getconn():
            return connector.connect(
                icn,
                "pg8000",
                user=os.environ.get("DB_USER", "postgres"),
                password=os.environ.get("DB_PASSWORD", ""),
                db=os.environ.get("DB_NAME", "mindlens"),
                ip_type=IPTypes.PUBLIC,
            )

        return create_engine(
            "postgresql+pg8000://",
            creator=getconn,
            pool_size=5,
            max_overflow=2,
            pool_pre_ping=True,   # Cloud Run 이 인스턴스를 재우면 죽은 커넥션이 남는다
            pool_recycle=1800,
        )

    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("INSTANCE_CONNECTION_NAME 또는 DATABASE_URL 이 필요합니다.")
    return create_engine(url, pool_pre_ping=True)


@lru_cache
def _factory():
    """sessionmaker 팩토리 자체를 캐시한다(세션이 아니라)."""
    return sessionmaker(bind=_engine(), expire_on_commit=False)


def db_session():
    """새 ORM 세션을 연다. 호출부는 `with db_session() as s:` 로 쓴다."""
    return _factory()()


def init_schema() -> None:
    """스키마 반영 — Alembic 이 단일 소스. 앱 startup 마다 upgrade head 를 적용한다.

    기존 DB(테이블은 있는데 alembic_version 이 없는 '최초 도입' 시점)는 현재 스키마를
    baseline 으로 stamp 한다 — 이미 있는 테이블을 다시 CREATE 하려다 터지는 걸 막는다.
    새·빈 DB 는 baseline 부터 upgrade 해서 테이블을 만든다.

    alembic 은 여기서만 import 한다(모듈 로드·테스트가 alembic 에 의존하지 않게).
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    api_dir = Path(__file__).resolve().parent.parent   # api/
    cfg = Config(str(api_dir / "alembic.ini"))
    cfg.set_main_option("script_location", str(api_dir / "alembic"))

    eng = _engine()
    with eng.connect() as conn:
        insp = inspect(conn)
        has_core = insp.has_table("projects")
        has_version = insp.has_table("alembic_version")

    if has_core and not has_version:
        command.stamp(cfg, "0001")   # 기존 스키마를 baseline(0001)으로 채택
    command.upgrade(cfg, "head")     # baseline 이후 마이그레이션(0002…)을 적용
