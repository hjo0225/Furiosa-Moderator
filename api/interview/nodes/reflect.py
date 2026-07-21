"""reflect — 슬로우패스 (Send 병렬). 응답자가 말하는 시간에 무거운 정리를 해둔다.

SSE 에서는 speak 가 토큰을 이미 다 내보낸 뒤라 여기 걸리는 시간은 체감 0.
- reflect_ledger: 직전 문답을 취재 수첩(원장)에 정리 — T3 까지 listen 이 하던 일의 이사.
- reflect_emotion 은 Task 2 에서 합류.
"""
from __future__ import annotations

import logging

from ...services.llm_client import LLMError, get_llm
from ..ledger import update_ledger
from ..prompts import REFLECT_SYSTEM, ReflectOut, reflect_user
from ..state import InterviewState

log = logging.getLogger(__name__)


def reflect_ledger(state: InterviewState) -> dict:
    qid = state.get("answered_qid", "")
    utterance = state.get("utterance", "")
    questions = {q["id"]: q for q in state.get("guide", {}).get("questions", []) if q.get("id")}
    if not qid or not utterance or qid not in questions:
        return {}
    q = questions[qid]
    try:
        out, _ = get_llm().structured(
            REFLECT_SYSTEM, reflect_user(q["text"], q.get("goal", ""), utterance),
            ReflectOut, max_tokens=400,
        )
    except LLMError as e:
        log.warning("원장 갱신 실패 — 이번 턴은 건너뜀 (다음 턴에 회복): %s", e)
        return {}
    return {"ledger": update_ledger(state.get("ledger", {}), qid, out.coverage, out.facts, out.hooks)}
