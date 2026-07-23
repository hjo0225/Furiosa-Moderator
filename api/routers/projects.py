"""의뢰자 API — 프로젝트·가이드·배포·대시보드 (C-1 ~ C-5).

MVP 무인증이다. PORTING.md '미해결' 항목대로 그대로 공개하면 LLM 호출이 외부에 열린다.
main.py 에 레이트리밋을 뒀지만, 운영 전에 세션 토큰이 반드시 필요하다.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Form, HTTPException, UploadFile

from ..config import get_settings
from ..briefing import pipeline as briefing_pipeline
from ..services.material import MaterialError, compose_guide_material, extract_text

from ..prompts.guide import GUIDE_SYSTEM, guide_user
from ..prompts.insight import (
    INSIGHT_SYSTEM,
    QUESTION_SUMMARY_SYSTEM,
    SESSION_SUMMARY_SYSTEM,
    QuestionSummariesOut,
    insight_user,
    question_summary_user,
    session_summary_user,
)
from ..schemas.models import (
    BlocklistSetIn,
    GuideGenerateIn,
    GuideQuestion,
    Insight,
    InterviewGuide,
    Material,
    Project,
    ProjectCreateIn,
    ResponseBucket,
    ScreenerSetIn,
    WebhookSetIn,
    WebSelectIn,
)
from ..services import store
from ..services import research
from ..services import evals
from ..services.audience import collect_personas
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
    """C-1 조사 브리프 입력·프로젝트 생성 → 상태=draft. 브리프 4개 필드는 모두 필수."""
    required = {
        "조사 목적": body.topic,
        "타깃 대상": body.target,
        "동기": body.motivation,
        "활용 방안": body.utilization,
    }
    missing = [name for name, v in required.items() if not v.strip()]
    if missing:
        raise HTTPException(400, f"{' · '.join(missing)}을(를) 입력하세요.")
    return store.create_project(
        Project(
            topic=body.topic.strip(),
            title=body.title.strip() or body.topic.strip()[:40],
            target=body.target.strip(),
            motivation=body.motivation.strip(),
            utilization=body.utilization.strip(),
            discord_webhook_url=body.discord_webhook_url.strip(),
        )
    )


@router.put("/{pid}/webhook", response_model=Project)
def set_webhook(pid: str, body: WebhookSetIn) -> Project:
    """프로젝트별 Discord 웹훅 override 설정. 빈 문자열이면 기본 채널로 폴백."""
    _require(pid)
    store.update_project(pid, {"discord_webhook_url": body.discord_webhook_url.strip()})
    return _require(pid)


@router.put("/{pid}/screener", response_model=Project)
def set_screener(pid: str, body: ScreenerSetIn) -> Project:
    """F4.3 참가 조건 스크리너 저장. 빈 리스트면 게이트를 없앤다."""
    _require(pid)
    store.update_project(pid, {"screener": [q.model_dump() for q in body.screener]})
    return _require(pid)


@router.put("/{pid}/blocklist", response_model=Project)
def set_blocklist(pid: str, body: BlocklistSetIn) -> Project:
    """F1.5 지식팩 금칙어 저장. 빈/공백 항목은 버리고, 빈 리스트면 금칙어 제약을 없앤다."""
    _require(pid)
    cleaned = [w.strip() for w in body.blocklist if w and w.strip()]
    store.update_project(pid, {"blocklist": cleaned})
    return _require(pid)


@router.get("", response_model=list[Project])
def list_projects() -> list[Project]:
    return store.list_projects()


@router.get("/{pid}", response_model=Project)
def get_project(pid: str) -> Project:
    return _require(pid)


class _GenBucket(ResponseBucket):
    """생성 전용 — definition 을 필수로 승격(F2.3.2). Qwen3 가 통째로 생략하는 걸 막는다."""

    definition: str


class _GenQuestion(GuideQuestion):
    """생성 전용 스키마 — goal·buckets 를 필수로 승격.

    저장·수정용 GuideQuestion 의 goal 은 default("") 라 LLM 스키마에서 required 가 아니고,
    Qwen3 는 required 아닌 필드를 통째로 생략하는 실사고가 났다. 필수로 승격하면
    비워 보낸 응답이 검증에서 떨어져 structured() 의 자가교정 재시도가 발동한다.
    """

    goal: str
    response_buckets: list[_GenBucket]


class _GenGuide(InterviewGuide):
    questions: list[_GenQuestion]


_GOAL_MARKER = "이 질문으로 알아내려는 것"


def _split_goal_from_text(q: GuideQuestion) -> None:
    """모델이 goal 을 text 뒤에 이어 붙여 보내는 실사고 보정(결정론).

    goal 에 default("") 가 있어 스키마 검증은 통과해 버린다 — order/id 확정과
    같은 계열의 서버 보정으로 분리한다. 프롬프트로도 금지하지만 재발 대비 이중 방어.
    """
    if _GOAL_MARKER not in q.text:
        return
    head, _, tail = q.text.partition(_GOAL_MARKER)
    q.text = head.strip().rstrip("·:：-—").strip()
    tail = tail.strip().lstrip(":：").strip()
    if tail and not q.goal.strip():
        q.goal = tail


def _normalize_buckets(q: GuideQuestion) -> None:
    """버킷 id 확정 + 캐치올 보장(F2.3.3). order/id 채우기와 같은 결정론 서버 보정.

    LLM 이 id 를 비워 보내거나 캐치올을 빠뜨리는 실사고 대비. 버킷이 아예 없으면 손대지 않는다
    (구가이드 호환).
    """
    if not q.response_buckets:
        return
    for i, b in enumerate(q.response_buckets):
        b.id = b.id or f"{q.id}_b{i + 1}"
    if not any(b.is_catchall for b in q.response_buckets):
        # LLM 이 캐치올 표시 없이 '기타' 류를 만든 경우: 중복 추가 대신 그걸 캐치올로 승격
        catchall_labels = {"기타", "그 외", "기타/모름", "해당 없음", "없음"}
        existing = next(
            (b for b in q.response_buckets if b.label.strip() in catchall_labels), None
        )
        if existing:
            existing.is_catchall = True
        else:
            q.response_buckets.append(
                ResponseBucket(id=f"{q.id}_other", label="기타", is_catchall=True)
            )


def _collect_evidence(pid: str, p) -> str:
    """가이드 생성용 RAG 근거 — 슬롯별 1쿼리로 검색해 dedup·cap(9)·라인 포맷.

    research.py 의 슬롯별 폴백 문구를 재사용한다. RAG 실패가 가이드 생성을 죽이면
    안 되므로(레포 관례) 각 검색을 try/except 로 감싸 실패 슬롯은 건너뛴다.
    search_chunks 는 순환 임포트 회피로 로컬 임포트.
    """
    if not store.list_materials(pid):   # 자료 없으면 임베딩 호출 없이 빠진다(불필요 네트워크 방지)
        return ""
    from ..briefing.pipeline import search_chunks

    queries: list[tuple[str, str]] = [
        ("현상", f"{p.topic} {p.target}".strip()),
        ("원인", f"{p.topic} 이유 원인"),
    ]
    if p.utilization.strip():
        queries.append(("활용", f"{p.utilization} 사례".strip()))

    lines: list[str] = []
    seen: set[str] = set()
    for slot, q in queries:
        if not q:
            continue
        try:
            hits = search_chunks(pid, q, k=3, angle=slot)
        except Exception:  # noqa: BLE001 — RAG 장애가 가이드 생성을 막아선 안 된다
            log.warning("evidence 검색 실패 (project=%s slot=%s)", pid, slot, exc_info=True)
            hits = []
        for h in hits:
            text = h["text"]
            if text in seen:
                continue
            seen.add(text)
            lines.append(f"- {text} (출처: {h['source']})")
    return "\n".join(lines[:9])


@router.post("/{pid}/guide", response_model=InterviewGuide)
def generate_guide(pid: str, body: GuideGenerateIn) -> InterviewGuide:
    """C-2 가이드 자동 생성."""
    p = _require(pid)
    topic = body.topic.strip() or p.topic
    target = body.target.strip() or p.target
    material = compose_guide_material(store.get_slot_summaries(pid))
    evidence = _collect_evidence(pid, p)
    audience = collect_personas(p)   # 글로벌 페르소나 풀 → [대상 청중](코퍼스 비면 "")
    try:
        guide, _ = get_llm().structured(
            GUIDE_SYSTEM,
            guide_user(topic, target, material, p.motivation, p.utilization,
                       evidence=evidence, audience=audience),
            _GenGuide,  # goal 필수 스키마 — 비워 보내면 자가교정 재시도가 발동
            max_tokens=2000,
            timeout=get_settings().llm_guide_timeout,   # 무거운 단발 생성 — 인터뷰 30s 와 분리
        )
    except LLMError as e:
        raise HTTPException(502, f"가이드 생성에 실패했습니다: {e}") from e

    # 모델이 order/id 를 비워 보낼 수 있어 서버에서 확정한다. goal 이 text 에 박혀 오는
    # 사고도 여기서 결정론으로 분리한다.
    for i, q in enumerate(guide.questions):
        _split_goal_from_text(q)
        q.order = i
        q.id = q.id or f"q{i + 1}"
        _normalize_buckets(q)
    guide.goal = guide.goal or topic

    # 비차단 품질 로그 (F8) — 매 생성마다 유도신문·버킷 MECE 를 오프라인 규칙으로 자기평가한다.
    # 로그 전용이다: 반환 가이드를 바꾸지 않고, eval 이 던져도 생성을 막지 않는다.
    try:
        report = evals.guide_quality_report(guide)
        if report["n_leading"] or report["bucket_warnings"]:
            log.warning(
                "guide quality: project=%s n_questions=%d n_leading=%d leading=%s bucket_warnings=%s",
                pid,
                report["n_questions"],
                report["n_leading"],
                report["leading"],
                report["bucket_warnings"],
            )
    except Exception:  # noqa: BLE001 — 품질 로그가 가이드 생성을 막아선 안 된다
        log.warning("guide quality eval 실패", exc_info=True)

    return store.save_guide(pid, guide)


@router.post("/{pid}/research")
def research_candidates(pid: str) -> dict:
    """웹 리서치 — 브리프로 검색어 생성 → SERP 후보 반환(크롤 전·미저장)."""
    p = _require(pid)
    slot_queries = research.research_queries(p.topic, p.target, p.motivation, p.utilization)
    try:
        cands = research.search(slot_queries)
    except research.ResearchError as e:
        raise HTTPException(502, f"웹 검색에 실패했습니다: {e}") from e
    return {"candidates": [
        {"angle": c.angle, "title": c.title, "url": c.url, "snippet": c.snippet}
        for c in cands
    ]}


@router.post("/{pid}/materials/web")
def add_web_materials(pid: str, body: WebSelectIn) -> dict:
    """선택 후보 크롤 → materials 저장 → 증분 인덱싱·요약. 중복 URL(요청 내·기존 풀)은 건너뛴다."""
    _require(pid)
    if not body.selected:
        raise HTTPException(400, "선택된 자료가 없습니다.")
    existing = {m.url for m in store.list_materials(pid) if m.url}
    picked: list = []
    seen: set[str] = set()
    skipped: list[str] = []
    for c in body.selected:
        if not c.url:
            continue
        if c.url in existing or c.url in seen:
            skipped.append(c.url)
            continue
        seen.add(c.url)
        picked.append(c)
    if not picked:
        return {"stored": 0, "failed": [], "skipped": skipped}    # 전부 중복/무효
    try:
        bodies = research.crawl([c.url for c in picked])
    except research.ResearchError as e:
        raise HTTPException(502, f"본문 수집에 실패했습니다: {e}") from e
    created: list = []
    failed: list[str] = []
    for c in picked:
        text = (bodies.get(c.url) or "").strip()
        if not text:
            failed.append(c.url)                # 크롤 실패분(같은 루프에서 판정)
            continue
        created.append(store.create_material(Material(
            project_id=pid, source="web", angle=c.angle,
            url=c.url, title=c.title or c.url, text=text,
        )))
    if created:                                  # 저장분 있을 때만 후처리
        briefing_pipeline.add_materials_incremental(pid, created)
    return {"stored": len(created), "failed": failed, "skipped": skipped}


_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10MB


@router.post("/{pid}/material")
async def upload_material(pid: str, file: UploadFile, angle: str = Form(...)) -> dict:
    """수동 업로드 → materials 풀에 저장(유저가 슬롯 지정). RAG 재인덱싱·요약."""
    _require(pid)
    if angle not in ("현상", "원인", "활용"):
        raise HTTPException(400, "슬롯(angle)은 현상·원인·활용 중 하나여야 합니다.")
    raw = await file.read()
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(400, "파일이 너무 큽니다(최대 10MB).")
    try:
        text = extract_text(file.filename or "", raw)
    except MaterialError as e:
        raise HTTPException(400, str(e)) from e
    if not text.strip():
        raise HTTPException(400, "자료에서 텍스트를 추출하지 못했습니다(스캔 PDF 등).")
    m = store.create_material(Material(
        project_id=pid, source="upload", angle=angle,
        title=file.filename or "업로드", text=text,
    ))
    briefing_pipeline.add_materials_incremental(pid, [m])
    return {"project_id": pid, "chars": len(text), "angle": angle}


@router.get("/{pid}/materials")
def list_project_materials(pid: str) -> list[dict]:
    """현재 자료 풀 목록(폼 재방문 표시용). 본문(text)은 제외."""
    _require(pid)
    return [
        {"id": m.id, "source": m.source, "angle": m.angle, "title": m.title, "url": m.url}
        for m in store.list_materials(pid)
    ]


@router.delete("/{pid}/materials/{mid}")
def remove_material(pid: str, mid: str) -> dict:
    """자료 풀에서 삭제 → RAG 재인덱싱·요약 재계산."""
    _require(pid)
    store.delete_material(pid, mid)
    briefing_pipeline.refresh_project(pid)
    return {"deleted": mid}


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


@router.post("/{pid}/briefing/index")
def briefing_index(pid: str) -> dict:
    """업로드 자료를 브리핑 팩으로 인덱싱 (청크→임베딩→pgvector). 멱등."""
    if not store.get_project(pid):
        raise HTTPException(404, "프로젝트를 찾을 수 없습니다.")
    try:
        n = briefing_pipeline.index_project(pid)
    except Exception as e:
        raise HTTPException(502, f"브리핑 인덱싱에 실패했습니다: {e}") from e
    if n == 0:
        raise HTTPException(400, "인덱싱할 업로드 자료가 없습니다.")
    return {"chunks": n}


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


def _answers_by_question(turns_by_session: list[list]) -> dict[str, list[str]]:
    """완료 세션들의 응답자 턴을 question_id 별로 묶는다 — 문항별 요약(F6.3)의 입력.

    빈 텍스트·빈 question_id 는 제외한다. '세는' 게 아니라 '무엇을 말했나'를 모으는 것뿐이라
    LLM 해석 출력 계열이다(계약 1 의 개수 집계와 무관 — 그건 store.bucket_distribution 이 한다).
    세션·문항 순서를 보존해 요약 입력이 결정론적으로 만들어지게 한다.
    """
    grouped: dict[str, list[str]] = {}
    for turns in turns_by_session:
        for t in turns:
            if t.role != "respondent":
                continue
            qid = (t.question_id or "").strip()
            text = (t.text or "").strip()
            if not qid or not text:
                continue
            grouped.setdefault(qid, []).append(text)
    return grouped


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
    # 문항별 응답 버킷 분포도 DB 실측으로 채운다(F6.4) — sentiment 와 같은 계약 1.
    insight.bucket_distribution = store.bucket_distribution(pid)
    insight.session_count = len(summaries)

    # 문항별 AI 요약(F6.3) — 여기부터는 LLM '해석' 출력이다(theme 요약과 같은 계열).
    # 위 DB 실측 카운트는 절대 건드리지 않는다. best-effort: 실패해도 인사이트 전체를
    # 막지 않고 문항 요약만 비운 채 진행한다.
    grouped = _answers_by_question([store.list_turns(pid, s.id) for s in sessions])
    if grouped:
        questions = guide.questions if guide else []
        items = [
            {"question_id": q.id, "question_text": q.text, "answers": grouped[q.id]}
            for q in questions
            if grouped.get(q.id)
        ]
        if items:
            try:
                qs_out, _ = llm.structured(
                    QUESTION_SUMMARY_SYSTEM,
                    question_summary_user(items),
                    QuestionSummariesOut,
                    max_tokens=3000,
                )
                insight.question_summaries = qs_out.items
            except LLMError as e:
                log.warning("문항별 요약 생성 실패 (project=%s): %s", pid, e)

    return store.save_insight(pid, insight)


@router.get("/{pid}/stats")
def stats(pid: str) -> dict:
    """가이드 커버리지·probing 비율·가드레일 발동 수 — 벤치마크용 실측(PRD 3절 지표)."""
    _require(pid)
    return store.coverage_stats(pid)
