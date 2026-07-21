"""listen — 발화 대기(interrupt) + 만능 1콜 + 원장 갱신 (T2).

T2: store 를 더 이상 읽지 않는다 — 대화·커버리지·페이스 전부 State 소유(필수③).
원장 갱신은 v1 규칙대로 노드 내에서(슬로우패스 이사는 T4).
interrupt() 는 여전히 노드 첫 문장 — 재실행 멱등 규약.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from ...services.llm_client import get_llm
from ..ledger import update_ledger
from ..prompts import ListenOut, interview_moderator_system, listen_user
from ..state import InterviewState


def listen(state: InterviewState) -> dict:
    utterance = interrupt({"waiting": "respondent"})  # 여기서 잠든다 — 재개값 = 마스킹된 발화
    utterance = (utterance or "").strip()

    prev_qid = state.get("question_id", "")           # 응답자가 방금 답한 문항
    out, _ = get_llm().structured(
        interview_moderator_system(state.get("lang", "ko")),
        listen_user(
            state["guide"], state.get("messages", []), utterance,
            state.get("asked", 0), state.get("probe_streak", 0),
            state.get("ledger", {}), state.get("lang", "ko"),
        ),
        ListenOut,
        max_tokens=700,
    )
    return {
        "messages": [HumanMessage(content=utterance)],
        "utterance": utterance,
        "ledger": update_ledger(state.get("ledger", {}), prev_qid, out.coverage, out.facts, out.hooks),
        "draft": (out.message or "").strip(),
        "action": "close" if out.done else ("probe" if out.is_probe else "advance"),
        "question_id": out.question_id or prev_qid,
        "is_probe": bool(out.is_probe),
        **({"end_reason": "model_done"} if out.done else {}),
    }
