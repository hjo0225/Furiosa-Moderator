"""가이드 주제화 — 구형(평면) 호환 읽기와 턴 예산.

스펙: docs/specs/2026-07-24-guide-topics-turn-budget.md
운영 DB 에는 평면 questions 만 있는 가이드가 남아 있다. 그게 깨지면 라이브 프로젝트가
전부 죽으므로 여기서 계약으로 고정한다.
"""
from __future__ import annotations

from api.schemas.models import GuideQuestion, GuideTopic, InterviewGuide


def _q(qid: str) -> GuideQuestion:
    return GuideQuestion(id=qid, text=f"{qid}?", goal="g")


def test_legacy_flat_guide_is_wrapped_into_one_topic():
    g = InterviewGuide(goal="배달앱", questions=[_q("q1"), _q("q2")])
    assert len(g.topics) == 1
    assert g.topics[0].title == "전체"
    assert [q.id for q in g.topics[0].questions] == ["q1", "q2"]
    # 평면 뷰는 그대로 남는다 — 진행자·인사이트·알림이 이걸 읽는다
    assert [q.id for q in g.questions] == ["q1", "q2"]


def test_topics_are_the_source_of_truth():
    g = InterviewGuide(
        goal="배달앱",
        topics=[GuideTopic(id="t1", title="선택", questions=[_q("q1"), _q("q2")]),
                GuideTopic(id="t2", title="전환", questions=[_q("q3")])],
    )
    assert [q.id for q in g.questions] == ["q1", "q2", "q3"]   # 평면 뷰는 topics 에서 파생


def test_conflicting_questions_are_overwritten_by_topics():
    """둘 다 주면 topics 가 이긴다 — 두 목록이 어긋난 채 흘러다니지 않게."""
    g = InterviewGuide(
        goal="배달앱",
        topics=[GuideTopic(id="t1", title="선택", questions=[_q("q1")])],
        questions=[_q("zz")],
    )
    assert [q.id for q in g.questions] == ["q1"]


def test_max_turns_is_questions_plus_one_per_topic():
    g = InterviewGuide(topics=[
        GuideTopic(id="t1", title="a", questions=[_q("q1"), _q("q2")]),   # 3턴
        GuideTopic(id="t2", title="b", questions=[_q("q3")]),             # 2턴
    ])
    assert g.max_turns == 5


def test_legacy_guide_max_turns_matches_wrapped_topic():
    # 구형 질문 7개 → 주제 1개(7질문) → 8턴. 라이브 프로젝트가 실제로 받는 값이다.
    g = InterviewGuide(questions=[_q(f"q{i}") for i in range(1, 8)])
    assert g.max_turns == 8


def test_empty_guide_has_no_budget():
    assert InterviewGuide().max_turns == 0
