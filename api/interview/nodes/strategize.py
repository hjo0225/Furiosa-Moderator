"""strategize — 결정론 확정: 12턴 하드 가드 + 정직한 종료 + revisit 근거 검증 (T3).

LLM(분석 콜)의 행동 '제안'을 데이터가 검열한다 — 판단은 LLM, 집행은 결정론.
"""
from __future__ import annotations

from ..state import InterviewState

MAX_ASKED = 12  # moderator._MAX_ASKED 와 동일 값 — 구엔진 제거 시 여기가 단일 출처


def strategize(state: InterviewState) -> dict:
    # 결정론 하드 가드 — LLM 이 close 를 안 내도 12번째 질문에서 끝낸다
    if state.get("asked", 0) + 1 >= MAX_ASKED:
        return {"action": "close", "end_reason": "max_turns"}
    # 정직한 종료 — "문항을 다 입에 올림"이 아니라 원장이 전부 satisfied/saturated 일 때
    ledger = state.get("ledger", {})
    if ledger and all(e["status"] in ("satisfied", "saturated") for e in ledger.values()):
        return {"action": "close", "end_reason": "honest_close"}
    # revisit 근거 검증 — 원장에 빈약(touched) 문항이 없으면 강등, 대상이 틀리면 보정
    if state.get("action") == "revisit":
        thin = [qid for qid, e in ledger.items() if e["status"] == "touched"]
        if not thin:
            return {"action": "advance"}
        if state.get("question_id") not in thin:
            return {"question_id": thin[0]}
    return {}
