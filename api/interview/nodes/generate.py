"""generate — T2: 오프닝 생성 + close 시 마무리 확정.

일반 턴의 생성 콜은 여전히 listen 의 만능 콜에 있다(콜 수 불변).
T3~T5 에서 행동별 생성·도구 호출이 이 노드로 들어온다.
"""
from __future__ import annotations

from ...services.llm_client import get_llm
from ..prompts import ListenOut, interview_moderator_system, listen_user
from ..state import InterviewState

_FAREWELL_FALLBACK = "오늘 말씀 정말 감사합니다. 여기서 인터뷰를 마치겠습니다."


def generate(state: InterviewState) -> dict:
    if state.get("action") == "close":
        # 구엔진 파리티: 모델이 준 문장이 있으면 그대로, 없으면 기본 인사.
        return {"draft": state.get("draft") or _FAREWELL_FALLBACK, "done": True}

    if not state.get("draft"):
        # 오프닝 턴 — 그래프 진입 직후 (대화 없음)
        out, _ = get_llm().structured(
            interview_moderator_system(state.get("lang", "ko")),
            listen_user(state["guide"], [], "", 0, 0, state.get("ledger", {}), state.get("lang", "ko")),
            ListenOut,
            max_tokens=500,
        )
        return {
            "draft": (out.message or "").strip(),
            "question_id": out.question_id or "",
            "is_probe": False,
            "action": "advance",
        }
    return {}
