"""listen — 발화 대기(interrupt) + 슬림 분석 콜 (T4).

취재 수첩 정리(facts/hooks/coverage)는 슬로우패스(reflect_ledger)로 이사 — 이 콜은
행동 선택·모순 감지만 해서 가볍다(패스트패스 첫 토큰 단축의 핵심).
원장 신선도는 한 칸 밀린다(직전 턴까지 반영) — 분석가는 발화 원문을 직접 보므로
판단 재료 손실은 없다(의도된 계약).
interrupt() 는 여전히 노드 첫 문장 — 재실행 멱등 규약.
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage
from langgraph.types import interrupt

from ...services.llm_client import get_llm
from ..prompts import ANALYST_SYSTEM, ListenOut, analysis_user
from ..state import InterviewState
from ..tools.pace import pace
from .strategize import MAX_ASKED


def listen(state: InterviewState) -> dict:
    resume = interrupt({"waiting": "respondent"})     # 여기서 잠든다 — 재개값 = 마스킹된 발화
    if isinstance(resume, dict):
        utterance = (resume.get("text") or "").strip()
        turn_id = resume.get("turn_id", "")
    else:                                             # 구 체크포인트(문자열 resume) 재개 방어
        utterance = (resume or "").strip()
        turn_id = ""

    prev_qid = state.get("question_id", "")           # 응답자가 방금 답한 문항
    ledger = state.get("ledger", {})
    pending_n = sum(1 for e in ledger.values() if e["status"] == "pending")
    out, _ = get_llm().structured(
        ANALYST_SYSTEM,
        analysis_user(
            state["guide"], state.get("messages", []), utterance,
            state.get("asked", 0), state.get("probe_streak", 0), ledger,
            pace_line=pace(state.get("asked", 0), MAX_ASKED, pending_n),   # 도구: 페이스 (결정론)
            current_qid=prev_qid,   # 지금 문항의 응답 버킷을 프롬프트에 실어 버킷 적합도 판단 (F5.1)
        ),
        ListenOut,
        max_tokens=500,
    )
    return {
        "messages": [HumanMessage(content=utterance)],
        "utterance": utterance,
        "answered_qid": prev_qid,
        "resp_turn_id": turn_id,
        "analysis": {"contradiction": out.contradiction, "reason": out.reason,
                     "unknown_terms": out.unknown_terms},
        "action": out.action,
        "question_id": out.question_id or prev_qid,
        "probe_type": out.probe_type,
        "fatigue": out.fatigue,
        "is_probe": out.action == "probe",
        "draft": "",
        **({"end_reason": "model_done"} if out.action == "close" else {}),
    }
