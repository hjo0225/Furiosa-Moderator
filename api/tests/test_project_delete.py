"""프로젝트 삭제 (C-6) — 되돌릴 수 없는 파괴적 작업이라 계약을 테스트로 못박는다.

DB 는 monkeypatch 한다(test_material_endpoint.py 패턴). 실제 CASCADE 동작은 DB 스키마
(ForeignKey ondelete="CASCADE")가 보장하므로 여기서는 라우터 계약만 본다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.schemas.models import Project
from api.services import store as store_mod

PID = "p_del"


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:
        yield c


def test_delete_route_registered():
    routes = {(r.path, m) for r in main.app.routes if hasattr(r, "path") for m in (r.methods or [])}
    assert ("/api/projects/{pid}", "DELETE") in routes


@pytest.fixture()
def existing_project(monkeypatch):
    """존재하는 프로젝트 + 세션 카운트. 개별 테스트가 필요한 것만 덮어쓴다."""
    monkeypatch.setattr(store_mod, "get_project", lambda pid: Project(id=pid, topic="주제"))
    monkeypatch.setattr(store_mod, "count_sessions", lambda pid: 0)


def test_delete_removes_project(client, monkeypatch, existing_project):
    called: list[str] = []
    monkeypatch.setattr(store_mod, "delete_project", lambda pid: called.append(pid) or True)

    r = client.delete(f"/api/projects/{PID}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    assert called == [PID]


def test_delete_unknown_project_is_404(client, monkeypatch):
    monkeypatch.setattr(store_mod, "get_project", lambda pid: None)
    # 없는 프로젝트를 지웠다고 200 을 주면 "지워졌다"는 거짓 확인을 주게 된다.
    assert client.delete("/api/projects/nope").status_code == 404


def test_delete_is_idempotent_after_row_vanishes(client, monkeypatch, existing_project):
    """존재 확인과 실제 삭제 사이에 다른 요청이 먼저 지웠어도 500 이 아니라 200 이어야 한다.

    더블클릭·재시도가 실패로 보이면 안 된다 — 원하는 최종 상태(없음)는 이미 달성됐다.
    """
    monkeypatch.setattr(store_mod, "delete_project", lambda pid: False)   # 이미 사라짐

    r = client.delete(f"/api/projects/{PID}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True


def test_delete_reports_what_was_removed(client, monkeypatch, existing_project):
    """무엇이 함께 지워졌는지 돌려준다 — 응답자 데이터가 사라지는 작업이라 흔적을 남긴다."""
    monkeypatch.setattr(store_mod, "delete_project", lambda pid: True)
    monkeypatch.setattr(store_mod, "count_sessions", lambda pid: 7)

    body = client.delete(f"/api/projects/{PID}").json()
    assert body["project_id"] == PID
    assert body["sessions"] == 7
