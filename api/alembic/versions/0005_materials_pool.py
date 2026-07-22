"""materials 풀 + slot_summaries + briefing_chunks.angle — 웹 리서치 자료 수집."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "materials",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("angle", sa.String(10), nullable=False),
        sa.Column("url", sa.Text(), nullable=False, server_default=""),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_materials_project_id", "materials", ["project_id"])
    op.create_table(
        "slot_summaries",
        sa.Column("project_id", sa.String(32),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("angle", sa.String(10), primary_key=True),
        sa.Column("summary", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("briefing_chunks",
                  sa.Column("angle", sa.String(10), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("briefing_chunks", "angle")
    op.drop_table("slot_summaries")
    op.drop_index("ix_materials_project_id", table_name="materials")
    op.drop_table("materials")
