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
from ..services.moderator import tag_emotion
from ..services.pii import mask_pii, scan_pii
from .checkpoint import get_checkpointer
from .graph import build_graph

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


def next_turn(
    project_id: str, session: Session, guide: InterviewGuide, respondent_text: str, lang: str = "ko"
) -> tuple[str, bool, Turn | None, Turn]:
    """moderator.next_turn 과 동일 반환: (발화, 종료, 응답자턴|None, 진행자턴)."""
    g = get_graph()
    sid = session.id
    config = {"configurable": {"thread_id": sid}}

    respondent_turn: Turn | None = None
    masked = ""
    text = (respondent_text or "").strip()
    if text:
        pii_types = scan_pii(text)
        masked = mask_pii(text)
        emotion, conf = tag_emotion(masked)
        respondent_turn = store.add_turn(project_id, sid, Turn(
            role="respondent", text=masked, emotion=emotion,
            emotion_confidence=conf, pii_types=pii_types,
        ))

    if g.get_state(config).next:          # interrupt 에서 잠들어 있다 → 재개
        result = g.invoke(Command(resume=masked), config)
    else:                                 # 첫 호출 → 그래프 시작(오프닝)
        result = g.invoke(
            {"project_id": project_id, "session_id": sid, "lang": lang,
             "guide": guide.model_dump(), "covered": list(session.covered),
             "asked": session.asked},
            config,
        )

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
