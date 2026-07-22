"""자극물(제시 자료) 데이터 연동 — 스키마 왕복 + 턴 응답 귀속 (PRD v2.0 자극물).

가이드 문항에 붙인 Stimulus 가 별도 테이블 없이 guides.questions(JSONB)에 실려 왕복하고,
진행자가 그 문항을 다룰 때 턴 응답(TurnOut)에 함께 실려 응답자 화면이 2분할로 렌더되는지 검증.
url 이 빈 자극물은 '없음'으로 걸러 내려보내지 않는다(빈 액자 방지). LLM·DB 없이 대역으로 돈다.
"""
from __future__ import annotations

import api.routers.public as pub
from api.routers.public import _question_stimulus
from api.schemas.models import (
    GuideQuestion,
    InterviewGuide,
    Session,
    Stimulus,
    Turn,
    TurnIn,
    TurnOut,
)


def _guide_with_stimulus() -> InterviewGuide:
    return InterviewGuide(
        project_id="p1",
        goal="시안 반응",
        questions=[
            GuideQuestion(id="q1", text="평소 어떤 앱을 쓰세요?", goal="현재 사용"),
            GuideQuestion(
                id="q2",
                text="이 시안 어떠세요?",
                goal="시안 반응",
                stimulus=Stimulus(type="image", url="https://cdn.x/ad.png", caption="새 광고 시안"),
            ),
        ],
    )


# --- 스키마: 기본값 + JSONB 왕복 -------------------------------------------------

def test_stimulus_defaults():
    s = Stimulus()
    assert s.type == "image" and s.url == "" and s.caption == ""


def test_guide_question_stimulus_defaults_none():
    q = GuideQuestion(id="q1", text="?")
    assert q.stimulus is None


def test_guide_roundtrips_stimulus_through_jsonb():
    # 저장 = model_dump(JSONB 로), 재적재 = model_validate. 별도 테이블·마이그레이션 없이 왕복해야 한다.
    guide = _guide_with_stimulus()
    reloaded = InterviewGuide.model_validate(guide.model_dump())
    assert reloaded.questions[0].stimulus is None
    stim = reloaded.questions[1].stimulus
    assert stim is not None
    assert stim.type == "image"
    assert stim.url == "https://cdn.x/ad.png"
    assert stim.caption == "새 광고 시안"


def test_video_stimulus_roundtrip():
    q = GuideQuestion(
        id="qv", text="이 영상 보시고", stimulus=Stimulus(type="video", url="https://cdn.x/clip.mp4")
    )
    reloaded = GuideQuestion.model_validate(q.model_dump())
    assert reloaded.stimulus is not None and reloaded.stimulus.type == "video"


# --- TurnOut: 기본 None + 적재 -------------------------------------------------

def test_turnout_stimulus_defaults_none():
    out = TurnOut(message="안녕하세요")
    assert out.stimulus is None


def test_turnout_carries_stimulus():
    out = TurnOut(message="이 시안 어떠세요?", stimulus=Stimulus(url="https://cdn.x/ad.png"))
    assert out.stimulus is not None and out.stimulus.url == "https://cdn.x/ad.png"
    # 직렬화(응답 바디)에도 실려 나가야 한다.
    dumped = out.model_dump()
    assert dumped["stimulus"]["url"] == "https://cdn.x/ad.png"


# --- 순수 헬퍼: 문항 → 자극물 조회 ---------------------------------------------

def test_question_stimulus_lookup_hits():
    guide = _guide_with_stimulus()
    stim = _question_stimulus(guide, "q2")
    assert stim is not None and stim.url == "https://cdn.x/ad.png"


def test_question_stimulus_without_stimulus_is_none():
    guide = _guide_with_stimulus()
    assert _question_stimulus(guide, "q1") is None


def test_question_stimulus_empty_qid_is_none():
    guide = _guide_with_stimulus()
    assert _question_stimulus(guide, "") is None


def test_question_stimulus_unknown_qid_is_none():
    guide = _guide_with_stimulus()
    assert _question_stimulus(guide, "q999") is None


def test_question_stimulus_empty_url_treated_as_none():
    # 의뢰자가 캡션만 남기고 URL 을 비운 채 저장 → 빈 액자 대신 '없음'으로 취급한다.
    guide = InterviewGuide(
        project_id="p1",
        questions=[GuideQuestion(id="q1", text="?", stimulus=Stimulus(caption="아직 URL 없음"))],
    )
    assert _question_stimulus(guide, "q1") is None


def test_question_stimulus_whitespace_url_treated_as_none():
    guide = InterviewGuide(
        project_id="p1",
        questions=[GuideQuestion(id="q1", text="?", stimulus=Stimulus(url="   "))],
    )
    assert _question_stimulus(guide, "q1") is None


# --- 턴 엔드포인트: 진행자가 다루는 문항의 자극물이 TurnOut 에 실린다 -----------

def _spy_engine(question_id: str):
    """mod_turn.question_id 를 지정한 값으로 채워 돌려주는 진행자 대역."""
    def fake_next_turn(*a, **k):
        return "이 시안 어떠세요?", False, None, Turn(
            role="moderator", text="이 시안 어떠세요?", question_id=question_id
        )
    return fake_next_turn


def _stub_turn(monkeypatch, guide: InterviewGuide, question_id: str):
    monkeypatch.delenv("INTERVIEW_ENGINE", raising=False)
    from api.config import get_settings
    get_settings.cache_clear()
    monkeypatch.setattr(pub.store, "get_session", lambda p, s: Session(id="s1", project_id="p1"))
    monkeypatch.setattr(pub.store, "get_guide", lambda p: guide)
    monkeypatch.setattr(pub.moderator, "next_turn", _spy_engine(question_id))


def test_turn_returns_stimulus_for_current_question(monkeypatch):
    _stub_turn(monkeypatch, _guide_with_stimulus(), "q2")
    out = pub.turn("p1", "s1", TurnIn(text="자세히 보고 싶어요"))
    assert out.stimulus is not None
    assert out.stimulus.type == "image"
    assert out.stimulus.url == "https://cdn.x/ad.png"
    from api.config import get_settings
    get_settings.cache_clear()


def test_turn_returns_none_when_question_has_no_stimulus(monkeypatch):
    _stub_turn(monkeypatch, _guide_with_stimulus(), "q1")
    out = pub.turn("p1", "s1", TurnIn(text="배민 써요"))
    assert out.stimulus is None
    from api.config import get_settings
    get_settings.cache_clear()


def test_turn_returns_none_for_empty_url_stimulus(monkeypatch):
    guide = InterviewGuide(
        project_id="p1",
        questions=[GuideQuestion(id="q1", text="?", stimulus=Stimulus(caption="URL 미입력"))],
    )
    _stub_turn(monkeypatch, guide, "q1")
    out = pub.turn("p1", "s1", TurnIn(text="네"))
    assert out.stimulus is None
    from api.config import get_settings
    get_settings.cache_clear()
