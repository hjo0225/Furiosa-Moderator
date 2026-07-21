"""listen — 발화 대기(interrupt) + 분석 콜 (T3 콜 분리).

분석 콜은 질문 문장을 만들지 않는다 — 취재 수첩 정리와 행동 7종 선택만.
질문 생성은 generate, 마무리 인사는 farewell 의 일.
interrupt() 는 여전히 노드 첫 문장 — 재실행 멱등 규약.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from ...services.llm_client import get_llm
from ..ledger import update_ledger
from ..prompts import ANALYST_SYSTEM, ListenOut, analysis_user
from ..state import InterviewState


def listen(state: InterviewState) -> dict:
    utterance = interrupt({"waiting": "respondent"})  # 여기서 잠든다 — 재개값 = 마스킹된 발화
    utterance = (utterance or "").strip()

    prev_qid = state.get("question_id", "")           # 응답자가 방금 답한 문항
    out, _ = get_llm().structured(
        ANALYST_SYSTEM,
        analysis_user(
            state["guide"], state.get("messages", []), utterance,
            state.get("asked", 0), state.get("probe_streak", 0), state.get("ledger", {}),
        ),
        ListenOut,
        max_tokens=700,
    )
    return {
        "messages": [HumanMessage(content=utterance)],
        "utterance": utterance,
        "ledger": update_ledger(state.get("ledger", {}), prev_qid, out.coverage, out.facts, out.hooks),
        "analysis": {"contradiction": out.contradiction, "reason": out.reason, "coverage": out.coverage},
        "action": out.action,
        "question_id": out.question_id or prev_qid,
        "probe_type": out.probe_type,
        "is_probe": out.action == "probe",
        "draft": "",
        **({"end_reason": "model_done"} if out.action == "close" else {}),
    }
