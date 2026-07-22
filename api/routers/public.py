"""응답자 API — 동의·세션·턴 (R-1 ~ R-4). 무인증(링크 접속).

응답자에게는 프로젝트의 최소 정보만 노출한다. 가이드 문항·다른 응답자 데이터는 주지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from ..config import get_settings
from ..interview import engine as graph_engine
from ..schemas.models import (
    ConsentLog,
    InterviewGuide,
    ScreenIn,
    Session,
    SessionStartIn,
    Stimulus,
    TurnIn,
    TurnOut,
)
from ..services import moderator, notify, store
from ..services.llm_client import LLMError

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/public/projects", tags=["respondent"])


def screener_qualifies(screener: list, answers: dict) -> bool:
    """스크리너 자격 판정(F4.3) — 순수 함수. 게이트 로직을 한 곳에 모아 테스트 가능하게 한다.

    빈 스크리너면 무조건 통과. 그 외에는 **모든** 문항에서 응답자의 답(answers[q.id])이
    그 문항의 pass_options 에 들어야 통과. 답이 없거나(미응답) pass_options 밖이면 탈락.
    AND 조건인 이유: 스크리너는 '모든 자격을 갖춘 사람만' 태우려는 것이라 하나라도 어긋나면 부적격.
    """
    for q in screener:
        if answers.get(q.id) not in (q.pass_options or []):
            return False
    return True


def _public_screener(screener: list) -> list[dict]:
    """응답자에게 내려줄 스크리너 — pass_options 는 벗겨낸다.

    어느 답이 통과인지 노출되면 응답자가 골라 맞출 수 있어 스크리너가 무력화된다.
    id·text·options 만 준다.
    """
    return [{"id": q.id, "text": q.text, "options": list(q.options or [])} for q in screener]


def _question_stimulus(guide: InterviewGuide, qid: str) -> Stimulus | None:
    """진행자가 지금 다루는 가이드 문항에 붙은 제시 자료(있으면 그것, 없으면 None) — 순수 함수.

    url 이 빈 자극물은 '없음'으로 친다: 의뢰자가 캡션만 남기고 URL 을 비운 채 저장하면
    응답자 화면에 빈 액자가 뜨는데, 그럴 바엔 기본 단일 컬럼으로 두는 게 낫다.
    문항은 JSONB 라 마이그레이션 없이 stimulus 를 얹어 여기서 꺼낸다.
    """
    if not qid:
        return None
    q = next((q for q in guide.questions if q.id == qid), None)
    if not q or not q.stimulus or not (q.stimulus.url or "").strip():
        return None
    return q.stimulus


@router.get("/{pid}")
def public_project(pid: str) -> dict:
    """링크 접속 시 보여줄 최소 정보. 스크리너는 통과 조건(pass_options)을 뺀 채로만 내려준다."""
    p = store.get_project(pid)
    if not p:
        raise HTTPException(404, "인터뷰를 찾을 수 없습니다.")
    if p.status != "deployed":
        raise HTTPException(403, "아직 배포되지 않은 인터뷰입니다.")
    return {
        "id": p.id, "title": p.title, "topic": p.topic, "status": p.status,
        "screener": _public_screener(p.screener),
    }


@router.post("/{pid}/screen")
def screen(pid: str, body: ScreenIn) -> dict:
    """F4.3 자격 판정 — 응답자의 스크리너 답으로 적격 여부만 돌려준다(pass_options 는 서버 안에서만).

    무인증이라 판정은 반드시 서버에서 한다 — 클라이언트에 pass_options 를 주지 않는 이유와 같은 계약.
    """
    p = store.get_project(pid)
    if not p:
        raise HTTPException(404, "인터뷰를 찾을 수 없습니다.")
    if p.status != "deployed":
        raise HTTPException(403, "아직 배포되지 않은 인터뷰입니다.")
    return {"qualified": screener_qualifies(p.screener, body.answers)}


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
        # 이번 발화가 다루는 문항의 제시 자료를 함께 내려 응답자 화면이 2분할로 렌더한다.
        # 두 엔진 모두 mod_turn.question_id 를 채우므로 엔진 분기 없이 한 번만 조회한다.
        stimulus=_question_stimulus(guide, mod_turn.question_id),
    )


@router.post("/{pid}/sessions/{sid}/turn/stream")
def turn_stream(pid: str, sid: str, body: TurnIn):
    """R-2 SSE 판 — 토큰을 흘리고 마지막에 meta 이벤트. 구엔진이면 완성문을 단일 흐름으로."""
    session = store.get_session(pid, sid)
    if not session:
        raise HTTPException(404, "세션을 찾을 수 없습니다.")
    if session.status == "completed":
        raise HTTPException(409, "이미 종료된 인터뷰입니다.")
    guide = store.get_guide(pid)
    if not guide:
        raise HTTPException(500, "가이드가 없습니다.")

    use_graph = get_settings().interview_engine == "graph" and graph_engine.ready()

    def _sse(event: dict) -> str:
        return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    def _stim_dump(stim: Stimulus | None) -> dict | None:
        return stim.model_dump() if stim else None

    def gen():
        try:
            if use_graph:
                # 그래프 엔진의 meta 는 내부 핸드오프로 question_id 를 실어 준다 — 여기서 뽑아
                # stimulus 로 바꿔치우고 question_id 자체는 벗겨 낸다(비스트림 TurnOut 처럼 미노출).
                for event in graph_engine.stream_turn(pid, session, guide, body.text, body.lang):
                    meta = event.get("meta") if isinstance(event, dict) else None
                    if isinstance(meta, dict):
                        qid = meta.pop("question_id", "")
                        meta["stimulus"] = _stim_dump(_question_stimulus(guide, qid))
                    yield _sse(event)
            else:
                message, done, _, mod_turn = moderator.next_turn(pid, session, guide, body.text, body.lang)
                yield _sse({"token": message})
                yield _sse({"meta": {"message": message, "done": done, "asked": session.asked,
                                     "is_probe": mod_turn.is_probe,
                                     "guardrail_rewritten": mod_turn.guardrail_rewritten,
                                     "stimulus": _stim_dump(_question_stimulus(guide, mod_turn.question_id))}})
        except LLMError as e:
            yield _sse({"error": f"인터뷰 진행에 실패했습니다: {e}"})

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/{pid}/sessions/{sid}/submit", response_model=Session)
def submit(pid: str, sid: str, background_tasks: BackgroundTasks) -> Session:
    """R-4 제출 — 이 시점에야 '응답 1건'이 된다.

    진행자가 done 을 냈다고 세션이 완료된 게 아니다. 응답자가 직접 제출해야 completed 로
    넘어가고 집계·인사이트 모수에 들어간다. 중간에 그만두고 제출하는 것도 허용한다(active).
    """
    session = store.get_session(pid, sid)
    if not session:
        raise HTTPException(404, "세션을 찾을 수 없습니다.")
    if session.status == "completed":
        return session   # 멱등 — 재전송·중복 클릭으로 실패시키지 않는다(알림도 재발사 안 함)
    if session.status not in ("active", "pending"):
        # consented(한 마디도 안 함) / abandoned — 제출할 답변이 없다.
        raise HTTPException(400, "제출할 답변이 없습니다.")

    from datetime import datetime, timezone

    store.update_session(
        pid, sid, {"status": "completed", "ended_at": datetime.now(timezone.utc)}
    )
    log.info("세션 제출 완료 (project=%s session=%s)", pid, sid)
    # 알림은 백그라운드로 — 응답자 응답을 막지 않는다. 실패해도 제출은 성공이다.
    background_tasks.add_task(notify.emit_session_completed, pid, sid)
    return store.get_session(pid, sid) or session
