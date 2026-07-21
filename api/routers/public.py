"""응답자 API — 동의·세션·턴 (R-1 ~ R-4). 무인증(링크 접속).

응답자에게는 프로젝트의 최소 정보만 노출한다. 가이드 문항·다른 응답자 데이터는 주지 않는다.
"""
from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, HTTPException

from ..config import get_settings
from ..interview import engine as graph_engine
from ..schemas.models import ConsentLog, Session, SessionStartIn, TurnIn, TurnOut
from ..services import moderator, store
from ..services.llm_client import LLMError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/public/projects", tags=["respondent"])


@router.get("/{pid}")
def public_project(pid: str) -> dict:
    """링크 접속 시 보여줄 최소 정보."""
    p = store.get_project(pid)
    if not p:
        raise HTTPException(404, "인터뷰를 찾을 수 없습니다.")
    if p.status != "deployed":
        raise HTTPException(403, "아직 배포되지 않은 인터뷰입니다.")
    return {"id": p.id, "title": p.title, "topic": p.topic, "status": p.status}


@router.post("/{pid}/sessions", response_model=Session)
def start_session(pid: str, body: SessionStartIn) -> Session:
    """R-1 동의 → 세션 시작. 동의 없이는 시작할 수 없다."""
    p = store.get_project(pid)
    if not p:
        raise HTTPException(404, "인터뷰를 찾을 수 없습니다.")
    if p.status != "deployed":
        raise HTTPException(403, "아직 배포되지 않은 인터뷰입니다.")
    if not body.agreed:
        raise HTTPException(400, "동의가 필요합니다.")
    if not store.get_guide(pid):
        raise HTTPException(500, "가이드가 없어 인터뷰를 시작할 수 없습니다.")

    # UA 원문은 식별자가 될 수 있어 해시만 남긴다(PRD 9절).
    ua_hash = hashlib.sha256((body.user_agent or "").encode()).hexdigest()[:16] if body.user_agent else ""
    consent = ConsentLog(agreed=True, user_agent_hash=ua_hash)
    return store.create_session(Session(project_id=pid), consent)


@router.post("/{pid}/sessions/{sid}/turn", response_model=TurnOut)
def turn(pid: str, sid: str, body: TurnIn) -> TurnOut:
    """R-2/R-3/R-4 한 턴 — 응답자 발화를 받아 진행자의 다음 한 마디를 돌려준다.

    첫 호출은 text 를 비워 보내면 진행자의 오프닝을 받는다.
    """
    session = store.get_session(pid, sid)
    if not session:
        raise HTTPException(404, "세션을 찾을 수 없습니다.")
    if session.status == "completed":
        raise HTTPException(409, "이미 종료된 인터뷰입니다.")
    guide = store.get_guide(pid)
    if not guide:
        raise HTTPException(500, "가이드가 없습니다.")

    # INTERVIEW_ENGINE 플래그로 그래프/구엔진 선택 — 체크포인터가 안 붙으면 구엔진 폴백
    use_graph = get_settings().interview_engine == "graph" and graph_engine.ready()
    run = graph_engine.next_turn if use_graph else moderator.next_turn
    try:
        message, done, _, mod_turn = run(pid, session, guide, body.text, body.lang)
    except LLMError as e:
        raise HTTPException(502, f"인터뷰 진행에 실패했습니다: {e}") from e

    return TurnOut(
        message=message,
        done=done,
        asked=session.asked,
        is_probe=mod_turn.is_probe,
        guardrail_rewritten=mod_turn.guardrail_rewritten,
        emotion="",
    )


@router.post("/{pid}/sessions/{sid}/submit", response_model=Session)
def submit(pid: str, sid: str) -> Session:
    """R-4 제출 — 이 시점에야 '응답 1건'이 된다.

    진행자가 done 을 냈다고 세션이 완료된 게 아니다. 응답자가 직접 제출해야 completed 로
    넘어가고 집계·인사이트 모수에 들어간다. 중간에 그만두고 제출하는 것도 허용한다(active).
    """
    session = store.get_session(pid, sid)
    if not session:
        raise HTTPException(404, "세션을 찾을 수 없습니다.")
    if session.status == "completed":
        return session   # 멱등 — 재전송·중복 클릭으로 실패시키지 않는다
    if session.status not in ("active", "pending"):
        # consented(한 마디도 안 함) / abandoned — 제출할 답변이 없다.
        raise HTTPException(400, "제출할 답변이 없습니다.")

    from datetime import datetime, timezone

    store.update_session(
        pid, sid, {"status": "completed", "ended_at": datetime.now(timezone.utc)}
    )
    log.info("세션 제출 완료 (project=%s session=%s)", pid, sid)
    return store.get_session(pid, sid) or session
