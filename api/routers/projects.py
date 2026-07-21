"""의뢰자 API — 프로젝트·가이드·배포·대시보드 (C-1 ~ C-5).

MVP 무인증이다. PORTING.md '미해결' 항목대로 그대로 공개하면 LLM 호출이 외부에 열린다.
main.py 에 레이트리밋을 뒀지만, 운영 전에 세션 토큰이 반드시 필요하다.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException, UploadFile

from ..services.material import SUMMARIZE_THRESHOLD, MaterialError, cap, extract_text

from ..prompts.guide import GUIDE_SYSTEM, guide_user
from ..prompts.material import MATERIAL_SUMMARY_SYSTEM, material_summary_user
from ..prompts.insight import (
    INSIGHT_SYSTEM,
    SESSION_SUMMARY_SYSTEM,
    insight_user,
    session_summary_user,
)
from ..schemas.models import (
    GuideGenerateIn,
    Insight,
    InterviewGuide,
    Project,
    ProjectCreateIn,
    WebhookSetIn,
)
from ..services import store
from ..services.llm_client import LLMError, get_llm

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects", tags=["client"])


def _require(pid: str) -> Project:
    p = store.get_project(pid)
    if not p:
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
    return p


@router.post("", response_model=Project)
def create_project(body: ProjectCreateIn) -> Project:
    """C-1 주제 입력·프로젝트 생성 → 상태=draft."""
    if not body.topic.strip():
        raise HTTPException(400, "주제를 입력하세요.")
    return store.create_project(
        Project(topic=body.topic.strip(), title=body.title.strip() or body.topic.strip()[:40],
                target=body.target.strip(), discord_webhook_url=body.discord_webhook_url.strip())
    )


@router.put("/{pid}/webhook", response_model=Project)
def set_webhook(pid: str, body: WebhookSetIn) -> Project:
    """프로젝트별 Discord 웹훅 override 설정. 빈 문자열이면 기본 채널로 폴백."""
    _require(pid)
    store.update_project(pid, {"discord_webhook_url": body.discord_webhook_url.strip()})
    return _require(pid)


@router.get("", response_model=list[Project])
def list_projects() -> list[Project]:
    return store.list_projects()


@router.get("/{pid}", response_model=Project)
def get_project(pid: str) -> Project:
    return _require(pid)


@router.post("/{pid}/guide", response_model=InterviewGuide)
def generate_guide(pid: str, body: GuideGenerateIn) -> InterviewGuide:
    """C-2 가이드 자동 생성."""
    p = _require(pid)
    topic = body.topic.strip() or p.topic
    target = body.target.strip() or p.target
    try:
        guide, _ = get_llm().structured(
            GUIDE_SYSTEM, guide_user(topic, target, p.material_text), InterviewGuide, max_tokens=2000
        )
    except LLMError as e:
        raise HTTPException(502, f"가이드 생성에 실패했습니다: {e}") from e

    # 모델이 order/id 를 비워 보낼 수 있어 서버에서 확정한다.
    for i, q in enumerate(guide.questions):
        q.order = i
        q.id = q.id or f"q{i + 1}"
    guide.goal = guide.goal or topic
    return store.save_guide(pid, guide)


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB


@router.post("/{pid}/material")
async def upload_material(pid: str, file: UploadFile) -> dict:
    """C-2 보조: 도메인 자료 업로드 → 가이드 생성 프롬프트에 주입(선택 스텝).

    자료가 SUMMARIZE_THRESHOLD 를 넘으면 자르는 대신 LLM 으로 요약해 저장한다
    (자르면 뒷부분 도메인 맥락이 통째로 사라지므로). 요약이 실패해도 업로드는 죽지 않고
    cap() 자르기로 후퇴한다.
    """
    _require(pid)
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(400, "파일이 너무 큽니다(최대 10MB).")
    try:
        text = extract_text(file.filename or "", raw)
    except MaterialError as e:
        raise HTTPException(400, str(e)) from e

    summarized = False
    if len(text) > SUMMARIZE_THRESHOLD:
        try:
            text, _ = get_llm().text(
                MATERIAL_SUMMARY_SYSTEM, material_summary_user(text), max_tokens=2048
            )
            summarized = True
        except LLMError as e:
            log.warning("자료 요약 실패, 자르기로 후퇴 (project=%s): %s", pid, e)

    # 요약을 건너뛰었거나 요약본이 여전히 길 경우의 최종 상한.
    text, truncated = cap(text)
    store.update_project(pid, {"material_text": text})
    return {"project_id": pid, "chars": len(text), "truncated": truncated, "summarized": summarized}


@router.get("/{pid}/guide", response_model=InterviewGuide)
def get_guide(pid: str) -> InterviewGuide:
    _require(pid)
    g = store.get_guide(pid)
    if not g:
        raise HTTPException(404, "가이드가 아직 없습니다. 먼저 생성하세요.")
    return g


@router.put("/{pid}/guide", response_model=InterviewGuide)
def update_guide(pid: str, body: InterviewGuide) -> InterviewGuide:
    """C-2 의뢰자 수정본 저장."""
    _require(pid)
    prev = store.get_guide(pid)
    body.version = (prev.version + 1) if prev else 1
    for i, q in enumerate(body.questions):
        q.order = i
        q.id = q.id or f"q{i + 1}"
    return store.save_guide(pid, body)


@router.post("/{pid}/deploy")
def deploy(pid: str) -> dict:
    """C-3 배포·링크 발급. 가이드 없이는 배포할 수 없다."""
    _require(pid)
    if not store.get_guide(pid):
        raise HTTPException(400, "가이드를 먼저 생성·승인하세요.")
    store.update_project(pid, {"status": "deployed"})
    base = os.environ.get("PUBLIC_WEB_BASE", "").rstrip("/")
    return {"project_id": pid, "url": f"{base}/i/{pid}" if base else f"/i/{pid}"}


@router.get("/{pid}/dashboard")
def dashboard(pid: str) -> dict:
    """C-4 누적 열람."""
    p = _require(pid)
    return {
        "project": p.model_dump(mode="json"),
        "sessions": [s.model_dump(mode="json") for s in store.list_sessions(pid)],
        "insight": (i.model_dump(mode="json") if (i := store.get_insight(pid)) else None),
    }


@router.get("/{pid}/sessions/{sid}/turns")
def session_turns(pid: str, sid: str) -> list[dict]:
    _require(pid)
    return [t.model_dump(mode="json") for t in store.list_turns(pid, sid)]


@router.post("/{pid}/insight", response_model=Insight)
def build_insight(pid: str) -> Insight:
    """M-4 요약·집계. 완료 세션의 요약을 모아 프로젝트 인사이트를 만든다."""
    p = _require(pid)
    guide = store.get_guide(pid)
    goal = guide.goal if guide else p.topic
    sessions = [s for s in store.list_sessions(pid) if s.status == "completed"]
    if not sessions:
        raise HTTPException(400, "완료된 인터뷰가 아직 없습니다.")

    llm = get_llm()
    summaries: list[str] = []
    for s in sessions:
        if s.summary:
            summaries.append(s.summary)
            continue
        turns = store.list_turns(pid, s.id)
        if not turns:
            continue
        transcript = "\n".join(
            f"{'진행자' if t.role == 'moderator' else '응답자'}: {t.text}" for t in turns
        )
        try:
            summary, _ = llm.text(
                SESSION_SUMMARY_SYSTEM, session_summary_user(goal, transcript), max_tokens=500
            )
        except LLMError as e:
            log.warning("세션 요약 실패 (%s): %s", s.id, e)
            continue
        store.update_session(pid, s.id, {"summary": summary})
        summaries.append(summary)

    if not summaries:
        raise HTTPException(502, "세션 요약 생성에 모두 실패했습니다.")

    try:
        insight, _ = llm.structured(
            INSIGHT_SYSTEM, insight_user(p.topic, summaries), Insight, max_tokens=3000
        )
    except LLMError as e:
        raise HTTPException(502, f"집계 생성에 실패했습니다: {e}") from e

    # overall 이 비는 경우가 실제로 나온다(구조화 출력에서 긴 필드가 누락).
    # 대시보드 최상단이라 비어 있으면 티가 크다 — 텍스트 호출로 한 번 더 받는다.
    if not (insight.overall or "").strip():
        log.warning("insight.overall 이 비어 재생성 (project=%s)", pid)
        try:
            insight.overall, _ = llm.text(
                SESSION_SUMMARY_SYSTEM,
                insight_user(p.topic, summaries) + "\n\n위 응답 전체를 3~5문장으로 요약하세요.",
                max_tokens=600,
            )
        except LLMError as e:
            log.warning("overall 재생성 실패: %s", e)

    # LLM 이 낸 '숫자'는 버리고 DB 실측으로 덮어쓴다.
    # 주제·요약·인용 같은 해석은 LLM 이 잘하지만, 세는 일은 LLM 에게 맡기면 안 된다.
    # 응답자가 수십 명이 되면 눈대중 카운트는 틀리고, 심사에서 검증도 불가능하다.
    insight.sentiment = store.sentiment_counts(pid)
    mentions = store.theme_mention_counts(
        pid, {t.theme: t.keywords for t in insight.themes}
    )
    for t in insight.themes:
        t.mention_count = mentions.get(t.theme, 0)
    insight.session_count = len(summaries)
    return store.save_insight(pid, insight)


@router.get("/{pid}/stats")
def stats(pid: str) -> dict:
    """가이드 커버리지·probing 비율·가드레일 발동 수 — 벤치마크용 실측(PRD 3절 지표)."""
    _require(pid)
    return store.coverage_stats(pid)
