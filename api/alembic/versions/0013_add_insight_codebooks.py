"""add insights.codebooks — 코드북 귀납 생성 (스펙 2026-07-24-qualitative-narrative-guide)

버킷(코드북)을 가이드가 아니라 인사이트가 소유한다. 인터뷰가 끝난 뒤 실제 전사에서 문항별로
버킷을 만들어 이 컬럼에 저장한다. {question_id: [ResponseBucket]}. 기존 행은 빈 JSON 이고,
결과 화면은 라벨을 여기서 먼저 찾고 없으면 가이드 버킷으로 폴백하므로 기존 인사이트도 그대로 뜬다.

Revision ID: 0013
Revises: 0012
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "insights",
        sa.Column("codebooks", postgresql.JSONB(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("insights", "codebooks")
