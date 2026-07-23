"""RAG-7 — 가이드 생성에 [대상 청중](페르소나 표본) 주입.

프롬프트 레벨(주입/회귀) + collect_personas(무동작 단락·조건 추출·검색·포맷·실패흡수) +
엔드포인트 배선([대상 청중]이 실제 LLM user 프롬프트로 흘러가는지) + has_knowledge.

collect_personas 는 페르소나 풀(has_knowledge/search_knowledge)을 로컬 임포트하므로
그 스파이는 api.briefing.pipeline(=bp)에 건다. get_llm 은 audience 모듈이 top-level
로 들고 있어 api.services.audience(=aud)에 건다. 라우터 배선은 import 지점(pm)에 건다.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import api.briefing.pipeline as bp
import api.main as main
import api.services.audience as aud
from api.prompts.guide import guide_user
from api.routers import projects as pm
from api.services.audience import AudienceSpec, collect_personas
from api.services.llm_client import LLMError
from api.schemas.models import GuideQuestion, InterviewGuide, Project


# ── 프롬프트 레벨 ────────────────────────────────────────────────
def test_guide_user_injects_audience():
    out = guide_user(topic="x", audience="- 페르소나1")
    assert "[대상 청중]" in out
    assert "- 페르소나1" in out


def test_guide_user_no_audience_regression():
    # 회귀 불변식: audience 없음/빈 문자열은 바이트 동일 + 청중 블록 없음.
    without = guide_user("x", "y", "mat", "mot", "util")
    empty = guide_user("x", "y", "mat", "mot", "util", audience="")
    assert without == empty
    assert "[대상 청중]" not in without
    assert "[대상 청중]" not in empty


# ── collect_personas ────────────────────────────────────────────
class _FakeLLM:
    """get_llm() 대체 — structured 가 지정 spec 을 돌려준다."""

    def __init__(self, spec):
        self._spec = spec

    def structured(self, system, user, schema, **kw):
        return self._spec, None


def test_collect_personas_noop_when_corpus_empty(monkeypatch):
    # 코퍼스가 비면 LLM·검색 호출 없이 즉시 "" — 운영 현재의 무동작 경로.
    llm_calls: list[int] = []
    search_calls: list[int] = []
    monkeypatch.setattr(bp, "has_knowledge", lambda corpus: False)
    monkeypatch.setattr(aud, "get_llm", lambda: llm_calls.append(1) or _FakeLLM(AudienceSpec()))
    monkeypatch.setattr(bp, "search_knowledge", lambda *a, **k: search_calls.append(1) or [])
    p = Project(id="p1", topic="주제", target="20대", motivation="동기", utilization="활용")

    assert collect_personas(p) == ""
    assert llm_calls == []          # 추출 LLM 호출 자체가 없다
    assert search_calls == []       # 임베딩·검색 호출 자체가 없다


def test_collect_personas_happy_path(monkeypatch):
    monkeypatch.setattr(bp, "has_knowledge", lambda corpus: True)
    spec = AudienceSpec(age_min=20, age_max=29, sex="남자",
                        keywords=["술", "음주"], query="술을 기피하는 20대 남성")
    monkeypatch.setattr(aud, "get_llm", lambda: _FakeLLM(spec))

    captured: dict = {}

    def fake_search(query, corpus=None, k=5, *, meta_filters=None, keywords=None, candidates=30):
        captured.update(query=query, corpus=corpus, k=k, meta_filters=meta_filters,
                        keywords=keywords, candidates=candidates)
        return [
            {"title": "20대 남성, 술을 거의 안 마심", "text": "본문A", "meta": {}, "score": 0.9},
            {"title": "회식 자리를 부담스러워하는 직장인", "text": "본문B", "meta": {}, "score": 0.8},
        ]

    monkeypatch.setattr(bp, "search_knowledge", fake_search)
    p = Project(id="p1", topic="술 소비", target="20대 남성", motivation="m", utilization="u")

    out = collect_personas(p)

    assert captured["corpus"] == "personas"
    assert captured["k"] == 8
    assert captured["meta_filters"] == {"age": (20, 29), "sex": "남자"}
    assert captured["keywords"] == ["술", "음주"]
    assert captured["candidates"] == 20
    assert captured["query"] == "술을 기피하는 20대 남성"
    # title 요약을 불릿으로
    assert out == "- 20대 남성, 술을 거의 안 마심\n- 회식 자리를 부담스러워하는 직장인"


def test_collect_personas_partial_age_fills_open_bound(monkeypatch):
    # age_max 만 오면 하한은 기본 19 로 열어 둔다 → ("age", (19, 29)).
    monkeypatch.setattr(bp, "has_knowledge", lambda corpus: True)
    monkeypatch.setattr(aud, "get_llm", lambda: _FakeLLM(AudienceSpec(age_max=29)))

    captured: dict = {}

    def fake_search(query, corpus=None, k=5, *, meta_filters=None, keywords=None, candidates=30):
        captured["meta_filters"] = meta_filters
        captured["keywords"] = keywords
        return []

    monkeypatch.setattr(bp, "search_knowledge", fake_search)
    p = Project(id="p1", topic="t", target="", motivation="", utilization="")

    collect_personas(p)

    assert captured["meta_filters"] == {"age": (19, 29)}   # 성별 언급 없음 → age 만
    assert captured["keywords"] is None                    # 키워드 없음 → None


def test_collect_personas_extraction_failure_returns_empty(monkeypatch):
    # 추출 LLM 이 LLMError → "" 이고 검색은 호출조차 안 된다.
    monkeypatch.setattr(bp, "has_knowledge", lambda corpus: True)

    class _BoomLLM:
        def structured(self, *a, **k):
            raise LLMError("추출 down")

    monkeypatch.setattr(aud, "get_llm", lambda: _BoomLLM())
    search_calls: list[int] = []
    monkeypatch.setattr(bp, "search_knowledge", lambda *a, **k: search_calls.append(1) or [])
    p = Project(id="p1", topic="t", target="", motivation="", utilization="")

    assert collect_personas(p) == ""
    assert search_calls == []


def test_collect_personas_absorbs_search_failure(monkeypatch):
    # 검색이 터져도 흡수 → "" (가이드 생성을 막지 않는다).
    monkeypatch.setattr(bp, "has_knowledge", lambda corpus: True)
    monkeypatch.setattr(aud, "get_llm", lambda: _FakeLLM(AudienceSpec(query="q")))

    def boom(*a, **k):
        raise RuntimeError("rerank down")

    monkeypatch.setattr(bp, "search_knowledge", boom)
    p = Project(id="p1", topic="t", target="", motivation="", utilization="")

    assert collect_personas(p) == ""


# ── 엔드포인트 배선 ─────────────────────────────────────────────
class _CaptureLLM:
    def __init__(self):
        self.user = ""

    def structured(self, system, user, schema, **kw):
        self.user = user
        return InterviewGuide(
            goal="g", questions=[GuideQuestion(id="q1", text="?", goal="x")]
        ), None


def _wire_endpoint(monkeypatch):
    llm = _CaptureLLM()
    monkeypatch.setattr(pm, "get_llm", lambda: llm)
    monkeypatch.setattr(
        pm.store, "get_project",
        lambda pid: Project(id=pid, topic="주제", target="20대", utilization="온보딩"),
    )
    monkeypatch.setattr(pm.store, "get_slot_summaries", lambda pid: {})   # 자료 요약 없음
    monkeypatch.setattr(pm.store, "save_guide", lambda pid, g: g)
    monkeypatch.setattr(pm.store, "has_materials", lambda pid: False)     # 자료 없음 → evidence "" 로 격리
    return llm


def test_generate_guide_injects_audience(monkeypatch):
    llm = _wire_endpoint(monkeypatch)
    monkeypatch.setattr(pm, "collect_personas", lambda p: "- 김철수 페르소나")
    resp = TestClient(main.app).post("/api/projects/p_1/guide", json={})
    assert resp.status_code == 200
    assert "[대상 청중]" in llm.user
    assert "- 김철수 페르소나" in llm.user


def test_generate_guide_no_audience_is_noop(monkeypatch):
    # collect_personas 가 "" 면 청중 블록이 프롬프트에 없다(무동작 회귀).
    llm = _wire_endpoint(monkeypatch)
    monkeypatch.setattr(pm, "collect_personas", lambda p: "")
    resp = TestClient(main.app).post("/api/projects/p_1/guide", json={})
    assert resp.status_code == 200
    assert "[대상 청중]" not in llm.user


# ── has_knowledge ───────────────────────────────────────────────
class _FirstResult:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _HKSession:
    """db_session() 대체 — execute(stmt).first() 로 row/None 을 돌려주고 stmt 를 붙잡는다."""

    def __init__(self, row):
        self._row = row
        self.captured = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt):
        self.captured = stmt
        return _FirstResult(self._row)


def test_has_knowledge_true_when_row_exists(monkeypatch):
    sess = _HKSession(row=("k_1",))
    monkeypatch.setattr(bp, "db_session", lambda: sess)

    assert bp.has_knowledge("personas") is True
    assert sess.captured.compile().params.get("corpus_1") == "personas"   # WHERE corpus 하드필터


def test_has_knowledge_false_when_empty(monkeypatch):
    sess = _HKSession(row=None)
    monkeypatch.setattr(bp, "db_session", lambda: sess)

    assert bp.has_knowledge("personas") is False
