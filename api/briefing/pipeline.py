"""브리핑 팩 인덱싱 — 업로드 자료(material_text) → 청크 → 임베딩 → pgvector.

단순 파이프라인이라 LangGraph 불필요(계획 §3.4 규칙). 입구는 팀원의 material
업로드를 재활용한다 — 웹 자동 리서치·승인 게이트는 라이트 판에서 컷.
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, select

from ..services.db import BriefingChunkRow, db_session
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


def search_chunks(pid: str, query: str, k: int = 3) -> list[dict]:
    """코사인 top-k — v1은 임베딩만(리랭커는 §8 확인 후)."""
    qv = embed_texts([query])[0]
    with db_session() as s:
        dist = BriefingChunkRow.embedding.cosine_distance(qv)
        rows = s.execute(
            select(BriefingChunkRow, dist.label("d"))
            .where(BriefingChunkRow.project_id == pid)
            .order_by(dist).limit(k)
        ).all()
    return [{"text": r.BriefingChunkRow.text, "source": r.BriefingChunkRow.source,
             "score": 1.0 - float(r.d)} for r in rows]


def refresh_project(pid: str) -> None:
    """자료 변경 후 후처리 — RAG 재인덱싱 + 슬롯별 요약 재계산·저장.

    요약 LLM 이 실패해도 인덱싱은 이미 끝났으므로 그 슬롯 요약만 비운다(인터뷰 RAG 는 산다).
    """
    from ..services.material import summarize_slot
    from ..services.store import list_materials, save_slot_summary

    index_project(pid)
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
