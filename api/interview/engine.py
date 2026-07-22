"""그래프 엔진 파사드 — moderator.next_turn 과 동일한 계약.

라우터는 INTERVIEW_ENGINE 플래그로 이 모듈과 구엔진 중 하나를 고른다.
PII 마스킹·응답자 턴 저장·감정 태깅은 그래프 진입 전(여기)에서 — 전역 불변식.
Command(resume=…) 에는 마스킹된 발화만 들어간다(체크포인트에 박제되므로).
"""
from __future__ import annotations

import logging
from functools import lru_cache

from langgraph.types import Command

from ..schemas.models import InterviewGuide, Session, Turn
from ..services import store
from ..services.moderator import _question_part, is_non_answer
from ..services.pii import mask_pii, scan_pii
from .checkpoint import get_checkpointer
from .graph import build_graph
from .state import init_ledger

log = logging.getLogger(__name__)


@lru_cache
def get_graph():
    return build_graph(get_checkpointer())


def ready() -> bool:
    """그래프 엔진 가용성 — 체크포인터 연결 실패 시 False (라우터가 구엔진 폴백)."""
    try:
        get_graph()
        return True
    except Exception as e:
        log.warning("그래프 엔진 비활성 (체크포인터 실패): %s", e)
        return False


def initial_state(project_id: str, sid: str, lang: str, guide: InterviewGuide, session: Session) -> dict:
    """그래프 시작 상태 — 테스트와 엔진이 같은 빌더를 쓴다."""
    gd = guide.model_dump()
    return {
        "project_id": project_id, "session_id": sid, "lang": lang, "guide": gd,
        "messages": [], "ledger": init_ledger(gd),
        "covered": list(session.covered), "asked": session.asked, "probe_streak": 0,
    }


def _non_answer_reply(project_id: str, sid: str, text: str) -> Turn | None:
    """추임새뿐인 발화면 되물을 진행자 턴을 만든다 — 저장 안 함·그래프 안 깨움(레거시 계약)."""
    if not text or not is_non_answer(text):
        return None
    prev = next(
        (t for t in reversed(store.list_turns(project_id, sid)) if t.role == "moderator"), None
    )
    if not (prev and prev.text):
        return None
    message = f"앗, 잘 못 들었어요. 다시 여쭤볼게요. {_question_part(prev.text)}"
    return Turn(role="moderator", text=message, question_id=prev.question_id)


def _prepare(
    project_id: str, session: Session, guide: InterviewGuide, text: str, lang: str
) -> tuple:
    """next_turn/stream_turn 공통 준비 — 그래프 핸들·config·payload(재개|시작)·저장된 응답자 턴.

    PII 마스킹→응답자 턴 저장이 그래프 진입 '전'이라는 전역 불변식의 단일 지점.
    emotion 은 슬로우패스(reflect_emotion)가 사후 기입하므로 여기선 비워서 저장한다.
    """
    g = get_graph()
    sid = session.id
    config = {"configurable": {"thread_id": sid}}

    respondent_turn: Turn | None = None
    masked = ""
    if text:
        pii_types = scan_pii(text)
        masked = mask_pii(text)
        respondent_turn = store.add_turn(project_id, sid, Turn(
            role="respondent", text=masked, pii_types=pii_types,
        ))

    if g.get_state(config).next:          # interrupt 에서 잠들어 있다 → 재개
        payload = Command(resume={"text": masked,
                                  "turn_id": respondent_turn.id if respondent_turn else ""})
    else:                                 # 첫 호출 → 그래프 시작(오프닝)
        payload = initial_state(project_id, sid, lang, guide, session)
    return g, config, payload, respondent_turn


def next_turn(
    project_id: str, session: Session, guide: InterviewGuide, respondent_text: str, lang: str = "ko"
) -> tuple[str, bool, Turn | None, Turn]:
    """moderator.next_turn 과 동일 반환: (발화, 종료, 응답자턴|None, 진행자턴)."""
    text = (respondent_text or "").strip()

    # 무의미 발화 단락 — 그래프 기동(get_graph) 전에 처리해야 잠든 실행을 건드리지 않는다
    retry = _non_answer_reply(project_id, session.id, text)
    if retry is not None:
        log.info("무의미 발화 — 그래프를 깨우지 않고 되묻는다 (session=%s)", session.id)
        return retry.text, False, None, retry

    g, config, payload, respondent_turn = _prepare(project_id, session, guide, text, lang)
    result = g.invoke(payload, config)

    message = result.get("message", "")
    done = bool(result.get("done"))
    session.covered = list(result.get("covered", session.covered))
    session.asked = int(result.get("asked", session.asked))
    moderator_turn = Turn(
        role="moderator", text=message,
        is_probe=bool(result.get("is_probe")),
        question_id=result.get("question_id", ""),
        guardrail_rewritten=bool(result.get("rewritten")),
    )
    return message, done, respondent_turn, moderator_turn


def stream_turn(
    project_id: str, session: Session, guide: InterviewGuide, respondent_text: str, lang: str = "ko"
):
    """SSE 용 제너레이터 — {"token": ...}* 뒤 {"meta": {...}} 하나.

    토큰이 다 나간 뒤 reflect(슬로우패스)가 도는 동안에도 스트림만 열려 있을 뿐
    사용자는 이미 질문을 받았다 — 슬로우패스를 사람의 시간에 숨기는 지점.
    """
    text = (respondent_text or "").strip()
    retry = _non_answer_reply(project_id, session.id, text)
    if retry is not None:
        log.info("무의미 발화 — 그래프를 깨우지 않고 되묻는다 (session=%s)", session.id)
        yield {"token": retry.text}
        # question_id 는 라우터가 제시 자료를 조회한 뒤 벗겨 내는 내부 핸드오프다(응답자엔 미노출).
        yield {"meta": {"message": retry.text, "done": False, "asked": session.asked,
                        "is_probe": False, "guardrail_rewritten": False,
                        "question_id": retry.question_id}}
        return

    g, config, payload, _ = _prepare(project_id, session, guide, text, lang)
    for chunk in g.stream(payload, config, stream_mode="custom"):
        if isinstance(chunk, dict) and "token" in chunk:
            yield {"token": chunk["token"]}

    result = g.get_state(config).values
    session.covered = list(result.get("covered", session.covered))
    session.asked = int(result.get("asked", session.asked))
    # question_id 는 라우터가 제시 자료를 조회한 뒤 벗겨 내는 내부 핸드오프다(응답자엔 미노출).
    yield {"meta": {"message": result.get("message", ""), "done": bool(result.get("done")),
                    "asked": session.asked, "is_probe": bool(result.get("is_probe")),
                    "guardrail_rewritten": bool(result.get("rewritten")),
                    "question_id": result.get("question_id", "")}}
