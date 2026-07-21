"""projects.material_text 필드 회귀 (모델·store 매핑)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace


def test_project_has_material_text_default():
    from api.schemas.models import Project
    assert Project(topic="t").material_text == ""
    assert Project(topic="t", material_text="자료 원문").material_text == "자료 원문"


def test_store_project_maps_material_text():
    from api.services import store

    row = SimpleNamespace(
        id="p_1", owner="anonymous", title="t", topic="주제", target="",
        material_text="자료", status="draft",
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    p = store._project(row, 0, 0)
    assert p.material_text == "자료"
