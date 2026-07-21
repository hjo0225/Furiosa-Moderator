"""briefing_chunks — RAG 브리핑 팩 (pgvector). TICKET-5 도입분을 Alembic 규칙에 편입.

langgraph 브랜치는 이 테이블을 create_all 로 만들었으나, main 은 Alembic 이 스키마
단일 소스다. 병합하며 create_all 을 버리고(db.init_schema) 이 마이그레이션으로 정식 추가한다.

embedding 은 pgvector Vector(1024) — vector 확장이 먼저 있어야 하므로 테이블보다 앞서
생성한다(IF NOT EXISTS, 멱등). 컬럼 정의는 db.BriefingChunkRow 와 1:1로 맞춘다.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "briefing_chunks",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(200), nullable=False, server_default=""),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_briefing_chunks_project_id", "briefing_chunks", ["project_id"])


def downgrade() -> None:
    op.drop_index("ix_briefing_chunks_project_id", table_name="briefing_chunks")
    op.drop_table("briefing_chunks")
