"""speak — 진행자 턴 저장 + 세션 갱신 + 상태 마감. '저장 완료 후 잠듦'(전역 불변식).

T2: AIMessage 를 messages 에 쌓고, probe_streak 를 갱신하고, 이번에 입에 올린
문항을 원장에서 touched 로 마킹한다(pending 이었다면).
SSE 스트리밍 연결은 T4.
"""
from __future__ import annotations

from langchain_core.messages import AIMessage

from ...schemas.models import Turn
from ...services import store
from ..ledger import update_ledger
from ..state import InterviewState


def speak(state: InterviewState) -> dict:
    pid, sid = state["project_id"], state["session_id"]
    message = state.get("message", "")
    store.add_turn(pid, sid, Turn(
        role="moderator",
        text=message,
        is_probe=bool(state.get("is_probe")),
        question_id=state.get("question_id", ""),
        guardrail_rewritten=bool(state.get("rewritten")),
    ))
    covered = list(state.get("covered", []))
    qid = state.get("question_id", "")
    if qid and qid not in covered:
        covered.append(qid)
    asked = state.get("asked", 0) + 1
    patch: dict = {"asked": asked, "covered": covered, "status": "active"}
    if state.get("done"):
        # 진행자 done ≠ 응답 1건 — 응답자가 제출(public.submit)해야 completed 가 되고
        # ended_at 도 그때 찍힌다 (원격 R-4 시맨틱과 정렬).
        patch["status"] = "pending"
    store.update_session(pid, sid, patch)
    return {
        "messages": [AIMessage(content=message)],
        "ledger": update_ledger(state.get("ledger", {}), qid, "touched", [], []),
        "covered": covered,
        "asked": asked,
        "probe_streak": (state.get("probe_streak", 0) + 1) if state.get("is_probe") else 0,
        "draft": "",
        "utterance": "",
    }
