"""지식팩 안전(F1.5) — read-only·발화금지 규칙 주입 + 금칙어(blocklist).

계약: 팩(브리핑)은 '읽기 전용·발화 금지'다. 진행자는 이 자료로 참가자의 말을 '이해'만 하고
팩의 내용을 참가자에게 말하거나 정정하지 않는다. 금칙어는 진행자가 먼저 꺼내면 안 되는 주제다.

주의(Phase 7): 여기서 검증하는 건 프롬프트 조립·배선뿐이다. NPU 모더레이터가 실제로 팩
사실을 누설하지 않는지(누설률)는 사람이 라이브로 확인해야 한다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import api.main as main
from api.interview.prompts import generate_user
from api.interview.state import init_ledger
from api.routers import projects as pm
from api.schemas.models import BlocklistSetIn, Project

GUIDE = {"goal": "배달앱 전환 요인", "questions": [
    {"id": "q1", "text": "어떤 앱을 쓰세요?", "goal": "현재 앱"},
    {"id": "q2", "text": "갈아탄 계기는?", "goal": "트리거"},
]}


# --- 모델 --------------------------------------------------------------------

def test_project_blocklist_defaults_empty():
    assert Project(topic="t").blocklist == []
    assert Project(topic="t", blocklist=["가격 정책 변경"]).blocklist == ["가격 정책 변경"]


def test_store_project_maps_blocklist():
    from api.services import store

    row = SimpleNamespace(
        id="p_1", owner="anonymous", title="t", topic="주제", target="",
        motivation="", utilization="", material_text="", discord_webhook_url="",
        screener=[], blocklist=["경쟁사 프로모션", "가격 정책 변경"],
        status="draft", created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    p = store._project(row, 0, 0)
    assert p.blocklist == ["경쟁사 프로모션", "가격 정책 변경"]


def test_store_project_maps_blocklist_none():
    from api.services import store

    row = SimpleNamespace(
        id="p_1", owner="anonymous", title="t", topic="주제", target="",
        motivation="", utilization="", material_text="", discord_webhook_url="",
        screener=None, blocklist=None,
        status="draft", created_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )
    assert store._project(row, 0, 0).blocklist == []


# --- 프롬프트: 읽기 전용·발화 금지 규칙 주입 --------------------------------

def test_generate_user_brief_carries_read_only_never_speak_rules():
    led = init_ledger(GUIDE)
    u = generate_user(
        "probe", "q1", "심화", "", GUIDE, [], led,
        brief_notes=[{"text": "배민클럽은 구독형 무료배달", "source": "의뢰자 자료.pdf"}],
    )
    # 팩 내용(노트·출처)은 실린다
    assert "배민클럽은 구독형 무료배달" in u and "의뢰자 자료.pdf" in u
    # F1.5.6 규칙이 verbatim(정신) 으로 실린다
    assert "읽기 전용" in u          # 팩은 read-only
    assert "말하지" in u             # never speak
    assert "정정" in u               # 참가자를 바로잡지 않는다
    assert "되물" in u               # 없는 건 추측 말고 되묻는다(clarifying probe)
    # 기존 중립성(유도 금지) 문구는 유지된다 (하위호환)
    assert "유도하는 데 쓰지 마세요" in u


def test_generate_user_omits_brief_block_when_empty():
    led = init_ledger(GUIDE)
    u = generate_user("probe", "q1", "심화", "", GUIDE, [], led)
    assert "읽기 전용" not in u and "참조 자료" not in u


# --- 프롬프트: 금칙어(blocklist) --------------------------------------------

def test_generate_user_injects_blocklist():
    led = init_ledger(GUIDE)
    u = generate_user(
        "advance", "q2", "", "", GUIDE, [], led,
        blocklist=["가격 정책 변경", "경쟁사 프로모션"],
    )
    assert "절대 언급 금지" in u
    assert "가격 정책 변경" in u and "경쟁사 프로모션" in u
    assert "먼저 꺼내지 마세요" in u


def test_generate_user_omits_blocklist_block_when_empty():
    led = init_ledger(GUIDE)
    u = generate_user("advance", "q2", "", "", GUIDE, [], led, blocklist=[])
    assert "절대 언급 금지" not in u


# --- 엔드포인트 (TestClient) -------------------------------------------------

def _project(pid="p_1", blocklist=None):
    return Project(id=pid, topic="주제", title="제목", status="draft", blocklist=blocklist or [])


def test_blocklist_route_registered():
    paths = {r.path for r in main.app.routes if hasattr(r, "path")}
    assert "/api/projects/{pid}/blocklist" in paths


def test_set_blocklist_strips_and_updates_via_store(monkeypatch):
    updates: dict = {}
    monkeypatch.setattr(pm.store, "get_project", lambda pid: _project(pid, ["기존"]))
    monkeypatch.setattr(pm.store, "update_project", lambda pid, patch: updates.update(patch))

    # 빈 문자열·공백만·앞뒤 공백 항목은 버리고 트림한다
    pm.set_blocklist("p_1", BlocklistSetIn(blocklist=["  가격 정책 변경 ", "", "   ", "경쟁사"]))
    assert updates == {"blocklist": ["가격 정책 변경", "경쟁사"]}


def test_set_blocklist_endpoint_via_testclient(monkeypatch):
    saved: dict = {}

    def _get(pid):
        return _project(pid, saved.get("blocklist", []))

    monkeypatch.setattr(pm.store, "get_project", _get)
    monkeypatch.setattr(pm.store, "update_project", lambda pid, patch: saved.update(patch))

    resp = TestClient(main.app).put(
        "/api/projects/p_1/blocklist", json={"blocklist": ["가격 정책 변경", "  "]}
    )
    assert resp.status_code == 200
    assert resp.json()["blocklist"] == ["가격 정책 변경"]


def test_set_blocklist_404_when_missing(monkeypatch):
    monkeypatch.setattr(pm.store, "get_project", lambda pid: None)
    resp = TestClient(main.app).put("/api/projects/nope/blocklist", json={"blocklist": []})
    assert resp.status_code == 404
