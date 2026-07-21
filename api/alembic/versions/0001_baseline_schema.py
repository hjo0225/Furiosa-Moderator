"""baseline schema — 기존 create_all 스키마를 Alembic baseline 으로 고정한다.

projects·guides·sessions·turns·insights. projects.material_text 포함
(협업자가 prod 에 수동 추가한 컬럼을 코드·마이그레이션에 정합시킨다).

중요: 기존 DB 는 이 마이그레이션을 **실행하지 않고** stamp 로 채택된다
(db.init_schema 의 stamp 분기). 새·빈 DB 에서만 실제로 테이블을 만든다.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("owner", sa.String(128), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("target", sa.Text(), nullable=False),
        sa.Column("material_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_projects_status", "projects", ["status"])
    op.create_index("ix_projects_created_at", "projects", ["created_at"])

    op.create_table(
        "guides",
        sa.Column("project_id", sa.String(32),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("questions", postgresql.JSONB(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("respondent_id", sa.String(32), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("asked", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("covered", postgresql.JSONB(), nullable=False),
        sa.Column("consent_agreed", sa.Boolean(), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consent_purpose_version", sa.String(16), nullable=False),
        sa.Column("consent_ua_hash", sa.String(32), nullable=False),
    )
    op.create_index("ix_sessions_project_id", "sessions", ["project_id"])
    op.create_index("ix_sessions_status", "sessions", ["status"])

    op.create_table(
        "turns",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("session_id", sa.String(32),
                  sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("emotion", sa.String(16), nullable=False),
        sa.Column("emotion_confidence", sa.Float(), nullable=False),
        sa.Column("is_probe", sa.Boolean(), nullable=False),
        sa.Column("question_id", sa.String(16), nullable=False),
        sa.Column("pii_types", postgresql.JSONB(), nullable=False),
        sa.Column("guardrail_rewritten", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_turns_session_id", "turns", ["session_id"])
    op.create_index("ix_turns_emotion", "turns", ["emotion"])
    op.create_index("ix_turns_created_at", "turns", ["created_at"])

    op.create_table(
        "insights",
        sa.Column("project_id", sa.String(32),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("overall", sa.Text(), nullable=False),
        sa.Column("themes", postgresql.JSONB(), nullable=False),
        sa.Column("sentiment", postgresql.JSONB(), nullable=False),
        sa.Column("session_count", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("insights")
    op.drop_table("turns")
    op.drop_table("sessions")
    op.drop_table("guides")
    op.drop_table("projects")
