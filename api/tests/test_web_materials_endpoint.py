"""/materials/web — 선택분 크롤·저장, 실패분 스킵 (store/research monkeypatch)."""
from __future__ import annotations

from fastapi.testclient import TestClient

import api.main as main
from api.routers import projects as pm
from api.schemas.models import Project


def test_add_web_materials_stores_crawled(monkeypatch):
    saved = []
    monkeypatch.setattr(pm.store, "get_project", lambda pid: Project(id=pid, topic="t"))
    monkeypatch.setattr(pm.store, "create_material", lambda m: saved.append(m) or m)
    monkeypatch.setattr(pm.research, "crawl", lambda urls: {"http://a": "본문A"})   # b 실패
    monkeypatch.setattr(pm.briefing_pipeline, "refresh_project", lambda pid: None)
    resp = TestClient(main.app).post("/api/projects/p_1/materials/web", json={
        "selected": [
            {"angle": "현상", "title": "A", "url": "http://a"},
            {"angle": "활용", "title": "B", "url": "http://b"},
        ]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["stored"] == 1 and body["failed"] == ["http://b"]
    assert saved[0].source == "web" and saved[0].angle == "현상" and saved[0].text == "본문A"


def test_add_web_materials_empty_400(monkeypatch):
    monkeypatch.setattr(pm.store, "get_project", lambda pid: Project(id=pid, topic="t"))
    resp = TestClient(main.app).post("/api/projects/p_1/materials/web", json={"selected": []})
    assert resp.status_code == 400
