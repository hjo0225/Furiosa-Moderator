"""Project 에 material_text 필드/컬럼/매핑이 실린다 (DB 불필요)."""
from __future__ import annotations

from datetime import datetime, timezone

from api.schemas.models import Project
from api.services import store
from api.services.db import ProjectRow


def test_project_schema_defaults_material_empty():
    assert Project(topic="주제").material_text == ""


def test_project_mapper_copies_material_text():
    row = ProjectRow(
        id="p_1", owner="anonymous", title="t", topic="주제",
        target="", material_text="배민클럽은 구독 멤버십", discord_webhook_url="",
        status="draft", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    p = store._project(row)
    assert p.material_text == "배민클럽은 구독 멤버십"
