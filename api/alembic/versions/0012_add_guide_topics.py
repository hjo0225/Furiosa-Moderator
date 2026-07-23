"""add guides.topics — 가이드 주제 > 질문 2단 (스펙 2026-07-24-guide-topics-turn-budget)

가이드의 정본이 평면 `questions` 에서 `topics`(주제 > 질문)로 바뀐다. 기존 행은 이 컬럼이
빈 배열이고, 읽을 때 `InterviewGuide` 가 평면 questions 를 주제 1개("전체")로 감싼다 —
**기존 데이터를 다시 쓰지 않는다.** 의뢰자가 가이드를 한 번 저장하면 그때 승격된다.

`questions` 컬럼은 남긴다. 진행자·인사이트·알림이 평면 뷰를 읽고 있고, 롤백 시 구버전
코드가 그대로 읽어야 하기 때문이다(파생 필드로 계속 기록한다).

Revision ID: 0012
Revises: 0011
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guides",
        sa.Column(
            "topics",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("guides", "topics")
