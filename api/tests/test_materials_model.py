"""materials 스키마·매퍼 (DB 불필요)."""
from __future__ import annotations

from datetime import datetime, timezone

from api.schemas.models import Material
from api.services import store
from api.services.db import MaterialRow


def test_material_schema_defaults():
    m = Material(source="web", angle="현상")
    assert m.id == "" and m.url == "" and m.title == "" and m.text == ""


def test_material_mapper_copies_fields():
    row = MaterialRow(
        id="m_1", project_id="p_1", source="web", angle="활용",
        url="http://x", title="T", text="본문",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    m = store._material(row)
    assert m.source == "web" and m.angle == "활용"
    assert m.url == "http://x" and m.text == "본문"
