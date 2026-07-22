"""add insights.bucket_distribution — 문항별 버킷 분포 실측(F6.4)

sentiment 와 똑같이 DB 실측으로 채워지는 집계라, 같은 인사이트 행에 함께 보존해
대시보드 재방문(get_insight) 때도 분포가 유지되게 한다. LLM 이 세지 않는다(계약 1).

Revision ID: 0007
Revises: 0006
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "insights",
        sa.Column(
            "bucket_distribution",
            postgresql.JSONB(),
            nullable=False,
            server_default="{}",
        ),
    )


def downgrade() -> None:
    op.drop_column("insights", "bucket_distribution")
