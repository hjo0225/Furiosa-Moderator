"""generate — T1 은 오프닝 생성 + close 시 마무리 확정만.

일반 턴의 생성 콜은 T1 에선 listen 의 만능 콜에 있다(콜 수 불변).
T3~T5 에서 행동별 생성·도구 호출이 이 노드로 들어온다.
"""
from __future__ import annotations

from ...prompts.interview_moderator import interview_moderator_system
from ...schemas.models import InterviewGuide
from ...services.llm_client import get_llm
from ...services.moderator import _ModeratorOut, _moderator_user
from ..state import InterviewState

_FAREWELL_FALLBACK = "오늘 말씀 정말 감사합니다. 여기서 인터뷰를 마치겠습니다."


def generate(state: InterviewState) -> dict:
    if state.get("action") == "close":
        # 구엔진 파리티: 모델이 준 문장이 있으면 그대로(12턴 가드로 잘린 경우 질문일 수도
        # 있다 — 알려진 구엔진 특성 보존), 없으면 기본 인사.
        return {"draft": state.get("draft") or _FAREWELL_FALLBACK, "done": True}

    if not state.get("draft"):
        # 오프닝 턴 — 그래프 진입 직후 (이력 없음)
        guide = InterviewGuide.model_validate(state["guide"])
        out, _ = get_llm().structured(
            interview_moderator_system(state.get("lang", "ko")),
            _moderator_user(guide, [], 0, []),
            _ModeratorOut,
            max_tokens=500,
        )
        return {
            "draft": (out.message or "").strip(),
            "question_id": out.question_id or "",
            "is_probe": False,
            "action": "advance",
        }
    return {}
