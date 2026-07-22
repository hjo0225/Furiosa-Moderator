"""프로빙 엔진 정식화 (Phase 3, PRD F5.1) — 버킷 적합도·피로 감지·프로빙 유형 5종.

analyst 스키마/프롬프트와 결정론 strategize 만 건드리는 contained 변경.
FakeLLM/FakeStore/GUIDE/_start/fakes 는 test_interview_graph 의 것을 그대로 재사용한다.
"""
from __future__ import annotations

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from api.interview.graph import build_graph
from api.interview.nodes.strategize import strategize
from api.interview.prompts import (
    ANALYST_SYSTEM,
    ListenOut,
    ReflectOut,
    _PROBE_DIRECTIVES,
    analysis_user,
)
from api.interview.state import init_ledger
from api.schemas.models import GuideQuestion, InterviewGuide, ResponseBucket

# 기존 그래프 테스트의 부품을 그대로 재사용 (fakes 는 pytest 픽스처 — import 로 등록됨)
from api.tests.test_interview_graph import GUIDE, _start, fakes  # noqa: F401

FIVE_NEW = ("예시요청", "대비", "결과추적", "감정원인")
ALL_PROBE_TYPES = ("", "구체화", "심화", *FIVE_NEW)

# q1 은 응답 버킷 보유, q2 는 미보유 — 버킷 블록 노출/생략 판단용
BUCKET_GUIDE = InterviewGuide(
    project_id="p1", goal="배달앱 전환 요인",
    questions=[
        GuideQuestion(
            id="q1", text="어떤 앱을 쓰세요?", goal="현재 사용 앱",
            response_buckets=[
                ResponseBucket(id="q1_a", label="배달의민족", definition="배민을 주로 씀"),
                ResponseBucket(id="q1_b", label="쿠팡이츠", definition="쿠팡이츠를 주로 씀"),
                ResponseBucket(id="q1_other", label="기타", is_catchall=True),
            ],
        ),
        GuideQuestion(id="q2", text="갈아탄 계기는?", goal="전환 트리거"),  # 버킷 없음
    ],
).model_dump()


# --- 스키마: fatigue 기본값 + 프로빙 유형 5종 확장 ------------------------------

def test_listenout_fatigue_defaults_false():
    assert ListenOut().fatigue is False


@pytest.mark.parametrize("pt", ALL_PROBE_TYPES)
def test_probe_type_values_validate(pt):
    assert ListenOut(action="probe", probe_type=pt).probe_type == pt


def test_probe_type_rejects_unknown():
    with pytest.raises(ValueError):
        ListenOut(probe_type="아무거나")


# --- 프롬프트: 피로/버킷 규칙 + 프로빙 유형 지시 --------------------------------

def test_analyst_system_has_fatigue_and_bucket_rules():
    assert "피로" in ANALYST_SYSTEM
    assert "버킷" in ANALYST_SYSTEM
    assert "fatigue" in ANALYST_SYSTEM


@pytest.mark.parametrize("pt", ("구체화", "심화", *FIVE_NEW))
def test_probe_directives_cover_all_types(pt):
    assert pt in _PROBE_DIRECTIVES and _PROBE_DIRECTIVES[pt]


# --- analysis_user: 버킷 블록 노출/생략 ----------------------------------------

def test_analysis_user_includes_buckets_for_current_qid():
    out = analysis_user(BUCKET_GUIDE, [], "답변", 0, 0, {}, current_qid="q1")
    assert "[지금 문항의 응답 버킷]" in out
    assert "배달의민족" in out and "쿠팡이츠" in out


def test_analysis_user_omits_block_without_current_qid():
    out = analysis_user(BUCKET_GUIDE, [], "답변", 0, 0, {}, current_qid="")
    assert "[지금 문항의 응답 버킷]" not in out


def test_analysis_user_omits_block_when_question_has_no_buckets():
    out = analysis_user(BUCKET_GUIDE, [], "답변", 0, 0, {}, current_qid="q2")
    assert "[지금 문항의 응답 버킷]" not in out


# --- strategize: 피로 강등 ------------------------------------------------------

def _thin_ledger():
    """q1 touched(빈약)·q2 pending — 전환할 pending 이 있는 상태."""
    led = init_ledger(GUIDE.model_dump())
    led["q1"]["status"] = "touched"
    return led


def test_fatigue_probe_with_pending_advances():
    patch = strategize({"asked": 4, "action": "probe", "question_id": "q1",
                        "probe_streak": 1, "fatigue": True, "ledger": _thin_ledger()})
    assert patch["action"] == "advance"
    assert patch["question_id"] == "q2"
    assert patch["is_probe"] is False
    assert patch["probe_type"] == ""


def test_fatigue_clarify_also_downgraded():
    patch = strategize({"asked": 4, "action": "clarify", "question_id": "q1",
                        "probe_streak": 1, "fatigue": True, "ledger": _thin_ledger()})
    assert patch["action"] == "advance" and patch["question_id"] == "q2"


def test_fatigue_probe_without_pending_closes():
    led = init_ledger(GUIDE.model_dump())
    led["q1"]["status"] = "touched"
    led["q2"]["status"] = "touched"   # pending 없음, 전부 satisfied 도 아님
    patch = strategize({"asked": 4, "action": "probe", "question_id": "q1",
                        "probe_streak": 1, "fatigue": True, "ledger": led})
    assert patch["action"] == "close"
    assert patch["end_reason"] == "fatigue"


def test_no_fatigue_leaves_probe_untouched():
    patch = strategize({"asked": 4, "action": "probe", "question_id": "q1",
                        "probe_streak": 1, "fatigue": False, "ledger": _thin_ledger()})
    assert patch == {}   # 피로 없으면 기존 동작 그대로


def test_fatigue_ignored_for_non_probe_actions():
    # advance 등 이미 캐묻지 않는 행동은 피로여도 건드리지 않는다
    patch = strategize({"asked": 4, "action": "advance", "question_id": "q2",
                        "probe_streak": 0, "fatigue": True, "ledger": _thin_ledger()})
    assert patch == {}


# --- 그래프: 피로 감지 시 probe 대신 advance/close -------------------------------

def test_graph_fatigue_downgrades_probe_to_advance(fakes):
    fs, set_llm = fakes
    set_llm(
        outs=[ListenOut(action="probe", question_id="q1", probe_type="심화", fatigue=True),
              ReflectOut()],
        texts=["오프닝?", "다음 문항 질문?"],
    )
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "s1"}}
    _start(g, config)                                  # 오프닝: q1 touched / q2 pending
    r = g.invoke(Command(resume="글쎄요 그냥요"), config)
    assert r["is_probe"] is False                      # 피로 감지 → probe 취소
    assert r["question_id"] == "q2"                    # 남은 pending 으로 전환
    assert not r.get("done")
    assert "__interrupt__" in r                        # 종료가 아니라 다음 답변 대기


def test_graph_fatigue_closes_when_no_pending(fakes):
    fs, set_llm = fakes
    led = init_ledger(GUIDE.model_dump())
    led["q1"]["status"] = "touched"
    led["q2"]["status"] = "touched"                    # pending 없음, 전부 satisfied 도 아님
    set_llm(outs=[ListenOut(action="probe", question_id="q1", fatigue=True), ReflectOut()],
            texts=["오프닝?", "마무리 인사"])
    g = build_graph(InMemorySaver())
    config = {"configurable": {"thread_id": "sf"}}
    g.invoke({"project_id": "p1", "session_id": "sf", "lang": "ko",
              "guide": GUIDE.model_dump(), "covered": [], "asked": 0,
              "messages": [], "ledger": led, "probe_streak": 0}, config)
    r = g.invoke(Command(resume="그냥요"), config)
    assert r["done"] is True and r["end_reason"] == "fatigue"
    assert r["message"] == "마무리 인사"
