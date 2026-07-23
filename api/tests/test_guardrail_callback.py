"""가드레일 ↔ 모더레이터 프롬프트 충돌 회귀 (벤치 2026-07-23).

522턴 실측에서 재작성률 85.4%(446/522)가 나왔고, 판정 사유가 전부 같은 패턴이었다:
모더레이터 프롬프트가 시킨 **콜백**("아까 …라고 하셨는데")을 가드레일이 "전제 = 유도"로
판정한 것. 두 프롬프트가 서로 반대를 지시하고 있었다.

여기 테스트는 그 계약을 문서가 아니라 코드로 고정한다 — 콜백을 시키는 쪽과 그것을
심사하는 쪽이 같은 정의를 쓰는지. LLM 판정 자체는 목킹 대상이라 여기서는 두 프롬프트의
문안 정합만 본다(프롬프트 레벨 테스트는 test_guide_prompt.py 와 같은 계열).
"""
from __future__ import annotations

from api.prompts.interview_moderator import (
    INTERVIEW_MODERATOR_SYSTEM,
    INTERVIEW_MODERATOR_SYSTEM_EN,
)
from api.services.guardrail import _NEUTRALITY_RULES, precheck


def test_moderator_still_instructs_callbacks():
    """전제 확인 — 모더레이터가 콜백을 시키지 않으면 이 충돌 자체가 없다."""
    assert "콜백" in INTERVIEW_MODERATOR_SYSTEM
    assert "callback" in INTERVIEW_MODERATOR_SYSTEM_EN


def test_neutrality_rules_exempt_respondent_callbacks():
    """가드레일 규칙이 콜백을 명시적으로 허용해야 한다.

    이게 없으면 8B 판정 모델은 '아까 …라고 하셨는데'를 전제로 읽고 재작성을 건다.
    """
    assert "콜백" in _NEUTRALITY_RULES, "콜백 허용 기준이 판정 규칙에 없다"
    # 허용의 근거는 '누가 한 말인가' 다 — 응답자 본인 발화의 인용은 전제가 아니다.
    assert "응답자" in _NEUTRALITY_RULES


def test_neutrality_rules_still_forbid_moderator_introduced_premises():
    """콜백을 허용하되 유도 금지가 물러나면 안 된다 — 허용 범위는 '응답자가 한 말'로 한정."""
    assert "유도 금지" in _NEUTRALITY_RULES
    assert "하지 않은" in _NEUTRALITY_RULES, "응답자가 하지 않은 말을 까는 것은 여전히 금지여야 한다"


def test_neutrality_rules_do_not_teach_vague_rewrites():
    """모범 답안이 '그 부분 어떻게 보세요?' 면 재작성이 두루뭉술해진다(벤치 §1-7).

    실측: 재작성 10/10, 결과 질문이 구체성을 잃고 대화가 한 주제에 갇힘.
    규칙이 그 예시를 모범으로 제시하고 있었던 것이 원인 중 하나다.
    """
    assert "그 부분 어떻게 보세요" not in _NEUTRALITY_RULES


def test_callback_phrasing_passes_regex_precheck():
    """정규식 사전검사는 원래 콜백을 안 잡는다 — 오탐은 순전히 LLM 판정에서 온다."""
    assert precheck("아까 야근할 때 시킨다고 하셨는데, 그럴 때 앱에서 제일 아쉬운 건 뭐였어요?") is None
    assert precheck("말씀하신 배달비 부분, 구체적으로 어떤 상황이었는지 들려주시겠어요?") is None
