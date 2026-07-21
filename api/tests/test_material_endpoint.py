"""업로드 엔드포인트 + 가이드 생성이 자료를 주입하는지 (DB/LLM 은 monkeypatch)."""
from __future__ import annotations

from fastapi.testclient import TestClient

import api.main as main
from api.routers import projects as projects_mod
from api.schemas.models import GuideQuestion, InterviewGuide, Project
from api.services import store as store_mod
from api.services.llm_client import LLMError


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
    assert body["summarized"] is False  # 짧은 자료는 요약하지 않는다(LLM 호출 없음)
    assert "배민클럽" in saved["material_text"]


def test_upload_material_summarizes_long(monkeypatch):
    """SUMMARIZE_THRESHOLD 초과 → LLM 요약본을 저장하고 summarized=True."""
    saved: dict = {}

    class FakeLLM:
        def text(self, system, user, **kw):
            return ("요약된 도메인 핵심", None)

    monkeypatch.setattr(store_mod, "get_project", lambda pid: Project(id=pid, topic="주제"))
    monkeypatch.setattr(store_mod, "update_project", lambda pid, patch: saved.update(patch))
    monkeypatch.setattr(projects_mod, "get_llm", lambda: FakeLLM())
    long_text = ("가" * 9000).encode("utf-8")  # 9000자 > 8000 임계값
    client = TestClient(main.app)
    resp = client.post(
        "/api/projects/p_1/material",
        files={"file": ("brief.txt", long_text, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summarized"] is True
    assert body["truncated"] is False
    assert saved["material_text"] == "요약된 도메인 핵심"


def test_upload_material_summary_fallback_on_llm_error(monkeypatch):
    """요약 LLM 이 죽어도 업로드는 성공 — cap() 자르기로 후퇴, summarized=False·truncated=True."""
    saved: dict = {}

    class FakeLLM:
        def text(self, system, user, **kw):
            raise LLMError("요약 서버 다운")

    monkeypatch.setattr(store_mod, "get_project", lambda pid: Project(id=pid, topic="주제"))
    monkeypatch.setattr(store_mod, "update_project", lambda pid, patch: saved.update(patch))
    monkeypatch.setattr(projects_mod, "get_llm", lambda: FakeLLM())
    long_text = ("가" * 9000).encode("utf-8")
    client = TestClient(main.app)
    resp = client.post(
        "/api/projects/p_1/material",
        files={"file": ("brief.txt", long_text, "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summarized"] is False
    assert body["truncated"] is True
    assert body["chars"] == 8000  # cap() 상한
    assert saved["material_text"] == "가" * 8000


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
