"""generate — 행동별 질문 생성 콜 (T3 콜 분리). T4 에서 stream_text 로 전환될 경로."""
from __future__ import annotations

from ...services.llm_client import get_llm
from ..prompts import generate_user, interview_moderator_system, opening_user
from ..state import InterviewState
from ..tools import brief
from ..tools.playbook import playbook


def generate(state: InterviewState) -> dict:
    lang = state.get("lang", "ko")
    if not state.get("action"):
        # 오프닝 — 첫 문항 id 는 코드가 확정한다 (LLM 은 문장만)
        prompt, qid = opening_user(state["guide"])
        msg, _ = get_llm().text(interview_moderator_system(lang), prompt, max_tokens=300)
        return {"draft": (msg or "").strip(), "question_id": qid, "is_probe": False, "action": "advance"}

    # 도구 (T0 폴백: 발동은 구조화 출력·결정론 규칙이 정한다 — 자율 tool choice 없음)
    terms = state.get("analysis", {}).get("unknown_terms", [])
    notes = brief.lookup(state["project_id"], terms) if terms else []
    msg, _ = get_llm().text(
        interview_moderator_system(lang),
        generate_user(
            state["action"], state.get("question_id", ""), state.get("probe_type", ""),
            state.get("analysis", {}).get("contradiction", ""),
            state["guide"], state.get("messages", []), state.get("ledger", {}),
            brief_notes=notes,
            technique=playbook(state["action"], state.get("probe_type", "")),
        ),
        max_tokens=300,
    )
    return {"draft": (msg or "").strip()}
