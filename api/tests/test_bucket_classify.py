"""응답 버킷 분류 (2B) — 프롬프트·BucketAssignment 모델·reflect_bucket 노드.

LLM 은 실제로 태우지 않는다: get_llm 을 목킹하고 store 는 FakeStore 로 대체한다
(test_interview_graph.py 의 FakeStore/monkeypatch 스타일).
분포 카운트(store.bucket_distribution)는 sentiment_counts 처럼 라이브 DB 가 필요해
여기서는 형태(shape) 스모크만 확인한다 — 아래 마지막 테스트 참고.
"""
from __future__ import annotations

from api.interview.nodes import reflect as ref_mod
from api.prompts.insight import BUCKET_CLASSIFY_SYSTEM, bucket_classify_user
from api.schemas.models import (
    BucketAssignment,
    GuideQuestion,
    InterviewGuide,
    ResponseBucket,
)
from api.services import store

GUIDE = InterviewGuide(
    project_id="p1", goal="아침 식사 조사",
    questions=[GuideQuestion(
        id="q1", text="평소 아침은 어떻게 해결하세요?", goal="아침 식사 패턴",
        response_buckets=[
            ResponseBucket(id="q1_b1", label="직접 조리", definition="집에서 차려 먹음"),
            ResponseBucket(id="q1_b2", label="간편식", definition="시리얼·대용식 등"),
            ResponseBucket(id="q1_other", label="기타", is_catchall=True),
        ],
    )],
)


def _state(**over):
    st = {
        "project_id": "p1", "session_id": "s1",
        "guide": GUIDE.model_dump(),
        "answered_qid": "q1", "utterance": "그냥 시리얼 부어 먹어요", "resp_turn_id": "t_1",
    }
    st.update(over)
    return st


class FakeStore:
    """update_turn 패치만 기억하는 store 대역."""
    def __init__(self):
        self.patches: dict[str, dict] = {}

    def update_turn(self, pid, sid, turn_id, patch):
        self.patches[turn_id] = patch


class FakeLLM:
    def __init__(self, out):
        self.out = out
        self.captured: tuple | None = None

    def structured(self, system, user, schema, **kw):
        self.captured = (system, user, schema)
        return self.out, None


def _patch(monkeypatch, out):
    fs = FakeStore()
    llm = FakeLLM(out)
    monkeypatch.setattr(ref_mod, "store", fs)
    monkeypatch.setattr(ref_mod, "get_llm", lambda: llm)
    return fs, llm


# --- 프롬프트 · 모델 ----------------------------------------------------------

def test_system_has_pick_one_constraint():
    assert "하나만 고르" in BUCKET_CLASSIFY_SYSTEM          # 정확히 하나만
    assert "서버가 셉니다" in BUCKET_CLASSIFY_SYSTEM         # 개수는 LLM 이 세지 않는다(계약 1)


def test_classify_user_lists_bucket_ids_and_answer():
    buckets = GUIDE.questions[0].model_dump()["response_buckets"]
    prompt = bucket_classify_user("평소 아침은?", "아침 식사 패턴", buckets, "시리얼 먹어요")
    assert "q1_b1" in prompt and "q1_b2" in prompt and "q1_other" in prompt
    assert "시리얼 먹어요" in prompt
    assert "기타/캐치올" in prompt                           # 캐치올 표식 노출


def test_bucket_assignment_roundtrips():
    a = BucketAssignment(bucket_id="q1_b2", confidence=0.8, evidence="시리얼")
    back = BucketAssignment.model_validate(a.model_dump())
    assert back.bucket_id == "q1_b2" and back.confidence == 0.8 and back.evidence == "시리얼"
    # 기본값 — confidence/evidence 는 선택
    d = BucketAssignment(bucket_id="q1_b1")
    assert d.confidence == 0.0 and d.evidence == ""


# --- reflect_bucket 노드 ------------------------------------------------------

def test_reflect_bucket_stores_valid_assignment(monkeypatch):
    fs, _ = _patch(
        monkeypatch, BucketAssignment(bucket_id="q1_b2", confidence=0.9, evidence="시리얼 부어"),
    )
    out = ref_mod.reflect_bucket(_state())
    assert out == {}
    assert fs.patches["t_1"] == {
        "bucket_id": "q1_b2", "bucket_confidence": 0.9, "bucket_evidence": "시리얼 부어",
    }


def test_reflect_bucket_clamps_confidence(monkeypatch):
    fs, _ = _patch(monkeypatch, BucketAssignment(bucket_id="q1_b1", confidence=1.7))
    ref_mod.reflect_bucket(_state())
    assert fs.patches["t_1"]["bucket_confidence"] == 1.0    # 0..1 로 클램프


def test_reflect_bucket_falls_back_to_catchall_on_unknown_id(monkeypatch):
    fs, _ = _patch(monkeypatch, BucketAssignment(bucket_id="q1_HALLUCINATED", confidence=0.5))
    ref_mod.reflect_bucket(_state())
    assert fs.patches["t_1"]["bucket_id"] == "q1_other"     # 환각 id → 캐치올


def test_reflect_bucket_noops_when_question_has_no_buckets(monkeypatch):
    fs, llm = _patch(monkeypatch, BucketAssignment(bucket_id="x"))
    guide = InterviewGuide(
        project_id="p1", goal="g",
        questions=[GuideQuestion(id="q1", text="t", goal="")],   # 버킷 없는 구가이드
    ).model_dump()
    out = ref_mod.reflect_bucket(_state(guide=guide))
    assert out == {}
    assert fs.patches == {}          # update_turn 미호출
    assert llm.captured is None      # LLM 도 안 태움 (구가이드 스킵)


def test_reflect_bucket_noops_without_turn_id(monkeypatch):
    fs, llm = _patch(monkeypatch, BucketAssignment(bucket_id="q1_b1"))
    out = ref_mod.reflect_bucket(_state(resp_turn_id=""))
    assert out == {} and fs.patches == {} and llm.captured is None


def test_reflect_bucket_noops_for_unknown_question(monkeypatch):
    fs, llm = _patch(monkeypatch, BucketAssignment(bucket_id="q1_b1"))
    out = ref_mod.reflect_bucket(_state(answered_qid="q99"))   # 가이드에 없는 문항
    assert out == {} and fs.patches == {} and llm.captured is None


def test_reflect_bucket_survives_llm_error(monkeypatch):
    from api.services.llm_client import LLMError

    fs = FakeStore()

    class Boom:
        def structured(self, *a, **k):
            raise LLMError("boom")

    monkeypatch.setattr(ref_mod, "store", fs)
    monkeypatch.setattr(ref_mod, "get_llm", lambda: Boom())
    out = ref_mod.reflect_bucket(_state())
    assert out == {} and fs.patches == {}    # 인터뷰를 막지 않는다(best-effort)


# --- 분포 실측 (store.bucket_distribution) -------------------------------------

def test_bucket_distribution_is_callable_smoke():
    # 실제 카운트는 라이브 Postgres 가 필요하다(sentiment_counts 와 동일 — 기존 테스트도
    # DB 집계 함수를 태우지 않는다). 여기서는 존재·시그니처만 스모크로 확인한다.
    assert callable(store.bucket_distribution)
