"""guard — 중립성 검수. 마무리 멘트(done)는 질문이 아니므로 검사하지 않는다(기존 동일)."""
from __future__ import annotations

from ...services import guardrail
from ..state import InterviewState


def guard(state: InterviewState) -> dict:
    draft = state.get("draft", "")
    if state.get("done") or not draft:
        return {"message": draft, "rewritten": False}
    message, rewritten, _reason = guardrail.ensure_neutral(draft)
    return {"message": message, "rewritten": rewritten}
