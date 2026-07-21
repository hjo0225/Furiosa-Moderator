"""모더레이터 프롬프트 + 신규 가드 로직 단위테스트 (네트워크 없이 도는 것만).

원본 테스트는 `api.prompts.survey.interview_moderator` 를 import 했다 — 원본 레포의
디렉터리 구조(prompts/survey/)를 그대로 물고 있어 이 레포에서는 수집 단계부터 실패했다.
경로를 고치고, 라우트 검증도 새 앱의 실제 경로로 바꿨다.
PII·가드레일 케이스는 신규다.
"""
from __future__ import annotations

from api.prompts.interview_moderator import (
    INTERVIEW_MODERATOR_SYSTEM,
    interview_moderator_system,
    interview_moderator_user,
)
from api.schemas.models import GuideQuestion, InterviewGuide
from api.services.guardrail import precheck
from api.services.moderator import _moderator_user, _question_part, is_non_answer
from api.services.pii import mask_pii, scan_pii


def _guide() -> InterviewGuide:
    return InterviewGuide(
        goal="배달앱 사용 경험 파악",
        questions=[
            GuideQuestion(id="q1", text="배달앱을 주로 어떤 목적으로 쓰세요?", goal="사용 맥락", order=0),
            GuideQuestion(id="q2", text="어떤 앱을 자주 쓰세요?", goal="앱 선택", order=1),
            GuideQuestion(id="q3", text="왜 그 앱을 고르셨어요?", goal="선택 이유", order=2),
        ],
    )


# --- 모더레이터 프롬프트 ------------------------------------------------------

def test_moderator_user_embeds_goal_and_history():
    u = interview_moderator_user(
        "제로슈거 음료 선호와 구매 요인",
        [{"role": "moderator", "text": "안녕하세요"}, {"role": "respondent", "text": "네 좋아요"}],
        1,
    )
    assert "제로슈거 음료 선호와 구매 요인" in u
    assert "진행자: 안녕하세요" in u and "응답자: 네 좋아요" in u
    assert "진행자 질문 1회" in u


def test_moderator_system_drives_one_question_and_done():
    assert "done" in INTERVIEW_MODERATOR_SYSTEM
    assert "질문 하나" in INTERVIEW_MODERATOR_SYSTEM  # 한 번에 하나만


def test_moderator_english_when_lang_en():
    assert interview_moderator_system("en") != INTERVIEW_MODERATOR_SYSTEM
    assert "English" in interview_moderator_system("en")
    assert interview_moderator_system("ko") == INTERVIEW_MODERATOR_SYSTEM
    u = interview_moderator_user(
        "zero-sugar drink preference",
        [{"role": "moderator", "text": "hi"}, {"role": "respondent", "text": "good"}],
        1,
        "en",
    )
    assert "Research goal" in u and "Moderator: hi" in u and "Respondent: good" in u


def test_moderator_user_handles_empty_history():
    assert "아직 시작 전" in interview_moderator_user("주제", [], 0)


# --- 라우트 등록 --------------------------------------------------------------

def test_interview_routes_registered():
    import api.main as m

    paths = {r.path for r in m.app.routes if hasattr(r, "path")}
    assert "/api/public/projects/{pid}/sessions/{sid}/turn" in paths
    assert "/api/public/projects/{pid}/sessions/{sid}/turn/stream" in paths
    assert "/api/projects/{pid}/guide" in paths
    assert "/api/speech/transcribe" in paths
    assert "/health" in paths


# --- PII 마스킹 (M-5) ---------------------------------------------------------

def test_mask_phone_and_email():
    out = mask_pii("제 번호는 010-1234-5678이고 메일은 hong@example.com 입니다")
    assert "010-1234-5678" not in out
    assert "hong@example.com" not in out
    assert "[전화번호]" in out and "[이메일]" in out


def test_mask_rrn_takes_priority():
    out = mask_pii("주민번호 901231-1234567 입니다")
    assert "[주민번호]" in out and "901231" not in out


def test_mask_address_and_name_honorific():
    assert "[주소]" in mask_pii("서울 강남구 테헤란로 123 에 삽니다")
    assert "[이름]" in mask_pii("김철수 님이 추천해줬어요")


def test_mask_leaves_clean_text_untouched():
    clean = "배달앱을 일주일에 세 번 정도 씁니다"
    assert mask_pii(clean) == clean
    assert scan_pii(clean) == []


def test_scan_reports_types_only():
    assert scan_pii("010-1234-5678 로 연락주세요") == ["전화번호"]


def test_mask_handles_empty():
    assert mask_pii("") == ""
    assert scan_pii("") == []


# --- 중립성 가드레일 (M-2) ----------------------------------------------------

def test_precheck_flags_leading_questions():
    assert precheck("정말 그게 편리하다고 확신하세요?")
    assert precheck("그 기능 불편하셨죠, 그렇지 않나요?")
    assert precheck("비용을 줄일 수 있다고 보시죠?")
    assert precheck("얼마나 불편하셨나요?")


def test_precheck_passes_neutral_questions():
    assert precheck("그 부분 어떻게 보세요?") is None
    assert precheck("그때 어떠셨는지 말씀해 주시겠어요?") is None
    assert precheck("실제로는 어떤 결과가 나올 것 같나요?") is None


def test_precheck_handles_empty():
    assert precheck("") is None


# --- 오프닝은 문항 하나만 (회귀) ----------------------------------------------

def test_first_turn_shows_only_the_first_question():
    """첫 턴 프롬프트에 문항 목록 전체가 실려 모델이 q1~q3 을 한 발화로 합쳐 던졌다."""
    u = _moderator_user(_guide(), [], 0, [])
    assert "q1" in u
    assert "q2" not in u and "q3" not in u
    assert "하나만" in u


def test_later_turns_still_list_remaining_questions():
    """뒤 턴에서는 '넘어갈 때 참고'로 남은 문항이 계속 보여야 한다."""
    from api.schemas.models import Turn

    history = [
        Turn(role="moderator", text="배달앱을 주로 어떤 목적으로 쓰세요?", question_id="q1"),
        Turn(role="respondent", text="야근할 때 주로 시켜요"),
    ]
    u = _moderator_user(_guide(), history, 1, ["q1"])
    assert "q2" in u and "q3" in u
    assert "야근할 때 주로 시켜요" in u


# --- 무의미 발화 판정 ---------------------------------------------------------

def test_non_answer_detects_fillers():
    for t in ["음, 그래. 그래.", "어어어", "네네", "음...", "아 네", "um, yeah", "  "]:
        assert is_non_answer(t), t


def test_non_answer_keeps_real_answers():
    """오탐이 미탐보다 나쁘다 — 짧아도 내용이 있으면 답변으로 남겨야 한다."""
    for t in ["배민이요", "네 자주 써요", "글쎄요", "별로요", "한 3만원?",
              "음 저는 주로 점심에 시켜요"]:
        assert not is_non_answer(t), t


def test_submit_route_registered():
    import api.main as m

    paths = {r.path for r in m.app.routes if hasattr(r, "path")}
    assert "/api/public/projects/{pid}/sessions/{sid}/submit" in paths


# --- 완료는 '제출' 시점이다 (회귀) --------------------------------------------

def test_done_marks_pending_not_completed(monkeypatch):
    """진행자가 done 을 내도 completed 가 되면 안 된다 — 제출해야 응답 1건이다.

    예전엔 여기서 바로 completed + ended_at 을 찍어, 응답자가 창을 닫아버린 세션도
    완료로 집계됐다.
    """
    from api.schemas.models import Session, Turn
    from api.services import moderator as mod

    patches: dict = {}

    monkeypatch.setattr(mod.store, "list_turns", lambda *a, **k: [
        Turn(role="moderator", text="어떤 목적으로 쓰세요?", question_id="q1"),
        Turn(role="respondent", text="야근할 때 주로 시켜요"),
    ])
    monkeypatch.setattr(mod.store, "add_turn", lambda pid, sid, t: t)
    monkeypatch.setattr(mod.store, "update_session", lambda pid, sid, patch: patches.update(patch))
    monkeypatch.setattr(mod, "tag_emotion", lambda text: ("중립", 0.0))
    monkeypatch.setattr(mod.guardrail, "ensure_neutral", lambda m: (m, False, ""))

    class _FakeLLM:
        def structured(self, system, user, model, **kw):
            return model(message="말씀 감사합니다.", done=True, question_id="q1"), {}

    monkeypatch.setattr(mod, "get_llm", lambda: _FakeLLM())

    session = Session(id="s_1", project_id="p_1", status="active")
    _msg, done, _r, _m = mod.next_turn("p_1", session, _guide(), "충분히 말했어요")

    assert done is True
    assert patches["status"] == "pending"
    assert "ended_at" not in patches   # 종료시각은 제출할 때 찍는다


def test_question_part_drops_the_greeting():
    """되물을 때 인사까지 되풀이하면 더 어색하다."""
    op = "안녕하세요! 오늘은 배달앱 경험을 여쭤볼게요. 배달앱을 주로 어떤 목적으로 쓰세요?"
    assert _question_part(op) == "배달앱을 주로 어떤 목적으로 쓰세요?"
    assert _question_part("조금만 더 들려주세요.") == "조금만 더 들려주세요."
