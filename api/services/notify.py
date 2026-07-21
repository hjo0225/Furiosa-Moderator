"""n8n 경유 아웃바운드 알림.

응답자가 인터뷰를 제출(completed)할 때 세션의 요약·감정·커버리지·전사 합본을
n8n 웹훅으로 emit 한다. n8n 이 Discord embed 로 게시한다.

원칙: 알림은 본류(인터뷰)를 절대 막지 않는다. 전사는 이미 마스킹된 turns.text 만 쓴다.
"""
from __future__ import annotations

import hashlib
import logging
import time

import httpx

from ..config import Settings, get_settings
from ..prompts.insight import SESSION_SUMMARY_SYSTEM, session_summary_user
from ..schemas.models import Session, Turn
from ..services import store
from ..services.llm_client import LLMError, get_llm

log = logging.getLogger(__name__)


def _respondent_ref(respondent_id: str) -> str:
    """원 식별자 대신 짧은 해시. 원 식별자·PII 미노출."""
    if not respondent_id:
        return ""
    return hashlib.sha256(respondent_id.encode("utf-8")).hexdigest()[:12]


def _transcript(turns: list[Turn]) -> str:
    """마스킹된 문답 합본. build_insight 과 같은 표기."""
    return "\n".join(
        f"{'진행자' if t.role == 'moderator' else '응답자'}: {t.text}" for t in turns
    )


def _emotion_counts(turns: list[Turn]) -> dict[str, int]:
    """이 세션 응답자 턴의 감정 라벨 카운트(빈 라벨 제외)."""
    out: dict[str, int] = {}
    for t in turns:
        if t.role == "respondent" and t.emotion:
            out[t.emotion] = out.get(t.emotion, 0) + 1
    return out


def _duration_sec(session: Session) -> int | None:
    if not session.ended_at:
        return None
    return int((session.ended_at - session.started_at).total_seconds())


def _generate_summary(goal: str, transcript: str) -> str | None:
    """세션 요약 1회 생성. 실패하면 None (best-effort)."""
    if not transcript.strip():
        return None
    try:
        summary, _ = get_llm().text(
            SESSION_SUMMARY_SYSTEM, session_summary_user(goal, transcript), max_tokens=500
        )
        return summary or None
    except LLMError as e:
        log.warning("세션 요약 생성 실패: %s", e)
        return None


def _build_payload(pid: str, sid: str, settings: Settings) -> dict | None:
    """이벤트 payload 구성. 세션이 없으면 None."""
    session = store.get_session(pid, sid)
    if not session:
        return None
    project = store.get_project(pid)
    guide = store.get_guide(pid)
    turns = store.list_turns(pid, sid)

    transcript = _transcript(turns)
    goal = (guide.goal if guide else "") or (project.topic if project else "")

    summary = _generate_summary(goal, transcript)
    if summary:
        store.update_session(pid, sid, {"summary": summary})   # 나중 insight 빌드도 재사용

    total_questions = len(guide.questions) if guide else 0
    web_base = (settings.public_web_base or "").rstrip("/")

    return {
        "event": "session.completed",
        "project": {
            "id": pid,
            "title": project.title if project else "",
            "topic": project.topic if project else "",
        },
        "session": {
            "id": sid,
            "respondent_ref": _respondent_ref(session.respondent_id),
            "asked": session.asked,
            "duration_sec": _duration_sec(session),
        },
        "metrics": {
            "emotion": _emotion_counts(turns),
            "coverage": {"covered": list(session.covered), "total": total_questions},
        },
        "summary": summary,
        "transcript": transcript,
        "dashboard_url": f"{web_base}/projects/{pid}" if web_base else f"/projects/{pid}",
    }


_TIMEOUT = 5.0
_MAX_ATTEMPTS = 3   # 최초 1회 + 2회 재시도


def _post(url: str, payload: dict) -> None:
    """n8n 웹훅으로 POST. 타임아웃·재시도. 최종 실패는 예외로 올린다(호출부가 흡수)."""
    last: Exception | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            r = httpx.post(url, json=payload, timeout=_TIMEOUT)
            r.raise_for_status()
            return
        except Exception as e:   # noqa: BLE001 — 네트워크 오류 전부
            last = e
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(0.5 * (2 ** attempt))   # 0.5s, 1s 백오프
    raise last if last else RuntimeError("알림 전송 실패")


def emit_session_completed(pid: str, sid: str) -> None:
    """제출 완료 알림 진입점. 백그라운드에서 호출된다.

    URL 미설정이면 조용히 skip. 어떤 예외도 밖으로 던지지 않는다 —
    알림 실패가 인터뷰를 깨선 안 된다.
    """
    settings = get_settings()
    if not settings.n8n_webhook_url:
        log.debug("N8N_WEBHOOK_URL 미설정 — 알림 skip (project=%s session=%s)", pid, sid)
        return
    try:
        payload = _build_payload(pid, sid, settings)
        if payload is None:
            log.warning("알림 payload 없음 — 세션 미발견 (project=%s session=%s)", pid, sid)
            return
        _post(settings.n8n_webhook_url, payload)
        log.info("n8n 알림 전송 (project=%s session=%s)", pid, sid)
    except Exception as e:   # noqa: BLE001 — 알림은 본류를 막지 않는다
        # 예외 문자열에 webhook URL 이 섞일 수 있어 타입·상태코드만 남긴다(시크릿 노출 금지).
        status = getattr(getattr(e, "response", None), "status_code", "")
        log.warning("n8n 알림 실패 (project=%s session=%s): %s %s", pid, sid, type(e).__name__, status)
