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
from api.services.guardrail import precheck
from api.services.pii import mask_pii, scan_pii


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
