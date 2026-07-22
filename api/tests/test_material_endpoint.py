"""업로드 엔드포인트 + 가이드 생성이 자료를 주입하는지 (DB/LLM 은 monkeypatch)."""
from __future__ import annotations

from fastapi.testclient import TestClient

import api.main as main
from api.routers import projects as projects_mod
from api.schemas.models import Project
from api.services import store as store_mod


def test_material_route_registered():
    paths = {r.path for r in main.app.routes if hasattr(r, "path")}
    assert "/api/projects/{pid}/material" in paths


def test_create_project_requires_all_brief_fields(monkeypatch):
    client = TestClient(main.app)
    # 일부만 채우면 400 (검증이 store 접근 전에 막는다 — DB 불필요)
    resp = client.post("/api/projects", json={"topic": "조사 목적만"})
    assert resp.status_code == 400
    for name in ("타깃 대상", "동기", "활용 방안"):
        assert name in resp.json()["detail"]
    # 4개 다 채우면 통과
    monkeypatch.setattr(store_mod, "create_project", lambda p: p)
    ok = client.post(
        "/api/projects",
        json={"topic": "목적", "target": "대상", "motivation": "동기", "utilization": "활용"},
    )
    assert ok.status_code == 200


def test_upload_material_creates_row(monkeypatch):
    saved = []
    monkeypatch.setattr(store_mod, "get_project", lambda pid: Project(id=pid, topic="주제"))
    monkeypatch.setattr(store_mod, "create_material", lambda m: saved.append(m) or m)
    monkeypatch.setattr(projects_mod.briefing_pipeline, "add_materials_incremental", lambda pid, mats: None)
    client = TestClient(main.app)
    resp = client.post(
        "/api/projects/p_1/material",
        files={"file": ("brief.txt", "배민클럽은 구독 멤버십".encode("utf-8"), "text/plain")},
        data={"angle": "현상"},
    )
    assert resp.status_code == 200
    assert saved[0].source == "upload" and saved[0].angle == "현상"
    assert "배민클럽" in saved[0].text


def test_upload_material_rejects_unknown_ext(monkeypatch):
    monkeypatch.setattr(store_mod, "get_project", lambda pid: Project(id=pid, topic="주제"))
    client = TestClient(main.app)
    resp = client.post(
        "/api/projects/p_1/material",
        files={"file": ("data.bin", b"\x00\x01", "application/octet-stream")},
        data={"angle": "현상"},
    )
    assert resp.status_code == 400


def test_upload_material_rejects_too_large(monkeypatch):
    monkeypatch.setattr(store_mod, "get_project", lambda pid: Project(id=pid, topic="주제"))
    monkeypatch.setattr(projects_mod, "_MAX_UPLOAD_BYTES", 10)  # 큰 페이로드 없이 가드만 검증
    client = TestClient(main.app)
    resp = client.post(
        "/api/projects/p_1/material",
        files={"file": ("brief.txt", b"x" * 50, "text/plain")},
        data={"angle": "현상"},
    )
    assert resp.status_code == 400
