"""브리핑 팩 인덱싱 — 업로드 자료(material_text) → 청크 → 임베딩 → pgvector.

단순 파이프라인이라 LangGraph 불필요(계획 §3.4 규칙). 입구는 팀원의 material
업로드를 재활용한다 — 웹 자동 리서치·승인 게이트는 라이트 판에서 컷.
"""
from __future__ import annotations

import logging

from sqlalchemy import delete, select

from ..services.db import BriefingChunkRow, db_session
from ..services.embeddings import embed_texts
from ..services.store import get_project, new_id

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


def index_project(pid: str, source: str = "업로드 자료") -> int:
    """멱등 인덱싱 — 기존 청크를 지우고 material_text 로 다시 적재. 반환 = 청크 수."""
    p = get_project(pid)
    if not p or not (p.material_text or "").strip():
        return 0
    chunks = chunk_text(p.material_text)
    if not chunks:
        return 0
    vecs = embed_texts(chunks)
    with db_session() as s:
        s.execute(delete(BriefingChunkRow).where(BriefingChunkRow.project_id == pid))
        for i, (c, v) in enumerate(zip(chunks, vecs)):
            s.add(BriefingChunkRow(id=new_id("b_"), project_id=pid, seq=i,
                                   text=c, source=source, embedding=v))
        s.commit()
    log.info("브리핑 인덱싱 완료 (project=%s, chunks=%d)", pid, len(chunks))
    return len(chunks)


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
