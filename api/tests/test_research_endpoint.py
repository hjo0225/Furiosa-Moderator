"""/research — 브리프로 후보 반환 (store/research monkeypatch)."""
from __future__ import annotations

from fastapi.testclient import TestClient

import api.main as main
from api.routers import projects as pm
from api.schemas.models import Project
from api.services import research


def test_research_route_registered():
    paths = {r.path for r in main.app.routes if hasattr(r, "path")}
    assert "/api/projects/{pid}/research" in paths


def test_research_returns_candidates(monkeypatch):
    monkeypatch.setattr(pm.store, "get_project",
                        lambda pid: Project(id=pid, topic="금주", target="2030"))
    monkeypatch.setattr(pm.research, "research_queries", lambda *a: {"현상": ["q"]})
    monkeypatch.setattr(pm.research, "search",
                        lambda sq: [research.Candidate("현상", "T", "http://a", "s")])
    resp = TestClient(main.app).post("/api/projects/p_1/research")
    assert resp.status_code == 200
    c = resp.json()["candidates"][0]
    assert c["url"] == "http://a" and c["angle"] == "현상"
