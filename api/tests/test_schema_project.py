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


def test_webhook_route_registered():
    import api.main as m
    paths = {r.path for r in m.app.routes if hasattr(r, "path")}
    assert "/api/projects/{pid}/webhook" in paths


def test_set_webhook_updates_via_store(monkeypatch):
    from api.routers import projects
    from api.schemas.models import Project, WebhookSetIn

    updates = {}
    monkeypatch.setattr(projects.store, "get_project", lambda pid: Project(id="p_1", topic="t"))
    monkeypatch.setattr(projects.store, "update_project", lambda pid, patch: updates.update(patch))

    projects.set_webhook("p_1", WebhookSetIn(discord_webhook_url="https://discord.com/api/webhooks/1/abc"))
    assert updates == {"discord_webhook_url": "https://discord.com/api/webhooks/1/abc"}


def test_create_project_passes_webhook(monkeypatch):
    from api.routers import projects
    from api.schemas.models import ProjectCreateIn

    captured = {}
    monkeypatch.setattr(projects.store, "create_project",
                        lambda p: captured.update(url=p.discord_webhook_url) or p)

    projects.create_project(ProjectCreateIn(topic="주제", discord_webhook_url="https://discord.com/api/webhooks/1/abc"))
    assert captured["url"] == "https://discord.com/api/webhooks/1/abc"


def test_project_webhook_excluded_from_response():
    from api.schemas.models import Project
    p = Project(topic="t", discord_webhook_url="https://discord.com/api/webhooks/1/abc")
    assert "discord_webhook_url" not in p.model_dump()   # 응답에 시크릿 노출 안 됨
    assert p.discord_webhook_url == "https://discord.com/api/webhooks/1/abc"  # 속성 접근은 그대로


def test_webhook_input_rejects_non_discord_url():
    import pytest
    from pydantic import ValidationError
    from api.schemas.models import WebhookSetIn, ProjectCreateIn
    with pytest.raises(ValidationError):
        WebhookSetIn(discord_webhook_url="https://evil.example/x")
    with pytest.raises(ValidationError):
        ProjectCreateIn(topic="t", discord_webhook_url="http://discord.com/api/webhooks/1/a")  # http 는 거부


def test_webhook_input_accepts_discord_and_empty():
    from api.schemas.models import WebhookSetIn
    assert WebhookSetIn(discord_webhook_url="").discord_webhook_url == ""
    ok = "https://discord.com/api/webhooks/123/abcDEF"
    assert WebhookSetIn(discord_webhook_url=ok).discord_webhook_url == ok
