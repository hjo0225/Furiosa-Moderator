"""업로드 엔드포인트 + 가이드 생성이 자료를 주입하는지 (DB/LLM 은 monkeypatch)."""
from __future__ import annotations

from fastapi.testclient import TestClient

import api.main as main
from api.routers import projects as projects_mod
from api.schemas.models import GuideQuestion, InterviewGuide, Project
from api.services import store as store_mod


def test_material_route_registered():
    paths = {r.path for r in main.app.routes if hasattr(r, "path")}
    assert "/api/projects/{pid}/material" in paths


def test_upload_material_stores_text(monkeypatch):
    saved: dict = {}
    monkeypatch.setattr(store_mod, "get_project", lambda pid: Project(id=pid, topic="주제"))
    monkeypatch.setattr(store_mod, "update_project", lambda pid, patch: saved.update(patch))
    client = TestClient(main.app)
    resp = client.post(
        "/api/projects/p_1/material",
        files={"file": ("brief.txt", "배민클럽은 구독 멤버십".encode("utf-8"), "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["chars"] > 0 and body["truncated"] is False
    assert "배민클럽" in saved["material_text"]


def test_upload_material_rejects_unknown_ext(monkeypatch):
    monkeypatch.setattr(store_mod, "get_project", lambda pid: Project(id=pid, topic="주제"))
    client = TestClient(main.app)
    resp = client.post(
        "/api/projects/p_1/material",
        files={"file": ("data.bin", b"\x00\x01", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_upload_material_rejects_too_large(monkeypatch):
    monkeypatch.setattr(store_mod, "get_project", lambda pid: Project(id=pid, topic="주제"))
    monkeypatch.setattr(projects_mod, "_MAX_UPLOAD_BYTES", 10)  # 큰 페이로드 없이 가드만 검증
    client = TestClient(main.app)
    resp = client.post(
        "/api/projects/p_1/material",
        files={"file": ("brief.txt", b"x" * 50, "text/plain")},
    )
    assert resp.status_code == 400


def test_generate_guide_injects_material(monkeypatch):
    captured: dict = {}

    class FakeLLM:
        def structured(self, system, user, schema, **kw):
            captured["user"] = user
            return (
                InterviewGuide(goal="g", questions=[GuideQuestion(id="q1", text="?", goal="")]),
                None,
            )

    monkeypatch.setattr(projects_mod, "get_llm", lambda: FakeLLM())
    monkeypatch.setattr(
        store_mod, "get_project",
        lambda pid: Project(id=pid, topic="주제", material_text="배민클럽 설명"),
    )
    monkeypatch.setattr(store_mod, "save_guide", lambda pid, g: g)
    client = TestClient(main.app)
    resp = client.post("/api/projects/p_1/guide", json={})
    assert resp.status_code == 200
    assert "배민클럽 설명" in captured["user"]
    assert "[참고 자료]" in captured["user"]
