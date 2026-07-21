"""add projects.motivation·utilization — 조사 브리프 필드(동기·활용 방안)

Revision ID: 0003
Revises: 0002
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("motivation", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "projects",
        sa.Column("utilization", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("projects", "utilization")
    op.drop_column("projects", "motivation")
