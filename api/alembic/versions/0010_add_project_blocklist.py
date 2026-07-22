"""add projects.blocklist — 지식팩 금칙어(F1.5)

진행자가 절대 먼저 꺼내면 안 되는 주제·표현 리스트를 프로젝트에 붙인다. 팩은 '읽기 전용·
발화 금지'라, 이건 팩이 말해선 안 되는 것을 명시하는 두 번째 방어선이다. 순서 있는 문자열
리스트라 별도 테이블 대신 JSONB 로 둔다(0009 screener 와 같은 판단). server_default 는 빈
JSON 배열("[]")이다(0009 와 같은 계열).

Revision ID: 0010
Revises: 0009
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "blocklist",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "blocklist")
