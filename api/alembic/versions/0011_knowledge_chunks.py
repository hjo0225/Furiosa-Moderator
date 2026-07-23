"""knowledge_chunks — 글로벌 지식 풀 (pgvector). RAG-5 인프라 도입분.

briefing_chunks 와 달리 project_id 가 없는 전역 테이블이다. corpus 로 데이터셋을
나누고 meta(JSONB)로 하드필터를 건다. 컬럼 정의는 db.KnowledgeChunkRow 와 1:1로 맞춘다.

embedding 은 pgvector Vector(1024) — vector 확장 생성은 0004 에서 이미 멱등으로 했지만,
이 마이그레이션만 단독 적용될 때도 안전하도록 IF NOT EXISTS 로 한 번 더 보장한다(멱등).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("corpus", sa.String(32), nullable=False),
        sa.Column("title", sa.Text(), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("embedding", Vector(1024), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_knowledge_chunks_corpus", "knowledge_chunks", ["corpus"])


def downgrade() -> None:
    op.drop_index("ix_knowledge_chunks_corpus", table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
