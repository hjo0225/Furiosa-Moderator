"""add insights.question_summaries — 문항별 AI 요약(F6.3)

버킷 분포(0007)와 같은 인사이트 행에 문항별 요약을 함께 보존해, 대시보드 재방문
(get_insight) 때도 문항별 headline+summary 가 유지되게 한다. 버킷 분포는 DB 실측이지만
이건 LLM 해석 출력이다(theme 요약과 같은 계열) — '세는' 값이 아니라 서술 요약이다.

리스트 컬럼이라 server_default 는 빈 JSON 배열("[]")이다(0007 의 dict "{}" 와 대비).

Revision ID: 0008
Revises: 0007
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "insights",
        sa.Column(
            "question_summaries",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("insights", "question_summaries")
