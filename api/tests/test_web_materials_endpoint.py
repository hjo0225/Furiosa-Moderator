"""/materials/web — 선택분 크롤·저장, 실패분 스킵 (store/research monkeypatch)."""
from __future__ import annotations

from fastapi.testclient import TestClient

import api.main as main
from api.routers import projects as pm
from api.schemas.models import Project


def test_add_web_materials_stores_crawled(monkeypatch):
    created = []
    monkeypatch.setattr(pm.store, "get_project", lambda pid: Project(id=pid, topic="t"))
    monkeypatch.setattr(pm.store, "list_materials", lambda pid: [])          # 기존 풀 비어있음
    monkeypatch.setattr(pm.store, "create_material", lambda m: created.append(m) or m)
    monkeypatch.setattr(pm.research, "crawl", lambda urls: {"http://a": "본문A"})   # b 실패
    incr = []
    monkeypatch.setattr(pm.briefing_pipeline, "add_materials_incremental",
                        lambda pid, mats: incr.extend(mats))
    resp = TestClient(main.app).post("/api/projects/p_1/materials/web", json={
        "selected": [
            {"angle": "현상", "title": "A", "url": "http://a"},
            {"angle": "활용", "title": "B", "url": "http://b"},
        ]})
    assert resp.status_code == 200
    body = resp.json()
    assert body["stored"] == 1 and body["failed"] == ["http://b"]
    assert created[0].source == "web" and created[0].angle == "현상" and created[0].text == "본문A"
    assert [m.angle for m in incr] == ["현상"]         # 증분 후처리에 저장분 전달


def test_add_web_materials_empty_400(monkeypatch):
    monkeypatch.setattr(pm.store, "get_project", lambda pid: Project(id=pid, topic="t"))
    resp = TestClient(main.app).post("/api/projects/p_1/materials/web", json={"selected": []})
    assert resp.status_code == 400


def test_add_web_materials_skips_duplicate_urls(monkeypatch):
    monkeypatch.setattr(pm.store, "get_project", lambda pid: Project(id=pid, topic="t"))
    monkeypatch.setattr(pm.store, "list_materials",
                        lambda pid: [type("M", (), {"url": "http://dup"})()])  # 이미 풀에 있음
    called = {"crawl": 0}
    monkeypatch.setattr(pm.research, "crawl", lambda urls: called.update(crawl=1) or {})
    monkeypatch.setattr(pm.briefing_pipeline, "add_materials_incremental", lambda pid, mats: None)
    resp = TestClient(main.app).post("/api/projects/p_1/materials/web", json={
        "selected": [{"angle": "현상", "title": "D", "url": "http://dup"}]})
    assert resp.status_code == 200
    assert resp.json()["skipped"] == ["http://dup"] and resp.json()["stored"] == 0
    assert called["crawl"] == 0                        # 중복뿐이라 크롤조차 안 함
