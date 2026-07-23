"""무거운 작업의 진행 이벤트 — 선언/방출 일치 · drain 동치 · 실패 · skip.

DB 와 LLM 은 전부 monkeypatch 한다(test_material_endpoint.py 패턴). 네트워크도
데이터베이스도 타지 않는다 — 로컬에 DATABASE_URL 이 없어도 돌아야 한다.

**단계 검증은 제너레이터를 직접 돌린다.** TestClient 로 SSE 를 태우면 Windows 에서
이벤트 루프가 GC 될 때 OSError(WinError 10014)가 나고 pytest 가 그 unraisable 예외를
그때 돌던 아무 테스트에나 붙여 버린다(스위트가 무작위로 빨개진다). 제너레이터는 순수
이터레이터라 그 문제가 없고, 검증하려는 계약은 전부 거기 있다. HTTP 는 배선(라우트
등록·상태코드·비스트림 동치)만 확인한다 — SSE 프레이밍 자체는 test_progress.py 가 맡는다.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.routers import projects as pm
from api.schemas.models import (
    GuideGenerateIn,
    GuideQuestion,
    InterviewGuide,
    Project,
    Session,
    Turn,
)
from api.services import store as store_mod
from api.services.llm_client import LLMError, Usage

PID = "p_1"


def _steps_of(events: list[dict]) -> tuple[set[str], set[str]]:
    """(선언된 키, 실제 방출된 키)."""
    declared = {s["key"] for s in events[0]["steps"]}
    emitted = {e["step"] for e in events if "step" in e}
    return declared, emitted


@pytest.fixture()
def project(monkeypatch):
    p = Project(id=PID, topic="아침 결식", target="20대 직장인",
                motivation="신제품", utilization="컨셉 방향")
    monkeypatch.setattr(store_mod, "get_project", lambda pid: p)
    return p


# ── 가이드 ───────────────────────────────────────────────────────
@pytest.fixture()
def guide_deps(monkeypatch):
    """가이드 생성이 건드리는 store/외부 호출을 전부 목킹한다."""
    monkeypatch.setattr(store_mod, "get_slot_summaries", lambda pid: {})
    monkeypatch.setattr(store_mod, "has_materials", lambda pid: False)
    monkeypatch.setattr(store_mod, "save_guide", lambda pid, g: g)
    monkeypatch.setattr(pm, "collect_personas", lambda p: "")


@pytest.fixture()
def fake_guide_llm(monkeypatch):
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
def boom_guide_llm(monkeypatch):
    class _BoomLLM:
        def structured(self, *a, **k):
            raise LLMError("NPU 응답 없음")

    monkeypatch.setattr(pm, "get_llm", lambda: _BoomLLM())


def _guide_events(project) -> list[dict]:
    return list(pm.run_guide(project, GuideGenerateIn()))


def test_guide_declares_then_emits_exactly_the_declared_steps(
    project, guide_deps, fake_guide_llm
):
    evs = _guide_events(project)
    assert "steps" in evs[0], "첫 이벤트는 단계 선언이어야 한다"
    declared, emitted = _steps_of(evs)
    assert emitted <= declared, f"선언에 없는 단계가 방출됨: {emitted - declared}"
    assert declared == emitted, f"선언했지만 방출되지 않은 단계: {declared - emitted}"


def test_guide_last_event_is_result(project, guide_deps, fake_guide_llm):
    evs = _guide_events(project)
    assert "result" in evs[-1]
    assert evs[-1]["result"]["goal"] == "왜 거르는가"


def test_guide_result_is_json_serialisable(project, guide_deps, fake_guide_llm):
    # datetime 이 객체로 남으면 SSE 직렬화에서 터진다 — mode="json" 회귀 가드.
    import json

    json.dumps(_guide_events(project)[-1]["result"], ensure_ascii=False)


def test_guide_llm_step_carries_measured_usage(project, guide_deps, fake_guide_llm):
    evs = _guide_events(project)
    llm_done = next(e for e in evs if e.get("step") == "llm" and e["status"] == "done")
    assert llm_done["detail"]["model"] == "furiosa-ai/Qwen3-32B-FP8"
    assert llm_done["detail"]["tokens"] == 340        # Usage.tokens_out 실측
    assert llm_done["ms"] >= 0


def test_guide_omits_usage_detail_when_unmeasured(project, guide_deps, monkeypatch):
    """실측이 없으면 추정치를 채우지 않고 키 자체를 뺀다 → 화면은 '—'."""
    guide = InterviewGuide(goal="g", questions=[])

    class _NoUsageLLM:
        def structured(self, *a, **k):
            return guide, None

    monkeypatch.setattr(pm, "get_llm", lambda: _NoUsageLLM())
    evs = _guide_events(project)
    llm_done = next(e for e in evs if e.get("step") == "llm" and e["status"] == "done")
    assert "tokens" not in llm_done.get("detail", {})
    assert "model" not in llm_done.get("detail", {})


def test_guide_skips_evidence_without_materials(project, guide_deps, fake_guide_llm):
    # 자료가 없으면 RAG 검색을 통째로 건너뛴다. "완료"로 위장하지 않는다.
    evs = _guide_events(project)
    # start 는 항상 먼저 나온다 — 종결 이벤트(done/skip)를 봐야 한다.
    ev = next(e for e in evs if e.get("step") == "evidence" and e["status"] in ("done", "skip"))
    assert ev["status"] == "skip"
    assert ev["detail"]["reason"] == "참고 자료 없음"


def test_guide_emits_error_event_and_stops_on_llm_failure(project, guide_deps, boom_guide_llm):
    evs = _guide_events(project)
    err = next(e for e in evs if e.get("status") == "error")
    assert "가이드 생성에 실패했습니다" in err["error"]
    assert err["status_code"] == 502
    assert not any("result" in e for e in evs), "실패했는데 result 를 내면 안 된다"


# ── 인사이트 ──────────────────────────────────────────────────────
@pytest.fixture()
def two_completed_sessions(monkeypatch):
    """완료 세션 2건을 요약 없이 심는다 — summarize 단계가 LLM 을 2번 타게."""
    sessions = [
        Session(id=f"s{i}", project_id=PID, status="completed", asked=3) for i in (1, 2)
    ]
    turns = {
        "s1": [Turn(session_id="s1", role="respondent", text="시간이 없어서요")],
        "s2": [Turn(session_id="s2", role="respondent", text="입맛이 없어요")],
    }
    monkeypatch.setattr(store_mod, "get_guide", lambda pid: None)
    monkeypatch.setattr(store_mod, "list_sessions", lambda pid: sessions)
    monkeypatch.setattr(store_mod, "list_turns", lambda pid, sid: turns.get(sid, []))
    monkeypatch.setattr(store_mod, "update_session", lambda pid, sid, patch: None)
    monkeypatch.setattr(store_mod, "sentiment_counts", lambda pid: {"positive": 1, "negative": 1})
    monkeypatch.setattr(store_mod, "theme_mention_counts", lambda pid, kw: {})
    monkeypatch.setattr(store_mod, "bucket_distribution", lambda pid: {})
    monkeypatch.setattr(store_mod, "save_insight", lambda pid, ins: ins)
    return sessions


@pytest.fixture()
def fake_insight_llm(monkeypatch):
    class _FakeLLM:
        def text(self, *a, **k):
            return "요약본", Usage("furiosa-ai/Qwen3-32B-FP8", 90, 40)

        def structured(self, system, user, schema, **k):
            return schema(overall="전체 요약"), Usage("furiosa-ai/Qwen3-32B-FP8", 200, 500)

    monkeypatch.setattr(pm, "get_llm", lambda: _FakeLLM())


def _insight_events(project, sessions) -> list[dict]:
    return list(pm.run_insight(project, sessions))


def test_insight_reports_session_progress(project, two_completed_sessions, fake_insight_llm):
    evs = _insight_events(project, two_completed_sessions)
    prog = [e for e in evs if e.get("step") == "summarize" and e.get("detail", {}).get("total")]
    assert prog, "세션 요약은 done/total 진행을 보고해야 한다"
    assert prog[-1]["detail"]["done"] == 2
    assert prog[-1]["detail"]["total"] == 2


def test_insight_counts_step_is_labelled_db_measured(
    project, two_completed_sessions, fake_insight_llm
):
    """AGENTS.md §0.1 계약 1 — 집계는 LLM 이 아니라 DB 가 센다. 화면에 그렇게 드러난다."""
    evs = _insight_events(project, two_completed_sessions)
    counts_decl = next(s for s in evs[0]["steps"] if s["key"] == "counts")
    assert "DB" in counts_decl["label"]
    done = next(e for e in evs if e.get("step") == "counts" and e["status"] == "done")
    assert done["detail"]["source"] == "db-group-by"


def test_insight_declares_and_emits_same_steps(
    project, two_completed_sessions, fake_insight_llm
):
    declared, emitted = _steps_of(_insight_events(project, two_completed_sessions))
    assert declared == emitted, f"선언/방출 불일치: {declared ^ emitted}"


def test_insight_result_is_json_serialisable(
    project, two_completed_sessions, fake_insight_llm
):
    import json

    evs = _insight_events(project, two_completed_sessions)
    json.dumps(evs[-1]["result"], ensure_ascii=False)


# ── HTTP 배선 (스트리밍 본문을 태우지 않는 것만) ──────────────────
def test_stream_routes_are_registered():
    paths = {r.path for r in main.app.routes if hasattr(r, "path")}
    for p in ("/api/projects/{pid}/guide/stream", "/api/projects/{pid}/insight/stream"):
        assert p in paths, f"{p} 라우트가 없다"


def test_guide_nonstream_matches_generator_result(project, guide_deps, fake_guide_llm):
    """두 겹 노출의 핵심 보증 — drain 경로가 제너레이터의 result 와 같아야 한다."""
    expected = _guide_events(project)[-1]["result"]
    with TestClient(main.app) as c:
        plain = c.post(f"/api/projects/{PID}/guide", json={})
    assert plain.status_code == 200
    assert plain.json()["goal"] == expected["goal"]
    assert len(plain.json()["questions"]) == len(expected["questions"])


def test_guide_nonstream_still_raises_502_on_llm_failure(project, guide_deps, boom_guide_llm):
    """기존 계약 회귀 — 비스트림은 지금과 똑같이 502 로 떨어져야 한다."""
    with TestClient(main.app) as c:
        assert c.post(f"/api/projects/{PID}/guide", json={}).status_code == 502


def test_guide_stream_404_before_stream_starts(monkeypatch, guide_deps, fake_guide_llm):
    # 없는 프로젝트는 SSE 200 + 인밴드 에러가 아니라 진짜 404 여야 한다.
    monkeypatch.setattr(store_mod, "get_project", lambda pid: None)
    with TestClient(main.app) as c:
        assert c.post("/api/projects/nope/guide/stream", json={}).status_code == 404


def test_insight_stream_400_before_stream_starts(project, monkeypatch):
    monkeypatch.setattr(store_mod, "list_sessions", lambda pid: [])
    with TestClient(main.app) as c:
        assert c.post(f"/api/projects/{PID}/insight/stream").status_code == 400


def test_insight_nonstream_matches_generator_result(
    project, two_completed_sessions, fake_insight_llm
):
    expected = _insight_events(project, two_completed_sessions)[-1]["result"]
    with TestClient(main.app) as c:
        plain = c.post(f"/api/projects/{PID}/insight")
    assert plain.status_code == 200
    assert plain.json()["overall"] == expected["overall"]
    assert plain.json()["session_count"] == expected["session_count"]
