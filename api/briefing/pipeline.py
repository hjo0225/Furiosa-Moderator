"""브리핑 팩 인덱싱 — 업로드 자료(material_text) → 청크 → 임베딩 → pgvector.

단순 파이프라인이라 LangGraph 불필요(계획 §3.4 규칙). 입구는 팀원의 material
업로드를 재활용한다 — 웹 자동 리서치·승인 게이트는 라이트 판에서 컷.
"""
from __future__ import annotations

import logging

from sqlalchemy import Numeric, cast, delete, or_, select

from ..services.db import BriefingChunkRow, KnowledgeChunkRow, db_session
from ..services.embeddings import embed_texts
from ..services.store import new_id

log = logging.getLogger(__name__)


def chunk_text(text: str, size: int = 500, overlap: int = 80) -> list[str]:
    """문단 우선 분할, 긴 문단은 size/overlap 슬라이딩. 공백 청크 제거."""
    chunks: list[str] = []
    for para in (p.strip() for p in (text or "").split("\n\n")):
        if not para:
            continue
        if len(para) <= size:
            chunks.append(para)
            continue
        step = size - overlap
        for i in range(0, len(para), step):
            piece = para[i:i + size]
            if piece.strip():
                chunks.append(piece)
            if i + size >= len(para):
                break
    return chunks


def chunks_with_angle(materials) -> list[tuple[int, str, str, str]]:
    """자료 리스트 → (seq, 청크텍스트, angle, source) 목록. 순수 함수."""
    out: list[tuple[int, str, str, str]] = []
    seq = 0
    for m in materials:
        src = m.title or m.url or m.source
        for c in chunk_text(m.text):
            out.append((seq, c, m.angle, src))
            seq += 1
    return out


def index_project(pid: str) -> int:
    """멱등 인덱싱 — 기존 청크를 지우고 materials 전체로 다시 적재. 반환 = 청크 수.

    입구가 material_text 단일 문자열에서 materials 여러 행으로 넓어졌다(웹 리서치 통합).
    각 청크에 그 자료의 angle 을 실어 저장한다(슬롯 필터 검색용).
    """
    from ..services.store import list_materials

    rows = chunks_with_angle(list_materials(pid))
    with db_session() as s:
        s.execute(delete(BriefingChunkRow).where(BriefingChunkRow.project_id == pid))
        if not rows:
            s.commit()
            return 0
        vecs = embed_texts([r[1] for r in rows])
        for (seq, text, angle, source), v in zip(rows, vecs):
            s.add(BriefingChunkRow(id=new_id("b_"), project_id=pid, seq=seq,
                                   text=text, source=source, angle=angle, embedding=v))
        s.commit()
    log.info("브리핑 인덱싱 완료 (project=%s, chunks=%d)", pid, len(rows))
    return len(rows)


def search_chunks(pid: str, query: str, k: int = 3, *,
                  angle: str | None = None, candidates: int = 12) -> list[dict]:
    """2단 검색 — 코사인으로 candidates 개 넓게 뽑고 리랭커로 top-k 재정렬.

    angle 이 주어지면 그 슬롯으로 하드필터(WHERE). 리랭커 실패(LLMError)면 코사인
    순서 그대로 top-k 반환(best-effort — 검색이 리랭커 장애로 죽지 않게).
    """
    qv = embed_texts([query])[0]
    with db_session() as s:
        dist = BriefingChunkRow.embedding.cosine_distance(qv)
        stmt = (select(BriefingChunkRow, dist.label("d"))
                .where(BriefingChunkRow.project_id == pid))
        if angle:
            stmt = stmt.where(BriefingChunkRow.angle == angle)
        rows = s.execute(stmt.order_by(dist).limit(candidates)).all()
    cands = [{"text": r.BriefingChunkRow.text, "source": r.BriefingChunkRow.source,
              "score": 1.0 - float(r.d)} for r in rows]
    if len(cands) <= k:
        return cands[:k]                       # 재정렬할 게 없으면 리랭커 호출 자체를 아낀다
    # 로컬 임포트 — 순환 임포트 위험 회피(레포 관례).
    from ..services.llm_client import LLMError, get_llm

    try:
        ranked = get_llm().rerank(query, [c["text"] for c in cands], top_n=k)
    except LLMError as e:  # 리랭커 장애가 검색을 죽이지 않게 — 코사인 순서로 폴백
        log.warning("리랭크 실패, 코사인 순서로 폴백 (project=%s): %s", pid, e)
        return cands[:k]
    return [{**cands[i], "score": score} for i, score in ranked if 0 <= i < len(cands)][:k]


def has_knowledge(corpus: str) -> bool:
    """코퍼스에 행이 하나라도 있나 — 비어 있으면 상위 배선이 통째로 스킵(무동작)."""
    with db_session() as s:
        stmt = select(KnowledgeChunkRow.id).where(KnowledgeChunkRow.corpus == corpus).limit(1)
        return s.execute(stmt).first() is not None


def search_knowledge(query: str, corpus: str | None = None, k: int = 5, *,
                     meta_filters: dict | None = None, keywords: list[str] | None = None,
                     candidates: int = 30) -> list[dict]:
    """글로벌 지식 풀 검색 — 코사인 candidates → 리랭커 top-k. search_chunks 의 전역판.

    corpus 지정 시 그 코퍼스로 하드필터. meta_filters(dict) 는 JSONB 하드필터로 WHERE 에
    실린다 — 스칼라 값은 동등(meta ->> key == str(val)), 2-원소 튜플/리스트 (lo, hi) 는
    숫자 범위(cast(meta ->> key, Numeric) BETWEEN lo AND hi)로 변환한다.
    예: meta_filters={"age": (20, 29), "sex": "M"} → age BETWEEN 20 AND 29 AND sex = 'M'.

    keywords 가 주어지면 하이브리드 recall — 같은 필터에 text ILIKE '%kw%' OR 를 건 두
    번째 쿼리로 키워드 매칭 문서를 뽑아 벡터 후보에 id 로 디둡 병합한다(벡터가 놓친 문서도
    리랭커가 보게). 키워드 전용 행은 score=0.0 으로 들어가고 최종 순위는 리랭커가 정한다.
    이건 확장자 BM25 가 아니라 가벼운 어휘(ILIKE 부분일치) recall 보정이다 — 한국어
    stock-PG FTS 엔 형태소 토크나이저가 없어 부분일치 ILIKE 가 이식성 있는 선택.
    리랭커 실패면 코사인 순서 폴백.

    소비처: services/audience.collect_personas (RAG-7) — 가이드 생성 시 브리프로 검색.
    """
    def with_filters(stmt):
        """corpus + meta_filters(동등/범위) 공통 WHERE — 벡터·키워드 쿼리가 함께 쓴다."""
        if corpus:
            stmt = stmt.where(KnowledgeChunkRow.corpus == corpus)
        for key, val in (meta_filters or {}).items():
            col = KnowledgeChunkRow.meta[key].astext
            if isinstance(val, (tuple, list)) and len(val) == 2:   # (lo, hi) → 숫자 범위
                stmt = stmt.where(cast(col, Numeric).between(val[0], val[1]))
            else:                                                  # 스칼라 → 동등
                stmt = stmt.where(col == str(val))
        return stmt

    qv = embed_texts([query])[0]
    with db_session() as s:
        dist = KnowledgeChunkRow.embedding.cosine_distance(qv)
        stmt = with_filters(select(KnowledgeChunkRow, dist.label("d")))
        rows = s.execute(stmt.order_by(dist).limit(candidates)).all()
        cands = [{"text": r.KnowledgeChunkRow.text, "title": r.KnowledgeChunkRow.title,
                  "meta": r.KnowledgeChunkRow.meta or {}, "score": 1.0 - float(r.d)} for r in rows]
        if keywords:                           # 하이브리드 recall — 키워드 매칭 행을 합류(id 디둡)
            seen = {r.KnowledgeChunkRow.id for r in rows}
            kw_stmt = with_filters(select(KnowledgeChunkRow)).where(
                or_(*[KnowledgeChunkRow.text.ilike(f"%{kw}%") for kw in keywords]))
            for kr in s.execute(kw_stmt.limit(candidates)).all():
                c = kr.KnowledgeChunkRow
                if c.id in seen:               # 벡터에서 이미 뽑힌 행은 두 번 넣지 않는다
                    continue
                seen.add(c.id)
                cands.append({"text": c.text, "title": c.title,
                              "meta": c.meta or {}, "score": 0.0})   # 키워드 전용 → 순위는 리랭커가
    if len(cands) <= k:
        return cands[:k]                       # 재정렬할 게 없으면 리랭커 호출 자체를 아낀다
    # 로컬 임포트 — 순환 임포트 위험 회피(레포 관례).
    from ..services.llm_client import LLMError, get_llm

    try:
        ranked = get_llm().rerank(query, [c["text"] for c in cands], top_n=k)
    except LLMError as e:  # 리랭커 장애가 검색을 죽이지 않게 — 코사인 순서로 폴백
        log.warning("리랭크 실패, 코사인 순서로 폴백 (corpus=%s): %s", corpus, e)
        return cands[:k]
    return [{**cands[i], "score": score} for i, score in ranked if 0 <= i < len(cands)][:k]


def refresh_project(pid: str) -> None:
    """자료 변경 후 후처리 — RAG 재인덱싱 + 슬롯별 요약 재계산·저장.

    요약 LLM 이 실패해도 인덱싱은 이미 끝났으므로 그 슬롯 요약만 비운다(인터뷰 RAG 는 산다).
    """
    from ..services.material import summarize_slot
    from ..services.store import list_materials, save_slot_summary

    try:
        index_project(pid)
    except Exception as e:  # noqa: BLE001 — 임베딩 일시 장애가 수집을 죽이지 않게(다음 refresh 가 따라잡음)
        log.warning("인덱싱 실패, 다음 refresh 로 미룸 (project=%s): %s", pid, e)
    by_angle: dict[str, list[str]] = {}
    for m in list_materials(pid):
        by_angle.setdefault(m.angle, []).append(m.text)
    for angle in ("현상", "원인", "활용"):
        try:
            summary = summarize_slot(by_angle.get(angle, []))
        except Exception as e:  # noqa: BLE001 — 요약 실패가 수집을 죽이지 않게
            log.warning("슬롯 요약 실패 (project=%s, angle=%s): %s", pid, angle, e)
            summary = ""
        save_slot_summary(pid, angle, summary)


def index_material(pid: str, m) -> int:
    """자료 1개만 청크·임베딩해서 append(전체 재구축 안 함). 반환=추가 청크 수.

    seq 는 자료 내부 순번이라 프로젝트 전역에서 유일하지 않다(검색은 seq 를 안 쓰고 코사인
    순이므로 무해). 전역 재번호가 필요하면 full rebuild(index_project)를 쓴다.
    """
    rows = chunks_with_angle([m])
    if not rows:
        return 0
    vecs = embed_texts([r[1] for r in rows])
    with db_session() as s:
        for (seq, text, angle, source), v in zip(rows, vecs):
            s.add(BriefingChunkRow(id=new_id("b_"), project_id=pid, seq=seq,
                                   text=text, source=source, angle=angle, embedding=v))
        s.commit()
    return len(rows)


def refresh_slot(pid: str, angle: str) -> None:
    """그 슬롯 자료만 모아 재요약·저장. 요약 실패는 흡수하고 '' 저장."""
    from ..services.material import summarize_slot
    from ..services.store import list_materials, save_slot_summary

    texts = [m.text for m in list_materials(pid) if m.angle == angle]
    try:
        summary = summarize_slot(texts)
    except Exception as e:  # noqa: BLE001 — 요약 실패가 수집을 죽이지 않게
        log.warning("슬롯 요약 실패 (project=%s, angle=%s): %s", pid, angle, e)
        summary = ""
    save_slot_summary(pid, angle, summary)


def add_materials_incremental(pid: str, materials: list) -> None:
    """추가된 자료만 증분 인덱싱 + 건드린 슬롯만 재요약. 인덱싱 실패는 흡수(다음 refresh 가 따라잡음)."""
    for m in materials:
        try:
            index_material(pid, m)
        except Exception as e:  # noqa: BLE001 — 임베딩 일시 장애가 수집을 죽이지 않게
            log.warning("증분 인덱싱 실패, 다음 refresh 로 미룸 (project=%s, material=%s): %s",
                        pid, getattr(m, "id", "?"), e)
    for angle in {m.angle for m in materials}:
        refresh_slot(pid, angle)
