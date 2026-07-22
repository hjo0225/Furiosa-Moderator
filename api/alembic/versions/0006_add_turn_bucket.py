"""add turns.bucket_id·bucket_confidence·bucket_evidence — 응답 버킷 분류(F6.1)

reflect_bucket 슬로우패스가 각 응답자 턴을 문항 코드북(response_buckets) 중 하나로
분류해 사후 기입한다. 분포(버킷별 N)는 이 컬럼들을 DB 에서 group-by 로 센다(계약 1).

Revision ID: 0006
Revises: 0005
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "turns",
        sa.Column("bucket_id", sa.String(32), nullable=False, server_default=""),
    )
    op.add_column(
        "turns",
        sa.Column("bucket_confidence", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "turns",
        sa.Column("bucket_evidence", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_turns_bucket_id", "turns", ["bucket_id"])


def downgrade() -> None:
    op.drop_index("ix_turns_bucket_id", table_name="turns")
    op.drop_column("turns", "bucket_evidence")
    op.drop_column("turns", "bucket_confidence")
    op.drop_column("turns", "bucket_id")
