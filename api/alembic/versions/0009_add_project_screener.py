"""add projects.screener — 참가 조건 스크리너(F4.3)

동의 후·인터뷰 전 자격 판정용 단일선택 문항 리스트를 프로젝트에 붙인다. 문항은 순서 있는
리스트라 별도 테이블 대신 JSONB 로 둔다(guides.questions 와 같은 판단). 리스트 컬럼이라
server_default 는 빈 JSON 배열("[]")이다(0008 과 같은 계열, 0007 의 dict "{}" 와 대비).

Revision ID: 0009
Revises: 0008
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "screener",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "screener")
