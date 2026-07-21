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
        material_text="자료", discord_webhook_url="", status="draft",
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    p = store._project(row, 0, 0)
    assert p.material_text == "자료"


def test_project_has_discord_webhook_url_default():
    from api.schemas.models import Project
    assert Project(topic="t").discord_webhook_url == ""
    assert Project(topic="t", discord_webhook_url="https://x").discord_webhook_url == "https://x"


def test_store_project_maps_discord_webhook_url():
    from api.services import store
    row = SimpleNamespace(
        id="p_1", owner="anonymous", title="t", topic="주제", target="",
        material_text="", discord_webhook_url="https://x", status="draft",
        created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    p = store._project(row, 0, 0)
    assert p.discord_webhook_url == "https://x"
