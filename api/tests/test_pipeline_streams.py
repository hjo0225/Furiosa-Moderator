"""무거운 작업의 SSE 스트림 — 선언/방출 일치 · drain 동치 · 실패 · skip.

DB 와 LLM 은 전부 monkeypatch 한다(test_material_endpoint.py 패턴). 네트워크도
데이터베이스도 타지 않는다 — 로컬에 DATABASE_URL 이 없어도 돌아야 한다.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.routers import projects as pm
from api.schemas.models import GuideQuestion, InterviewGuide, Project
from api.services import store as store_mod
from api.services.llm_client import LLMError, Usage

PID = "p_1"


def _events(body: str) -> list[dict]:
    """SSE 응답 본문 → 이벤트 리스트."""
    return [
        json.loads(line[len("data: "):])
        for line in body.split("\n\n")
        if line.startswith("data: ")
    ]


@pytest.fixture()
def client():
    # 컨텍스트 매니저로 써야 anyio 포털이 테스트 끝에 결정론으로 닫힌다. 그냥 만들어 두면
    # Windows 에서 이벤트 루프가 나중에 GC 될 때 OSError(WinError 10014)가 나고, pytest 가
    # 그 unraisable 예외를 "그때 돌던 다른 테스트"의 실패로 붙여 버린다(스트림 테스트에서 재현).
    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def project(monkeypatch):
    p = Project(id=PID, topic="아침 결식", target="20대 직장인",
                motivation="신제품", utilization="컨셉 방향")
    monkeypatch.setattr(store_mod, "get_project", lambda pid: p)
    return p


@pytest.fixture()
def guide_deps(monkeypatch):
    """가이드 생성이 건드리는 store/외부 호출을 전부 목킹한다."""
    monkeypatch.setattr(store_mod, "get_slot_summaries", lambda pid: {})
    monkeypatch.setattr(store_mod, "has_materials", lambda pid: False)
    monkeypatch.setattr(store_mod, "save_guide", lambda pid, g: g)
    monkeypatch.setattr(pm, "collect_personas", lambda p: "")


@pytest.fixture()
def fake_guide_llm(monkeypatch):
    """가이드 생성 LLM 을 결정론 목으로 바꾼다."""
    guide = InterviewGuide(
        goal="왜 거르는가",
        questions=[
            GuideQuestion(id="q1", text="아침을 거르시나요?", goal="현상 확인", order=0,
                          response_buckets=[])
        ],
    )

    class _FakeLLM:
        def structured(self, *a, **k):
            return guide, Usage("furiosa-ai/Qwen3-32B-FP8", 120, 340)

    monkeypatch.setattr(pm, "get_llm", lambda: _FakeLLM())
    return guide


@pytest.fixture()
def boom_llm(monkeypatch):
    class _BoomLLM:
        def structured(self, *a, **k):
            raise LLMError("NPU 응답 없음")

    monkeypatch.setattr(pm, "get_llm", lambda: _BoomLLM())


# ── 가이드 ───────────────────────────────────────────────────────
def test_guide_stream_declares_then_emits_only_declared_steps(
    client, project, guide_deps, fake_guide_llm
):
    r = client.post(f"/api/projects/{PID}/guide/stream", json={})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    evs = _events(r.text)

    assert "steps" in evs[0], "첫 이벤트는 단계 선언이어야 한다"
    declared = {s["key"] for s in evs[0]["steps"]}
    emitted = {e["step"] for e in evs if "step" in e}
    assert emitted <= declared, f"선언에 없는 단계가 방출됨: {emitted - declared}"
    assert declared == emitted, f"선언했지만 방출되지 않은 단계: {declared - emitted}"


def test_guide_stream_last_event_is_result(client, project, guide_deps, fake_guide_llm):
    evs = _events(client.post(f"/api/projects/{PID}/guide/stream", json={}).text)
    assert "result" in evs[-1]
    assert evs[-1]["result"]["goal"] == "왜 거르는가"


def test_guide_stream_llm_step_carries_measured_usage(
    client, project, guide_deps, fake_guide_llm
):
    evs = _events(client.post(f"/api/projects/{PID}/guide/stream", json={}).text)
    llm_done = next(e for e in evs if e.get("step") == "llm" and e["status"] == "done")
    assert llm_done["detail"]["model"] == "furiosa-ai/Qwen3-32B-FP8"
    assert llm_done["detail"]["tokens"] == 340        # Usage.tokens_out 실측
    assert llm_done["ms"] >= 0


def test_guide_stream_skips_evidence_without_materials(
    client, project, guide_deps, fake_guide_llm
):
    # 자료가 없으면 RAG 검색을 통째로 건너뛴다. "완료"로 위장하지 않는다.
    evs = _events(client.post(f"/api/projects/{PID}/guide/stream", json={}).text)
    ev = next(e for e in evs if e.get("step") == "evidence" and e["status"] in ("done", "skip"))
    assert ev["status"] == "skip"


def test_guide_nonstream_matches_stream_result(client, project, guide_deps, fake_guide_llm):
    """두 겹 노출의 핵심 보증 — drain 경로가 스트림의 result 와 같아야 한다."""
    streamed = _events(client.post(f"/api/projects/{PID}/guide/stream", json={}).text)[-1]["result"]
    plain = client.post(f"/api/projects/{PID}/guide", json={})
    assert plain.status_code == 200
    assert plain.json()["goal"] == streamed["goal"]
    assert len(plain.json()["questions"]) == len(streamed["questions"])


def test_guide_stream_emits_error_event_on_llm_failure(client, project, guide_deps, boom_llm):
    evs = _events(client.post(f"/api/projects/{PID}/guide/stream", json={}).text)
    err = next(e for e in evs if e.get("status") == "error")
    assert "가이드 생성에 실패했습니다" in err["error"]
    assert err["status_code"] == 502


def test_guide_nonstream_still_raises_502_on_llm_failure(client, project, guide_deps, boom_llm):
    """기존 계약 회귀 — 비스트림은 지금과 똑같이 502 로 떨어져야 한다."""
    assert client.post(f"/api/projects/{PID}/guide", json={}).status_code == 502


def test_guide_stream_404_before_stream_starts(client, monkeypatch, guide_deps, fake_guide_llm):
    # 없는 프로젝트는 SSE 200 + 인밴드 에러가 아니라 진짜 404 여야 한다.
    monkeypatch.setattr(store_mod, "get_project", lambda pid: None)
    assert client.post("/api/projects/nope/guide/stream", json={}).status_code == 404
