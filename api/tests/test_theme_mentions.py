"""주제별 mention_count — F3 버그 회귀 방지.

두 갈래를 다룬다:
1) store.theme_mention_counts 단위테스트 — keywords 매칭 / 빈 keywords 폴백(라벨 토큰화) /
   응답자 턴만 대상(모더레이터 턴 제외, DB 쿼리의 role 필터로 보장).
2) build_insight 의 테마 경로 — Qwen3 가 optional 필드(keywords)를 통째로 생략하는 실사고를
   막으려고 keywords 를 필수로 승격한 생성 전용 스키마(_GenInsight/_GenTheme)를 실제로 쓰는지,
   그리고 LLM 이 낸 mention_count 는 버려지고 DB 실측(store.theme_mention_counts)으로
   덮이는지(계약 1)를 검증한다.

db_session 은 test_knowledge.py 의 _FakeSession 패턴과 같은 방식으로 가짜로 바꾼다 — 실제
join/group by/string_agg 실행 결과를 (session_id, transcript) 튜플로 흉내내고, 응답자 턴만
필터한다는 쿼리 자체의 성질은 컴파일된 statement 의 바인드 파라미터로 확인한다.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import api.main as main
from api.routers import projects as pm
from api.schemas.models import Project, Session
from api.services import store


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """db_session() 대체 — (session_id, transcript) 목록을 그대로 돌려주고 statement 를 붙잡아 둔다."""

    def __init__(self, rows):
        self._rows = rows
        self.captured = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, stmt):
        self.captured = stmt
        return _Result(self._rows)


def _wire(monkeypatch, rows):
    sess = _FakeSession(rows)
    monkeypatch.setattr(store, "db_session", lambda: sess)
    return sess


# --- store.theme_mention_counts ---------------------------------------------

def test_theme_mention_counts_matches_populated_keywords(monkeypatch):
    rows = [
        ("s1", "배달비가 너무 비싸요 그래서 쿠폰만 찾아요"),
        ("s2", "저는 그냥 마트에서 장을 봐요"),
    ]
    sess = _wire(monkeypatch, rows)

    out = store.theme_mention_counts("p1", {"배달비 부담": ["배달비", "쿠폰"]})

    assert out == {"배달비 부담": 1}                                    # s1 만 키워드에 걸림
    # 쿼리 자체가 응답자 턴만 대상으로 한다(모더레이터 턴 제외) — WHERE role = respondent
    assert sess.captured.compile().params.get("role_1") == "respondent"


def test_theme_mention_counts_empty_keywords_falls_back_to_tokenized_label(monkeypatch):
    rows = [
        ("s1", "칼로리 신경 안 쓰고 그냥 먹어요"),
        ("s2", "저는 가격만 봐요"),
    ]
    _wire(monkeypatch, rows)

    # keywords 가 비면 라벨을 토큰화(칼로리/기준/중요도, 순수 숫자 '0'은 버림)해
    # 그중 하나라도 걸리면 매칭한다 — 라벨 전체를 통째로 매칭하던 예전 폴백은 항상 0 이었다.
    out = store.theme_mention_counts("p1", {"칼로리 0 기준 중요도": []})

    assert out == {"칼로리 0 기준 중요도": 1}          # s1 만 '칼로리' 포함
    assert list(out.values())[0] != 0                  # 회귀 확인: 예전엔 항상 0


def test_theme_mention_counts_tokenized_fallback_does_not_match_unrelated_turn(monkeypatch):
    """서술형 라벨을 통째로 매칭하던 예전 버그의 대조군 — 무관한 응답에는 안 걸려야 한다."""
    rows = [("s1", "재구매 의사는 있어요")]
    _wire(monkeypatch, rows)

    out = store.theme_mention_counts("p1", {"배달비 및 할인 제도에 대한 불만족": []})

    assert out == {"배달비 및 할인 제도에 대한 불만족": 0}


def test_theme_mention_counts_no_sessions_returns_zero(monkeypatch):
    _wire(monkeypatch, [])

    out = store.theme_mention_counts("p1", {"테마": ["키워드"]})

    assert out == {"테마": 0}


# --- build_insight 의 테마 경로 (생성 스키마 + DB 실측 덮어쓰기) -----------------

class _FakeInsightLLM:
    """get_llm() 대체 — structured() 에 쓰인 스키마를 붙잡아 둔다(keywords 필수 승격 검증용)."""

    def __init__(self, theme_payload):
        self.schema_used = None
        self._theme_payload = theme_payload

    def structured(self, system, user, schema, **kw):
        self.schema_used = schema
        payload = schema.model_validate({"overall": "종합 요약입니다.", "themes": self._theme_payload})
        return payload, None

    def text(self, system, user, **kw):
        return "텍스트 생성", None


def test_build_insight_promotes_keywords_required_and_keeps_db_mention_count(monkeypatch):
    proj = Project(id="p1", topic="배달 서비스 사용 경험")
    sess = Session(id="s1", project_id="p1", status="completed", summary="배달비 관련 불만이 많았다.")

    monkeypatch.setattr(pm.store, "get_project", lambda pid: proj)
    monkeypatch.setattr(pm.store, "get_guide", lambda pid: None)
    monkeypatch.setattr(pm.store, "list_sessions", lambda pid: [sess])
    monkeypatch.setattr(pm.store, "list_turns", lambda pid, sid: [])  # 문항별 요약 경로는 스킵
    monkeypatch.setattr(pm.store, "sentiment_counts", lambda pid: {"긍정": 1, "중립": 0, "부정": 2})
    monkeypatch.setattr(pm.store, "bucket_distribution", lambda pid: {})
    monkeypatch.setattr(pm.store, "save_insight", lambda pid, i: i)

    captured_kw = {}

    def fake_mention_counts(pid, theme_keywords):
        captured_kw.update(theme_keywords)
        return {"배달비 부담": 7}   # DB 실측값 — LLM 이 준 숫자와 의도적으로 다르게

    monkeypatch.setattr(pm.store, "theme_mention_counts", fake_mention_counts)

    fake_llm = _FakeInsightLLM(theme_payload=[
        {"theme": "배달비 부담", "summary": "배달비가 비싸다는 응답이 많았다.",
         "quotes": [], "keywords": ["배달비", "쿠폰"], "mention_count": 999},   # LLM 숫자는 버려져야 함
    ])
    monkeypatch.setattr(pm, "get_llm", lambda: fake_llm)

    resp = TestClient(main.app).post("/api/projects/p1/insight")

    assert resp.status_code == 200
    body = resp.json()
    assert body["themes"][0]["mention_count"] == 7             # LLM 의 999 가 아니라 DB 실측 7
    assert captured_kw == {"배달비 부담": ["배달비", "쿠폰"]}    # LLM 은 검색어만 제공
    assert body["sentiment"] == {"긍정": 1, "중립": 0, "부정": 2}  # sentiment 도 DB 실측 그대로

    # keywords 가 생성 스키마에서 필수로 승격됐는지 — Qwen3 가 optional 필드를 통째로
    # 생략하는 실사고(F2.3.2 와 같은 패턴)를 막는 핵심 방어.
    schema_json = fake_llm.schema_used.model_json_schema()
    theme_def = schema_json["$defs"]["_GenTheme"]
    assert "keywords" in theme_def["required"]
