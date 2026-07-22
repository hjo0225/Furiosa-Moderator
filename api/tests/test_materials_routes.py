"""GET/DELETE /materials — 목록(본문 제외)·삭제(refresh_project 호출)."""
from __future__ import annotations

from fastapi.testclient import TestClient

import api.main as main
from api.routers import projects as pm
from api.schemas.models import Material, Project


def test_list_materials_excludes_text(monkeypatch):
    monkeypatch.setattr(pm.store, "get_project", lambda pid: Project(id=pid, topic="t"))
    monkeypatch.setattr(pm.store, "list_materials", lambda pid: [
        Material(id="m1", source="web", angle="현상", url="http://a", title="A", text="긴 본문"),
    ])
    resp = TestClient(main.app).get("/api/projects/p_1/materials")
    assert resp.status_code == 200
    item = resp.json()[0]
    assert item == {"id": "m1", "source": "web", "angle": "현상", "title": "A", "url": "http://a"}
    assert "text" not in item                    # 본문 제외


def test_delete_material_calls_refresh(monkeypatch):
    monkeypatch.setattr(pm.store, "get_project", lambda pid: Project(id=pid, topic="t"))
    deleted, refreshed = {}, {}
    monkeypatch.setattr(pm.store, "delete_material", lambda pid, mid: deleted.update(mid=mid))
    monkeypatch.setattr(pm.briefing_pipeline, "refresh_project", lambda pid: refreshed.update(pid=pid))
    resp = TestClient(main.app).delete("/api/projects/p_1/materials/m1")
    assert resp.status_code == 200 and resp.json() == {"deleted": "m1"}
    assert deleted == {"mid": "m1"} and refreshed == {"pid": "p_1"}
