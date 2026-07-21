"""speak — 진행자 턴 저장 + 세션 갱신 + 상태 마감. '저장 완료 후 잠듦'(전역 불변식).

T2: AIMessage 를 messages 에 쌓고, probe_streak 를 갱신하고, 이번에 입에 올린
문항을 원장에서 touched 로 마킹한다(pending 이었다면).
SSE 스트리밍 연결은 T4.
"""
from __future__ import annotations

import re

from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer

from ...schemas.models import Turn
from ...services import store
from ..ledger import update_ledger
from ..state import InterviewState

_CHUNK = re.compile(r"\S+\s*")   # 어절 단위 재생 — TTS 클라이언트가 즉시 읽기 시작할 수 있게


def speak(state: InterviewState) -> dict:
    pid, sid = state["project_id"], state["session_id"]
    message = state.get("message", "")
    # guard 를 통과한 완성문을 토큰으로 방출(재생 스트리밍 — guard 앞 배치는 §11 v1 결정).
    # 방출 → 저장 순서지만 둘 다 이 노드 안에서 끝난다 — '저장 완료 후 잠듦' 불변식 유지.
    try:
        writer = get_stream_writer()
        for m in _CHUNK.finditer(message):
            writer({"token": m.group(0)})
    except Exception:  # invoke 경로 등 스트림 컨텍스트가 없으면 그냥 진행
        pass
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
        # utterance 는 리셋하지 않는다 — 뒤따르는 reflect(슬로우패스)가 읽어야 한다
    }
