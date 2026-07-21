"""generate — 행동별 질문 생성 콜 (T3 콜 분리). T4 에서 stream_text 로 전환될 경로."""
from __future__ import annotations

from ...services.llm_client import get_llm
from ..prompts import generate_user, interview_moderator_system, opening_user
from ..state import InterviewState


def generate(state: InterviewState) -> dict:
    lang = state.get("lang", "ko")
    if not state.get("action"):
        # 오프닝 — 첫 문항 id 는 코드가 확정한다 (LLM 은 문장만)
        prompt, qid = opening_user(state["guide"])
        msg, _ = get_llm().text(interview_moderator_system(lang), prompt, max_tokens=300)
        return {"draft": (msg or "").strip(), "question_id": qid, "is_probe": False, "action": "advance"}

    msg, _ = get_llm().text(
        interview_moderator_system(lang),
        generate_user(
            state["action"], state.get("question_id", ""), state.get("probe_type", ""),
            state.get("analysis", {}).get("contradiction", ""),
            state["guide"], state.get("messages", []), state.get("ledger", {}),
        ),
        max_tokens=300,
    )
    return {"draft": (msg or "").strip()}
