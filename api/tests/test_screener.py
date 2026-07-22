"""참가 조건 스크리너(F4.3) — 모델·순수 판정·저장 매핑·공개/설정 엔드포인트.

계약: pass_options(어느 답이 통과인지)는 응답자 경로로 절대 새지 않는다. 판정은 서버에서만.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import api.main as main
from api.routers import projects as pm
from api.routers import public as pub
from api.schemas.models import Project, ScreenerQuestion, ScreenerSetIn


# --- 모델 --------------------------------------------------------------------

def test_screener_question_roundtrip():
    q = ScreenerQuestion(id="s1", text="배달앱을 쓰나요?", options=["예", "아니오"], pass_options=["예"])
    dumped = q.model_dump()
    assert dumped == {
        "id": "s1", "text": "배달앱을 쓰나요?", "options": ["예", "아니오"], "pass_options": ["예"],
    }
    assert ScreenerQuestion(**dumped) == q


def test_screener_question_defaults():
    q = ScreenerQuestion(text="질문만")
    assert q.id == "" and q.options == [] and q.pass_options == []


def test_project_screener_defaults_empty():
    assert Project(topic="t").screener == []
    q = ScreenerQuestion(text="q", options=["a"], pass_options=["a"])
    assert Project(topic="t", screener=[q]).screener == [q]


# --- 순수 판정 helper --------------------------------------------------------

def _screener():
    return [
        ScreenerQuestion(id="s1", text="배달앱?", options=["예", "아니오"], pass_options=["예"]),
        ScreenerQuestion(id="s2", text="연령대?", options=["20대", "30대", "40대"], pass_options=["20대", "30대"]),
    ]


def test_qualifies_empty_screener_true():
    # 게이트가 없으면 누구나 통과
    assert pub.screener_qualifies([], {}) is True
    assert pub.screener_qualifies([], {"s1": "예"}) is True


def test_qualifies_all_in_pass_options_true():
    assert pub.screener_qualifies(_screener(), {"s1": "예", "s2": "30대"}) is True


def test_qualifies_one_wrong_false():
    assert pub.screener_qualifies(_screener(), {"s1": "예", "s2": "40대"}) is False


def test_qualifies_missing_answer_false():
    # 한 문항 미응답 → 탈락(모든 문항이 pass 여야 함)
    assert pub.screener_qualifies(_screener(), {"s1": "예"}) is False
    assert pub.screener_qualifies(_screener(), {}) is False


# --- 저장 매핑 (store._project 회귀) -----------------------------------------

def test_store_project_maps_screener():
    from api.services import store

    row = SimpleNamespace(
        id="p_1", owner="anonymous", title="t", topic="주제", target="",
        motivation="", utilization="", material_text="", discord_webhook_url="",
        screener=[{"id": "s1", "text": "q", "options": ["a", "b"], "pass_options": ["a"]}],
        blocklist=[], status="draft", created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    p = store._project(row, 0, 0)
    assert p.screener == [ScreenerQuestion(id="s1", text="q", options=["a", "b"], pass_options=["a"])]


def test_store_project_maps_screener_empty():
    from api.services import store

    row = SimpleNamespace(
        id="p_1", owner="anonymous", title="t", topic="주제", target="",
        motivation="", utilization="", material_text="", discord_webhook_url="",
        screener=None, blocklist=None, status="draft", created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    assert store._project(row, 0, 0).screener == []


# --- 공개 스크리너 노출: pass_options 유출 금지 -----------------------------

def test_public_screener_strips_pass_options():
    stripped = pub._public_screener(_screener())
    assert stripped == [
        {"id": "s1", "text": "배달앱?", "options": ["예", "아니오"]},
        {"id": "s2", "text": "연령대?", "options": ["20대", "30대", "40대"]},
    ]
    # 어느 키에도 pass_options 가 없어야 한다
    assert all("pass_options" not in item for item in stripped)


# --- 엔드포인트 (TestClient) -------------------------------------------------

def _deployed(pid="p_1", screener=None):
    return Project(id=pid, topic="주제", title="제목", status="deployed", screener=screener or [])


def test_public_project_includes_screener_without_pass_options(monkeypatch):
    monkeypatch.setattr(pub.store, "get_project", lambda pid: _deployed(pid, _screener()))
    resp = TestClient(main.app).get("/api/public/projects/p_1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "p_1"
    assert body["screener"] == [
        {"id": "s1", "text": "배달앱?", "options": ["예", "아니오"]},
        {"id": "s2", "text": "연령대?", "options": ["20대", "30대", "40대"]},
    ]
    # 계약: 통과 조건은 응답자에게 절대 새지 않는다
    assert "pass_options" not in resp.text


def test_screen_endpoint_qualified(monkeypatch):
    monkeypatch.setattr(pub.store, "get_project", lambda pid: _deployed(pid, _screener()))
    resp = TestClient(main.app).post(
        "/api/public/projects/p_1/screen", json={"answers": {"s1": "예", "s2": "20대"}}
    )
    assert resp.status_code == 200 and resp.json() == {"qualified": True}


def test_screen_endpoint_disqualified(monkeypatch):
    monkeypatch.setattr(pub.store, "get_project", lambda pid: _deployed(pid, _screener()))
    resp = TestClient(main.app).post(
        "/api/public/projects/p_1/screen", json={"answers": {"s1": "아니오", "s2": "20대"}}
    )
    assert resp.status_code == 200 and resp.json() == {"qualified": False}


def test_screen_endpoint_404_when_missing(monkeypatch):
    monkeypatch.setattr(pub.store, "get_project", lambda pid: None)
    resp = TestClient(main.app).post(
        "/api/public/projects/nope/screen", json={"answers": {}}
    )
    assert resp.status_code == 404


def test_screen_endpoint_403_when_not_deployed(monkeypatch):
    monkeypatch.setattr(pub.store, "get_project", lambda pid: Project(id=pid, topic="t", status="draft"))
    resp = TestClient(main.app).post(
        "/api/public/projects/p_1/screen", json={"answers": {}}
    )
    assert resp.status_code == 403


# --- 의뢰자 설정 엔드포인트 --------------------------------------------------

def test_screener_routes_registered():
    paths = {r.path for r in main.app.routes if hasattr(r, "path")}
    assert "/api/projects/{pid}/screener" in paths
    assert "/api/public/projects/{pid}/screen" in paths


def test_set_screener_updates_via_store(monkeypatch):
    updates = {}
    monkeypatch.setattr(pm.store, "get_project", lambda pid: _deployed(pid))
    monkeypatch.setattr(pm.store, "update_project", lambda pid, patch: updates.update(patch))

    body = ScreenerSetIn(screener=[ScreenerQuestion(id="s1", text="q", options=["a", "b"], pass_options=["a"])])
    pm.set_screener("p_1", body)
    assert updates == {
        "screener": [{"id": "s1", "text": "q", "options": ["a", "b"], "pass_options": ["a"]}]
    }
