"""문항별 AI 요약 (Phase 5 / F6.3) — 모델·프롬프트·묶음 헬퍼 단위테스트.

LLM 은 실제로 태우지 않는다. build_insight 전체 경로는 라이브 DB(sentiment_counts 등)를
요구해 기존 테스트도 태우지 않으므로(test_bucket_classify.py 의 분포 스모크와 같은 이유),
여기서는 순수 부분 — QuestionSummary/QuestionSummariesOut 라운드트립, 프롬프트 제약,
그리고 답변을 문항별로 묶는 순수 헬퍼 _answers_by_question — 만 검증한다.
"""
from __future__ import annotations

from api.prompts.insight import (
    QUESTION_SUMMARY_SYSTEM,
    QuestionSummariesOut,
    question_summary_user,
)
from api.routers.projects import _answers_by_question
from api.schemas.models import Insight, QuestionSummary, Turn


# --- 모델 ---------------------------------------------------------------------

def test_question_summary_roundtrips():
    qs = QuestionSummary(question_id="q1", headline="핵심 발견", summary="응답자들은 ~라고 했다.")
    back = QuestionSummary.model_validate(qs.model_dump())
    assert back.question_id == "q1"
    assert back.headline == "핵심 발견"
    assert back.summary == "응답자들은 ~라고 했다."
    # headline/summary 는 선택(기본값 "")
    d = QuestionSummary(question_id="q2")
    assert d.headline == "" and d.summary == ""


def test_question_summaries_out_roundtrips():
    out = QuestionSummariesOut(
        items=[
            QuestionSummary(question_id="q1", headline="h1", summary="s1"),
            QuestionSummary(question_id="q2", headline="h2", summary="s2"),
        ]
    )
    back = QuestionSummariesOut.model_validate(out.model_dump())
    assert [i.question_id for i in back.items] == ["q1", "q2"]
    assert back.items[0].headline == "h1" and back.items[1].summary == "s2"
    # 빈 배치도 유효
    assert QuestionSummariesOut().items == []


def test_insight_question_summaries_defaults_empty():
    assert Insight().question_summaries == []
    # 라운드트립에서도 유지된다
    i = Insight(question_summaries=[QuestionSummary(question_id="q1", headline="h")])
    back = Insight.model_validate(i.model_dump())
    assert back.question_summaries[0].question_id == "q1"


# --- 프롬프트 -----------------------------------------------------------------

def test_system_forbids_fabrication_and_centers_respondent():
    # 지어내지 말 것(theme 요약과 같은 계약) + 응답자 발언 중심
    assert "지어내지" in QUESTION_SUMMARY_SYSTEM
    assert "응답자" in QUESTION_SUMMARY_SYSTEM
    # headline / summary 두 필드를 모두 요구
    assert "headline" in QUESTION_SUMMARY_SYSTEM and "summary" in QUESTION_SUMMARY_SYSTEM


def test_user_includes_each_question_text_and_all_answers():
    items = [
        {"question_id": "q1", "question_text": "아침은 어떻게 드세요?", "answers": ["시리얼", "굶어요"]},
        {"question_id": "q2", "question_text": "왜 그렇게 하세요?", "answers": ["시간이 없어서"]},
    ]
    prompt = question_summary_user(items)
    # 각 문항 텍스트
    assert "아침은 어떻게 드세요?" in prompt
    assert "왜 그렇게 하세요?" in prompt
    # 모든 답변
    assert "시리얼" in prompt and "굶어요" in prompt and "시간이 없어서" in prompt
    # question_id 도 그대로 노출(모델이 유지하도록)
    assert "q1" in prompt and "q2" in prompt


# --- 묶음 헬퍼 (_answers_by_question) -----------------------------------------

def _t(role: str, text: str, qid: str = "") -> Turn:
    return Turn(role=role, text=text, question_id=qid)


def test_answers_by_question_groups_respondent_turns_in_order():
    s1 = [
        _t("moderator", "아침은 어떻게 드세요?", "q1"),
        _t("respondent", "시리얼 먹어요", "q1"),
        _t("respondent", "가끔 굶어요", "q1"),
        _t("moderator", "왜요?", "q2"),
        _t("respondent", "시간이 없어서", "q2"),
    ]
    s2 = [
        _t("respondent", "저는 밥 차려 먹어요", "q1"),
    ]
    grouped = _answers_by_question([s1, s2])
    # 세션·문항 순서 보존
    assert grouped["q1"] == ["시리얼 먹어요", "가끔 굶어요", "저는 밥 차려 먹어요"]
    assert grouped["q2"] == ["시간이 없어서"]


def test_answers_by_question_excludes_moderator_empty_text_and_empty_qid():
    turns = [
        _t("moderator", "질문입니다", "q1"),   # 진행자 제외
        _t("respondent", "", "q1"),            # 빈 텍스트 제외
        _t("respondent", "   ", "q1"),         # 공백만 제외
        _t("respondent", "질문 귀속 없음", ""),  # 빈 question_id 제외
        _t("respondent", "유효 답변", "q1"),
    ]
    grouped = _answers_by_question([turns])
    assert grouped == {"q1": ["유효 답변"]}
    assert "" not in grouped


def test_answers_by_question_empty_when_no_respondent_turns():
    assert _answers_by_question([[_t("moderator", "질문", "q1")]]) == {}
    assert _answers_by_question([]) == {}
