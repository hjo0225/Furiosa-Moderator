"""farewell — 마무리 인사 생성. 질문이 아니므로 guard 를 거치지 않는다(기존 동작 유지).

12턴 가드로 잘릴 때 모델의 '질문'이 마지막 멘트로 나가던 구엔진 quirk 가 여기서 해소된다.
생성 실패는 기본 문구 폴백 — 마무리 인사가 인터뷰를 막아선 안 된다.
"""
from __future__ import annotations

import logging

from ...services.llm_client import LLMError, get_llm
from ..prompts import farewell_user, interview_moderator_system
from ..state import InterviewState

log = logging.getLogger(__name__)

FAREWELL_FALLBACK = "오늘 말씀 정말 감사합니다. 여기서 인터뷰를 마치겠습니다."


def farewell(state: InterviewState) -> dict:
    try:
        msg, _ = get_llm().text(
            interview_moderator_system(state.get("lang", "ko")),
            farewell_user(state.get("messages", [])),
            max_tokens=200,
        )
    except LLMError as e:
        log.warning("마무리 인사 생성 실패 — 기본 문구 사용: %s", e)
        msg = ""
    return {"message": (msg or "").strip() or FAREWELL_FALLBACK, "rewritten": False, "done": True, "draft": ""}
