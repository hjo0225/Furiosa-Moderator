"""speak — 진행자 턴 저장 + 세션 갱신. '저장은 speak 에서 완료 후 잠듦'(전역 불변식).

SSE 스트리밍 연결은 T4. T1 은 동기 반환이다.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ...schemas.models import Turn
from ...services import store
from ..state import InterviewState


def speak(state: InterviewState) -> dict:
    pid, sid = state["project_id"], state["session_id"]
    store.add_turn(pid, sid, Turn(
        role="moderator",
        text=state.get("message", ""),
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
        patch["status"] = "completed"
        patch["ended_at"] = datetime.now(timezone.utc)
    store.update_session(pid, sid, patch)
    # 턴 스크래치 초기화 — 다음 턴의 오프닝 오인 방지
    return {"covered": covered, "asked": asked, "draft": "", "utterance": ""}
